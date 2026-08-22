"""
dem.py — DEM loading and processing utilities.

Owner: Engineer 3 (Geospatial Digital Twin / Flood Scenario Simulation)

Responsibilities of this module:
    - Load a Digital Elevation Model (DEM) raster from local scratch disk
      (downloaded temporarily from Supabase Storage — see README.md).
    - Expose the elevation array, nodata mask, affine transform and source CRS
      needed by simulation.py and geometry.py.
    - Provide small helper stats used for sanity-checking a region's DEM
      before running a scenario.

This module does NOT touch Supabase directly. Per DATA_FORMATS.md §6, the
DEM file itself is expected to already exist as a local temp file (downloaded
from the `dem/` Supabase Storage bucket by the caller / backend service
layer). This keeps digital_twin/ testable in isolation, per ENGG_3.txt's
requirement that "the module must work independently before integration".
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

import numpy as np

try:
    import rasterio
    from rasterio.errors import RasterioIOError
    from rasterio.transform import Affine
    _HAS_RASTERIO = True
except ImportError:  # pragma: no cover - allows unit-testing core math without rasterio
    _HAS_RASTERIO = False
    RasterioIOError = Exception  # placeholder so the except clause below still parses


@dataclass
class DEMData:
    """In-memory representation of a loaded DEM."""

    elevation: np.ndarray          # 2D float array, NaN where nodata
    transform: "Affine"            # affine georeferencing transform (pixel -> CRS coords)
    crs: str                       # source CRS of the raster, e.g. "EPSG:32644" (UTM) or "EPSG:4326"
    nodata: Optional[float]
    width: int
    height: int
    pixel_size_x: float
    pixel_size_y: float


def load_dem(path: str, crs_override: Optional[str] = None) -> DEMData:
    """
    Load a DEM GeoTIFF from local disk into memory.

    Elevation values and `flood_level` (see simulation.py) are both assumed
    to be in **metres**, in the **same vertical reference** — this module
    performs no vertical-datum conversion (documented MVP assumption, see
    README.md "Documented assumptions" §2).

    Parameters
    ----------
    path : str
        Path to a local, temporary DEM file (already downloaded from the
        Supabase `dem/` storage bucket by the caller).
    crs_override : str, optional
        Explicit CRS (e.g. "EPSG:32644") to use if the DEM file has no
        embedded CRS. Only use this when you have independently confirmed
        the DEM's true CRS out-of-band (e.g. from the data source's
        documentation) — see the ValueError below for why this is required
        rather than assumed.

    Returns
    -------
    DEMData

    Raises
    ------
    FileNotFoundError
        If `path` does not exist.
    ImportError
        If rasterio is not installed.
    RasterioIOError
        If the file exists but cannot be read as a raster (corrupt/unsupported).
    ValueError
        If the DEM has no embedded CRS and `crs_override` was not supplied.
        We deliberately do NOT default to EPSG:4326 or any other CRS here:
        DEM sources are frequently in a projected CRS (e.g. UTM), and
        silently treating projected coordinates as lon/lat would corrupt
        every downstream area/geometry calculation without any visible error.
    ValueError
        If the DEM contains zero valid (non-NoData) pixels.

    Notes
    -----
    - The DEM's native/projected CRS is preserved as-is (per DATA_FORMATS.md §1,
      raster processing may use a native/projected CRS transiently). Reprojection
      to EPSG:4326 happens only for the *vector* simulation result, in geometry.py,
      right before it is persisted to PostGIS.
    - NoData cells are converted to np.nan using rasterio's masked read, which
      is more robust than a manual `== nodata` float comparison (avoids
      precision-drift false negatives/positives on float DEMs).
    """
    if not _HAS_RASTERIO:
        raise ImportError(
            "rasterio is required to load DEM files. Install project "
            "dependencies with `pip install -r requirements.txt`."
        )
    if not os.path.exists(path):
        raise FileNotFoundError(f"DEM file not found: {path}")

    try:
        with rasterio.open(path) as src:
            masked = src.read(1, masked=True).astype("float64")
            # Fill masked (NoData) cells with NaN so every downstream
            # comparison (elevation <= flood_level) treats them consistently
            # as "unknown", never as "low ground".
            band1 = np.ma.filled(masked, np.nan)
            nodata = src.nodata

            if src.crs is None:
                if crs_override is None:
                    raise ValueError(
                        f"DEM at '{path}' has no embedded CRS and no crs_override "
                        "was supplied. Refusing to guess (e.g. defaulting to "
                        "EPSG:4326) since an incorrect CRS silently corrupts area "
                        "and geometry calculations. Confirm the DEM's true CRS and "
                        "pass it explicitly via load_dem(path, crs_override=...)."
                    )
                crs = crs_override
            else:
                crs = src.crs.to_string()

            transform = src.transform
            pixel_size_x = abs(transform.a)
            pixel_size_y = abs(transform.e)
            width, height = src.width, src.height
    except RasterioIOError as exc:
        raise RasterioIOError(
            f"DEM at '{path}' exists but could not be read as a raster "
            f"(corrupt file or unsupported format): {exc}"
        ) from exc

    valid_pixel_count = int(np.sum(~np.isnan(band1)))
    if valid_pixel_count == 0:
        raise ValueError(
            f"DEM at '{path}' contains zero valid (non-NoData) pixels — "
            "cannot run a simulation against an empty DEM."
        )

    return DEMData(
        elevation=band1,
        transform=transform,
        crs=crs,
        nodata=nodata,
        width=width,
        height=height,
        pixel_size_x=pixel_size_x,
        pixel_size_y=pixel_size_y,
    )


def dem_stats(dem: DEMData) -> dict:
    """Quick sanity-check summary of a loaded DEM (used for logging / debugging)."""
    valid = dem.elevation[~np.isnan(dem.elevation)]
    if valid.size == 0:
        return {"min": None, "max": None, "mean": None, "valid_pixels": 0}
    return {
        "min": float(np.min(valid)),
        "max": float(np.max(valid)),
        "mean": float(np.mean(valid)),
        "valid_pixels": int(valid.size),
        "total_pixels": int(dem.elevation.size),
    }


def cleanup_local_file(path: str) -> None:
    """
    Delete a temporary local DEM file after processing.

    Per COMMON.txt / ARCHITECTURE.md §7: local files are scratch space only,
    never a persistent store. Callers should invoke this once the simulation
    result has been written back to Supabase Storage/PostGIS.
    """
    if path and os.path.exists(path):
        os.remove(path)
