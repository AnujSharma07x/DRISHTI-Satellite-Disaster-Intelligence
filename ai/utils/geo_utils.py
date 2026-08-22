"""
geo_utils.py
============
Converts a binary flood mask (raster, native/projected CRS) into the vector
GeoJSON contract required by DATA_FORMATS.md and API_CONTRACT.md:

    - Stored/returned geometry: MultiPolygon, EPSG:4326 (WGS84)
    - Area: square kilometres (km2)

Required flow (DATA_FORMATS.md #1):
    raster (native/projected CRS, transient)
        -> vectorize mask
        -> dissolve into a single (multi)polygon
        -> reproject to EPSG:4326
        -> [caller stores this GeoJSON in flood_predictions.geometry]

Rule: no vector data produced here is ever left in a projected CRS - the last
step of every public function in this file is a reprojection to EPSG:4326 (or,
for area, a *temporary* reprojection to an equal-area CRS purely for the
calculation, per DATA_FORMATS.md's explicit carve-out for accurate area math).
"""

from __future__ import annotations

import logging
from typing import Optional

import numpy as np

try:
    import rasterio
    from rasterio.features import shapes as rasterio_shapes
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "rasterio is required for geo_utils.py. "
        "Install with: pip install rasterio --break-system-packages"
    ) from exc

try:
    import geopandas as gpd
    from shapely.geometry import shape, mapping, MultiPolygon, Polygon
    from shapely.ops import unary_union
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "geopandas/shapely are required for geo_utils.py. "
        "Install with: pip install geopandas shapely --break-system-packages"
    ) from exc

logger = logging.getLogger("drishti.ai.geo_utils")

TARGET_CRS = "EPSG:4326"
# Equal-area projection used ONLY transiently for km2 calculations, never for
# storage (see DATA_FORMATS.md #1). World Cylindrical Equal Area.
EQUAL_AREA_CRS = "EPSG:6933"


def mask_to_geometry(
    mask: np.ndarray,
    transform: "rasterio.Affine",
    src_crs,
    valid_mask: Optional[np.ndarray] = None,
    min_region_pixels: int = 4,
) -> Optional[dict]:
    """Vectorize a binary flood mask into a single EPSG:4326 GeoJSON
    MultiPolygon (matching `flood_predictions.geometry`, a
    `geometry(MultiPolygon, 4326)` column - DATABASE_SCHEMA.md #3).

    Args:
        mask: 2D binary array (1 = flooded, 0 = not flooded).
        transform: the affine transform of the source raster (post-flood
            image, per preprocessing.preprocess_pair()).
        src_crs: the source raster's CRS (native/projected - fine here,
            it is only used transiently).
        valid_mask: optional 2D bool array, True where the pixel is real
            data (not NoData). If given, invalid pixels are excluded from
            vectorization even if `mask` somehow flags them (defence in
            depth - `inference.run_inference` already zeroes these out, but
            this keeps geo_utils safe to call independently too - STEP 5).
        min_region_pixels: drop vectorized regions smaller than this many
            pixels (removes speckle-noise-driven single-pixel "islands").

    Returns:
        A GeoJSON-like dict (as produced by shapely.geometry.mapping),
        type "MultiPolygon", in EPSG:4326 - or None if no flood was detected.
    """
    binary_mask = (mask > 0).astype("uint8")
    if valid_mask is not None:
        binary_mask = np.where(valid_mask, binary_mask, 0).astype("uint8")

    if binary_mask.sum() == 0:
        logger.info("No flooded pixels in mask - returning no geometry.")
        return None

    polygons = []
    for geom_dict, value in rasterio_shapes(binary_mask, mask=binary_mask.astype(bool), transform=transform):
        if value != 1:
            continue
        geom = shape(geom_dict)
        if geom.is_empty:
            continue
        polygons.append(geom)

    if not polygons:
        return None

    # Build a GeoDataFrame in the source CRS, drop tiny noise regions, then
    # dissolve everything into one (multi)polygon and reproject once.
    gdf = gpd.GeoDataFrame({"geometry": polygons}, crs=src_crs)

    # Pixel area in the source CRS units^2, used only to filter noise regions.
    px_w, px_h = abs(transform.a), abs(transform.e)
    min_area = min_region_pixels * px_w * px_h
    gdf = gdf[gdf.geometry.area >= min_area]

    if gdf.empty:
        logger.info("All vectorized regions were below the noise-area threshold.")
        return None

    dissolved = unary_union(gdf.geometry.tolist())
    dissolved = _ensure_multipolygon(dissolved)

    gdf_out = gpd.GeoDataFrame({"geometry": [dissolved]}, crs=src_crs)
    gdf_wgs84 = gdf_out.to_crs(TARGET_CRS)  # -> EPSG:4326, per DATA_FORMATS.md #1

    return mapping(gdf_wgs84.geometry.iloc[0])


def calculate_area_km2(geometry_geojson: dict, src_crs: str = TARGET_CRS) -> float:
    """Compute the geometry's area in km2 using a temporary equal-area
    reprojection (DATA_FORMATS.md #1 explicitly allows this: "Projected CRS
    is only acceptable transiently, in memory or in a temp file, for
    calculations like accurate area (km2)").

    Args:
        geometry_geojson: GeoJSON dict, assumed to already be in `src_crs`
            (defaults to EPSG:4326, matching how mask_to_geometry() returns it).
    """
    geom = shape(geometry_geojson)
    gdf = gpd.GeoDataFrame({"geometry": [geom]}, crs=src_crs)
    gdf_equal_area = gdf.to_crs(EQUAL_AREA_CRS)  # transient only, never persisted
    area_m2 = float(gdf_equal_area.geometry.area.iloc[0])
    return round(area_m2 / 1_000_000.0, 4)


def _ensure_multipolygon(geom):
    """flood_predictions.geometry is typed geometry(MultiPolygon, 4326) -
    wrap a bare Polygon so downstream inserts never fail on geometry-type
    mismatch."""
    if isinstance(geom, Polygon):
        return MultiPolygon([geom])
    return geom
