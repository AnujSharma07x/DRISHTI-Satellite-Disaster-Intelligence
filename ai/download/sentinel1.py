#!/usr/bin/env python3
"""
sentinel1.py
============
Small, reproducible Sentinel-1 GRD acquisition utility for the Assam demo
AOI (Phase 4). This is a thin wrapper around the Alaska Satellite Facility
(ASF) `asf_search` API - NOT a new data-processing pipeline. It only
finds and downloads scenes; everything downstream (preprocessing,
inference, geometry) is the existing, unmodified `ai/` pipeline.

Why ASF / asf_search: it's the standard free, programmatic, no-scraping
way to search and download Sentinel-1 GRD products (mirrors Copernicus
data, requires only a free NASA Earthdata login), and returns products in
the calibrated/terrain-corrected form `sar_preprocessing.py` already
assumes ("analysis-ready Sentinel-1 GRD" - see that module's docstring).

Demo AOI: a small bounding box around Morigaon district, Assam
(`data/mock/sample_event.json` already uses this as the placeholder demo
event location) - NOT all of Assam, per the "do not download all of
Assam" / "small demonstration AOI" constraint.

Credentials: NASA Earthdata login, read only from environment variables
(never hardcoded/committed, consistent with `ai/utils/storage_utils.py`'s
existing Supabase-credential handling):
    EARTHDATA_USERNAME
    EARTHDATA_PASSWORD

Network note: this sandboxed execution environment's network allowlist
does not include ASF/Earthdata endpoints, so this script cannot actually
be *run* here - it is provided as a ready-to-use, documented utility for
a machine with real internet access and Earthdata credentials (i.e. a
teammate's laptop or a CI runner with those endpoints reachable). See the
Phase-4 note in the final deliverable summary.

Usage
-----
    export EARTHDATA_USERNAME=...
    export EARTHDATA_PASSWORD=...

    # Search only (no download), to sanity-check what's available first:
    python -m ai.download.sentinel1 search \\
        --start 2026-06-01 --end 2026-06-03

    # Download a pre-flood and a post-flood scene into ./data/satellite/raw:
    python -m ai.download.sentinel1 fetch-pair \\
        --pre-date 2026-06-01 --post-date 2026-06-05 \\
        --out data/satellite/raw
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path
from typing import Optional

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("drishti.ai.download.sentinel1")

# Small bounding box (lon_min, lat_min, lon_max, lat_max) around Morigaon
# district, Assam - approximate, demo-scale only (not survey-grade), matches
# data/mock/sample_event.json's placeholder demo event location.
DEMO_AOI_BBOX = (92.20, 26.20, 92.45, 26.40)


def _aoi_wkt(bbox=DEMO_AOI_BBOX) -> str:
    lon_min, lat_min, lon_max, lat_max = bbox
    return (
        f"POLYGON(({lon_min} {lat_min}, {lon_max} {lat_min}, "
        f"{lon_max} {lat_max}, {lon_min} {lat_max}, {lon_min} {lat_min}))"
    )


def _require_asf_search():
    try:
        import asf_search  # noqa: F401
        return asf_search
    except ImportError as exc:
        raise ImportError(
            "asf_search is required for ai/download/sentinel1.py. "
            "Install with: pip install asf_search --break-system-packages"
        ) from exc


def _require_credentials() -> tuple:
    user = os.environ.get("EARTHDATA_USERNAME")
    password = os.environ.get("EARTHDATA_PASSWORD")
    if not user or not password:
        raise EnvironmentError(
            "EARTHDATA_USERNAME and EARTHDATA_PASSWORD must be set as "
            "environment variables (free NASA Earthdata account: "
            "https://urs.earthdata.nasa.gov/users/new). Never hardcode "
            "credentials in this file."
        )
    return user, password


def search_scenes(start_date: str, end_date: str, bbox=DEMO_AOI_BBOX, max_results: int = 10):
    """Search ASF for Sentinel-1 GRD scenes over the demo AOI within a date
    range. Returns the raw asf_search result list; does not download
    anything, so it's safe to run repeatedly to check availability/orbit
    coverage before committing to a download.
    """
    asf = _require_asf_search()

    logger.info("Searching Sentinel-1 GRD: AOI=%s, %s -> %s", bbox, start_date, end_date)
    results = asf.geo_search(
        platform=[asf.PLATFORM.SENTINEL1],
        processingLevel=[asf.PRODUCT_TYPE.GRD_HD],
        intersectsWith=_aoi_wkt(bbox),
        start=start_date,
        end=end_date,
        maxResults=max_results,
    )
    logger.info("Found %d scene(s).", len(results))
    for r in results:
        props = r.properties
        logger.info("  %s  date=%s  polarizations=%s", props.get("sceneName"), props.get("startTime"), props.get("polarization"))
    return results


def download_scene(result, out_dir: str) -> str:
    """Download a single asf_search result to `out_dir`. Returns the local
    file path. Requires EARTHDATA_USERNAME/PASSWORD (see module docstring).
    """
    asf = _require_asf_search()
    user, password = _require_credentials()

    Path(out_dir).mkdir(parents=True, exist_ok=True)
    session = asf.ASFSession().auth_with_creds(user, password)

    logger.info("Downloading %s -> %s", result.properties.get("sceneName"), out_dir)
    result.download(path=out_dir, session=session)

    filename = result.properties.get("fileName")
    return os.path.join(out_dir, filename) if filename else out_dir


def fetch_pair(pre_date: str, post_date: str, out_dir: str, bbox=DEMO_AOI_BBOX, window_days: int = 1) -> tuple:
    """Find and download the closest available scene to `pre_date` and to
    `post_date` over the demo AOI (Phase 4/5 - "pre-flood Sentinel-1 +
    post/during-flood Sentinel-1", "prefer ... same/similar orbit/track
    where practical").

    This does NOT itself produce analysis-ready calibrated dB GeoTIFFs -
    raw ASF GRD downloads still need the existing
    `preprocessing/sar_preprocessing.py` assumptions to hold (radiometric
    calibration + terrain correction). If the downloaded product is not
    already analysis-ready, run it through SNAP / the ASF On Demand HyP3
    RTC pipeline first - this is a documented follow-up, not implemented
    here, per "Do NOT create an unnecessarily complicated Sentinel-1
    processing chain".
    """

    def _closest(date: str):
        # +/- window_days search window around the target date, narrowed
        # to the single closest-in-time result.
        from datetime import datetime, timedelta

        d = datetime.fromisoformat(date)
        start = (d - timedelta(days=window_days)).strftime("%Y-%m-%d")
        end = (d + timedelta(days=window_days + 1)).strftime("%Y-%m-%d")
        results = search_scenes(start, end, bbox=bbox, max_results=5)
        if not results:
            raise RuntimeError(f"No Sentinel-1 GRD scene found near {date} over the demo AOI.")
        return results[0]

    pre_scene = _closest(pre_date)
    post_scene = _closest(post_date)

    pre_path = download_scene(pre_scene, os.path.join(out_dir, "pre_flood"))
    post_path = download_scene(post_scene, os.path.join(out_dir, "post_flood"))
    return pre_path, post_path


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Sentinel-1 acquisition utility for the DRISHTI Assam demo AOI")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("search", help="Search only, no download")
    s.add_argument("--start", required=True)
    s.add_argument("--end", required=True)
    s.add_argument("--max-results", type=int, default=10)

    f = sub.add_parser("fetch-pair", help="Download closest pre/post scenes")
    f.add_argument("--pre-date", required=True)
    f.add_argument("--post-date", required=True)
    f.add_argument("--out", default="data/satellite/raw")
    f.add_argument("--window-days", type=int, default=1)

    return p.parse_args()


def main() -> int:
    args = _parse_args()
    if args.command == "search":
        search_scenes(args.start, args.end, max_results=args.max_results)
    elif args.command == "fetch-pair":
        pre_path, post_path = fetch_pair(args.pre_date, args.post_date, args.out, window_days=args.window_days)
        logger.info("Pre-flood scene:  %s", pre_path)
        logger.info("Post-flood scene: %s", post_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
