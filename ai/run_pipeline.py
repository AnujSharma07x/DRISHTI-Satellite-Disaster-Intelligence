#!/usr/bin/env python3
"""
run_pipeline.py
================
Independent, end-to-end executable for the Engineer 2 AI flood-detection
module.

    Sentinel-1 pre-flood image + Sentinel-1 post-flood image
        -> Input validation
        -> SAR preprocessing
        -> Flood detection
        -> Flood probability/score
        -> Binary flood mask
        -> Noise filtering
        -> Flood polygon
        -> Flood area calculation
        -> Output metadata
        -> Optional Supabase Storage upload

Usage
-----
Demo mode (no real satellite files needed - generates a synthetic Sentinel-1
style pre/post SAR pair, including a NoData region, over a sample
flood-prone region, clearly labelled as SYNTHETIC/DEMO data - see STEP 15):

    python run_pipeline.py --demo --region-id demo-region-001

Real data:

    python -m ai.run_pipeline \\
        --pre  /path/to/pre_flood.tif \\
        --post /path/to/post_flood.tif \\
        --region-id <uuid-from-regions-table> \\
        --out ./output \\
        [--weights models/weights/light_unet.pt] \\
        [--drop-threshold-db 3.0] \\
        [--upload]

Output (written to --out)
--------------------------
- flood_prediction.json  - dict matching the `flood_predictions` row contract
                            (DATABASE_SCHEMA.md #3 / API_CONTRACT.md)
- flood_polygon.geojson  - the flood polygon alone, as a standalone GeoJSON file
- flood_mask.tif         - binary flood mask raster (uint8, CRS/transform preserved)

Per ARCHITECTURE.md #7 ("local files may only be used temporarily during
processing"), `--out` is a scratch/handoff directory for Engineer 1's
integration layer to pick up (and, for the mask raster, optionally upload to
Supabase Storage) - not the system of record.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import tempfile
import uuid
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ai.preprocessing.sar_preprocessing import preprocess_pair, RasterData
from ai.models.unet import load_model, ThresholdFloodModel
from ai.inference.predict import run_inference
from ai.utils.geo_utils import mask_to_geometry, calculate_area_km2
from ai.utils.schema import build_flood_prediction_payload
from ai.utils.storage_utils import upload_mask_raster, StorageUploadError

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("drishti.ai.run_pipeline")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="DRISHTI AI flood-detection pipeline (Engineer 2)")
    parser.add_argument("--pre", type=str, help="Path to pre-flood SAR GeoTIFF")
    parser.add_argument("--post", type=str, help="Path to post-flood SAR GeoTIFF")
    parser.add_argument("--region-id", type=str, default=None, help="regions.id (UUID) this prediction belongs to")
    parser.add_argument("--flood-event-id", type=str, default=None, help="Optional flood_events.id")
    parser.add_argument("--satellite-observation-id", type=str, default=None)
    parser.add_argument("--weights", type=str, default=None, help="Path to trained LightUNet weights (.pt)")
    parser.add_argument("--threshold", type=float, default=0.5, help="Flood classification probability/proxy threshold (0-1)")
    parser.add_argument(
        "--drop-threshold-db", type=float, default=ThresholdFloodModel.DEFAULT_DROP_THRESHOLD_DB,
        help=(
            "ThresholdFloodModel baseline only: minimum pre->post SAR backscatter "
            "drop, in dB, to count as flooded. See models/unet.py docstring for "
            "the literature-informed default and why it's configurable, not hardcoded."
        ),
    )
    parser.add_argument("--min-region-pixels", type=int, default=4, help="Drop vectorized flood regions smaller than this many pixels (noise filtering)")
    parser.add_argument("--out", "--output-dir", dest="out", type=str, default="./output", help="Output directory for local scratch/handoff files")
    parser.add_argument("--upload", action="store_true", help="Upload mask raster to Supabase Storage (requires env vars)")
    parser.add_argument("--delete-local-mask-after-upload", action="store_true", help="Delete the local mask GeoTIFF once it has been confirmed uploaded to Supabase Storage")
    parser.add_argument("--demo", action="store_true", help="Generate a synthetic, clearly-labelled SAR pair instead of reading real files")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if not args.demo and (not args.pre or not args.post):
        logger.error("Provide --pre and --post, or use --demo for a synthetic run.")
        return 1

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    region_id = args.region_id or "demo-region-001"

    temp_dir = tempfile.mkdtemp(prefix="drishti_ai_")
    try:
        if args.demo:
            pre_path, post_path = _generate_demo_sar_pair(temp_dir)
            logger.warning(
                "DEMO MODE: using SYNTHETIC SAR data (not a real satellite "
                "observation). Do not present this output as a real "
                "flood detection result."
            )
        else:
            pre_path, post_path = args.pre, args.post

        # 1-3. Input validation + SAR preprocessing (load, validate
        # alignment, calibrate to dB, despeckle, joint-normalize)
        logger.info("Preprocessing: loading and validating pre/post SAR pair...")
        try:
            prep = preprocess_pair(pre_path, post_path)
        except (FileNotFoundError, ValueError) as exc:
            logger.error("Preprocessing failed: %s", exc)
            return 1
        logger.info(
            "Preprocessing OK: %d/%d pixels valid (non-NoData).",
            int(prep.valid_mask.sum()), prep.valid_mask.size,
        )

        # 4-6. Flood detection -> probability/score -> binary mask
        if args.weights:
            model = load_model(weights_path=args.weights)
        else:
            model = ThresholdFloodModel(drop_threshold_db=args.drop_threshold_db)
        logger.info("Detection method: %s", type(model).__name__)

        result = run_inference(
            pre_db=prep.pre_db,
            post_db=prep.post_db,
            valid_mask=prep.valid_mask,
            pre_norm=prep.pre_norm,
            post_norm=prep.post_norm,
            model=model,
            threshold=args.threshold,
        )

        # 7. Noise filtering + flood polygon (EPSG:4326)
        geometry = mask_to_geometry(
            result.mask,
            prep.reference.transform,
            prep.reference.crs,
            valid_mask=prep.valid_mask,
            min_region_pixels=args.min_region_pixels,
        )

        # 8. Flood area calculation (equal-area CRS, never lat/lon degrees)
        flood_area_km2 = calculate_area_km2(geometry) if geometry is not None else 0.0

        # Save mask raster + standalone GeoJSON (local scratch/handoff output)
        mask_path = out_dir / "flood_mask.tif"
        _write_mask_raster(result.mask, prep.reference, str(mask_path))

        geojson_path = out_dir / "flood_polygon.geojson"
        with open(geojson_path, "w") as f:
            json.dump(geometry if geometry is not None else {"type": "MultiPolygon", "coordinates": []}, f, indent=2)

        # 9. Optional Supabase Storage upload
        mask_storage_path = None
        if args.upload:
            prediction_id = str(uuid.uuid4())
            try:
                mask_storage_path = upload_mask_raster(
                    local_path=str(mask_path),
                    region_slug=region_id,
                    prediction_id=prediction_id,
                )
                if args.delete_local_mask_after_upload:
                    os.remove(mask_path)
                    logger.info("Deleted local mask raster after confirmed Supabase Storage upload.")
            except StorageUploadError as exc:
                logger.warning("Supabase Storage upload skipped: %s", exc)

        # 10. Output metadata (flood_predictions contract)
        payload = build_flood_prediction_payload(
            region_id=region_id,
            model_version=result.model_name,
            confidence=result.confidence,
            flood_area_km2=flood_area_km2,
            geometry=geometry,
            mask_storage_path=mask_storage_path,
            flood_event_id=args.flood_event_id,
            satellite_observation_id=args.satellite_observation_id,
            status="completed",
        )

        payload_path = out_dir / "flood_prediction.json"
        with open(payload_path, "w") as f:
            json.dump(payload, f, indent=2)

        # Extra, non-contract diagnostic info goes in a SEPARATE sidecar
        # file - flood_prediction.json above must stay an exact match for
        # the flood_predictions row shape (DATABASE_SCHEMA.md #3) so
        # Engineer 1 can insert it directly without stripping unexpected
        # keys ("Do NOT invent new database columns").
        metadata = {
            "is_calibrated_probability": result.is_calibrated_probability,
            "valid_pixels": int(prep.valid_mask.sum()),
            "total_pixels": int(prep.valid_mask.size),
            "flooded_pixels": int(result.mask.sum()),
            "drop_threshold_db": args.drop_threshold_db if isinstance(model, ThresholdFloodModel) else None,
            "probability_threshold": args.threshold,
            "demo_mode": bool(args.demo),
        }
        metadata_path = out_dir / "inference_metadata.json"
        with open(metadata_path, "w") as f:
            json.dump(metadata, f, indent=2)

        flooded_pixels = int(result.mask.sum())
        confidence_label = "calibrated model probability" if result.is_calibrated_probability else "heuristic proxy (NOT a calibrated probability)"

        logger.info("=" * 60)
        logger.info("PIPELINE SUMMARY")
        logger.info("  Detection method:      %s", result.model_name)
        logger.info("  Flooded pixels:        %d / %d valid", flooded_pixels, int(prep.valid_mask.sum()))
        logger.info("  Flood area:            %.4f km2", flood_area_km2)
        logger.info("  Confidence:            %.3f (%s)", result.confidence, confidence_label)
        logger.info("  Mask raster:           %s", mask_path)
        logger.info("  Flood polygon GeoJSON: %s", geojson_path)
        logger.info("  flood_predictions payload: %s", payload_path)
        logger.info("  Inference metadata:    %s", metadata_path)
        if args.upload and mask_storage_path is None:
            logger.warning("  Supabase Storage upload was requested but did not complete - see warning above.")
        logger.info("=" * 60)

        return 0
    finally:
        _cleanup_dir(temp_dir)


def _generate_demo_sar_pair(temp_dir: str):
    """Build a small, self-contained SYNTHETIC Sentinel-1-style pre/post SAR
    pair so the pipeline can run without any real satellite data. This is
    demo/test data only - see STEP 15: never present it as a real detection.

    Demo region: a sample flood-prone area near the Mahanadi delta,
    Odisha, India (ARCHITECTURE.md #9 assumption 3: "One region is seeded
    manually for the MVP demo"). Coordinates are approximate and for
    demonstration only - not survey-grade.

    Also includes a NoData region (simulating a sensor gap / masked area)
    so the demo run exercises NoData handling end-to-end, not just the
    happy path.
    """
    import rasterio
    from rasterio.transform import from_origin

    rng = np.random.default_rng(seed=42)
    height, width = 200, 200
    pixel_size = 10.0  # metres
    nodata_value = -9999.0

    # Approximate UTM 45N easting/northing near Cuttack, Odisha.
    origin_x, origin_y = 466000.0, 2264000.0
    transform = from_origin(origin_x, origin_y, pixel_size, pixel_size)
    crs = "EPSG:32645"  # WGS 84 / UTM zone 45N - reprojected to 4326 downstream

    baseline = rng.normal(loc=0.08, scale=0.02, size=(height, width)).clip(0.001, None)
    pre_flood = baseline.copy()
    post_flood = baseline.copy()

    # Simulate a flooded region (river overflow blob) with a strong
    # backscatter drop in the post-event image (~6-10 dB, within the
    # documented literature range for open water).
    yy, xx = np.mgrid[0:height, 0:width]
    cy, cx = 120, 90
    blob = ((yy - cy) / 55) ** 2 + ((xx - cx) / 40) ** 2 <= 1.0
    post_flood[blob] *= rng.uniform(0.08, 0.2, size=blob.sum())

    # Simulate a NoData strip (e.g. a sensor gap) present in both scenes.
    nodata_region = np.zeros((height, width), dtype=bool)
    nodata_region[0:15, :] = True

    pre_path = os.path.join(temp_dir, "demo_pre_flood.tif")
    post_path = os.path.join(temp_dir, "demo_post_flood.tif")

    for path, array in ((pre_path, pre_flood), (post_path, post_flood)):
        array = array.copy()
        array[nodata_region] = nodata_value
        with rasterio.open(
            path, "w",
            driver="GTiff",
            height=height, width=width, count=1,
            dtype="float32", crs=crs, transform=transform, nodata=nodata_value,
        ) as dst:
            dst.write(array.astype("float32"), 1)

    return pre_path, post_path


def _write_mask_raster(mask: np.ndarray, ref_raster: RasterData, path: str) -> None:
    import rasterio

    with rasterio.open(
        path, "w",
        driver="GTiff",
        height=ref_raster.height, width=ref_raster.width, count=1,
        dtype="uint8", crs=ref_raster.crs, transform=ref_raster.transform,
        nodata=0,
    ) as dst:
        dst.write(mask.astype("uint8"), 1)


def _cleanup_dir(path: str) -> None:
    import shutil

    try:
        shutil.rmtree(path, ignore_errors=True)
    except OSError:
        pass


if __name__ == "__main__":
    sys.exit(main())
