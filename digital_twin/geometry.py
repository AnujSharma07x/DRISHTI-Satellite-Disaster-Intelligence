"""
geometry.py — Raster-to-vector conversion, reprojection, and area math.

Owner: Engineer 3.

Enforces the spatial data standard locked in DATA_FORMATS.md §1:

    Satellite / DEM raster
            |
    AI or GIS processing
            |
    Temporary native/projected CRS (if required for accurate area/distance math)
            |
    Generate flood/result polygon
            |
    Convert vector result to EPSG:4326
            |
    Store in PostGIS (geometry(..., 4326))

Rule enforced here: no vector data produced by this module is ever handed
back to the caller in a projected CRS for persistence — only EPSG:4326.
Projected-CRS geometry is used internally, transiently, purely for accurate
area calculation, exactly as DATA_FORMATS.md §1 permits.
"""

from __future__ import annotations

from typing import Optional, Tuple

import numpy as np

try:
    import rasterio
    from rasterio.features import shapes as rasterio_shapes
    from rasterio.transform import Affine
    _HAS_RASTERIO = True
except ImportError:  # pragma: no cover
    _HAS_RASTERIO = False

try:
    from shapely.geometry import shape, MultiPolygon, Polygon
    from shapely.ops import unary_union, transform as shapely_transform
    _HAS_SHAPELY = True
except ImportError:  # pragma: no cover
    _HAS_SHAPELY = False

try:
    import pyproj
    _HAS_PYPROJ = True
except ImportError:  # pragma: no cover
    _HAS_PYPROJ = False


TARGET_CRS = "EPSG:4326"  # locked per DATA_FORMATS.md §1


def _require_deps():
    missing = [
        name
        for name, present in (
            ("rasterio", _HAS_RASTERIO),
            ("shapely", _HAS_SHAPELY),
            ("pyproj", _HAS_PYPROJ),
        )
        if not present
    ]
    if missing:
        raise ImportError(
            f"Missing required dependencies for geometry.py: {', '.join(missing)}. "
            "Install with `pip install -r requirements.txt`."
        )


def mask_to_multipolygon_4326(
    mask: np.ndarray,
    transform: "Affine",
    src_crs: str,
    simplify_tolerance: Optional[float] = None,
) -> Tuple[Optional["MultiPolygon"], Optional["MultiPolygon"]]:
    """
    Vectorize a boolean flood mask into a MultiPolygon.

    Returns a tuple of (geometry_in_EPSG_4326, geometry_in_source_crs).
    The source-CRS version is returned alongside so callers can compute
    accurate area (see calculate_area_km2) without re-reprojecting; it must
    NEVER be persisted to PostGIS directly (see module docstring).

    If the mask has no True pixels, returns (None, None).
    """
    _require_deps()

    if not np.any(mask):
        return None, None

    # rasterio.features.shapes vectorizes connected regions of equal value.
    # We only keep polygons where value == 1 (i.e. mask == True).
    mask_uint8 = mask.astype("uint8")
    polygons = []
    for geom_dict, value in rasterio_shapes(mask_uint8, mask=mask, transform=transform):
        if value == 1:
            polygons.append(shape(geom_dict))

    if not polygons:
        return None, None

    merged = unary_union(polygons)

    # Pixel-adjacency rasterization can occasionally produce technically
    # invalid geometry (e.g. self-touching rings at diagonal pixel corners).
    # Repair invalid polygon topology using Shapely's buffer(0) technique and
    # revalidate the result. buffer(0) is not guaranteed to be a no-op on an
    # already-valid geometry's exact vertex layout (it can, in principle,
    # nudge coordinates during the repair), so it's applied only when
    # `merged.is_valid` is already False, and the result is re-checked.
    if not merged.is_valid:
        merged = merged.buffer(0)
        if not merged.is_valid:
            raise ValueError(
                "Flood mask vectorization produced an invalid geometry that "
                "could not be repaired with buffer(0). Inspect the input mask."
            )

    if simplify_tolerance:
        simplified = merged.simplify(simplify_tolerance, preserve_topology=True)
        # preserve_topology=True should guarantee validity, but verify —
        # we'd rather keep the unsimplified (larger) geometry than silently
        # persist a boundary that no longer matches the actual flood extent.
        if simplified.is_valid and not simplified.is_empty:
            merged = simplified

    # Normalize to MultiPolygon (schema requires geometry(MultiPolygon, 4326))
    if isinstance(merged, Polygon):
        merged = MultiPolygon([merged])

    geom_source_crs = merged

    if src_crs == TARGET_CRS:
        geom_4326 = merged
    else:
        transformer = pyproj.Transformer.from_crs(src_crs, TARGET_CRS, always_xy=True)
        geom_4326 = shapely_transform(transformer.transform, merged)
        if isinstance(geom_4326, Polygon):
            geom_4326 = MultiPolygon([geom_4326])

    return geom_4326, geom_source_crs


def calculate_area_km2(geom, working_crs: str) -> float:
    """
    Compute area in km² for a geometry.

    If `working_crs` is already a projected (metres-based) CRS, area is
    computed directly. If it's geographic (e.g. EPSG:4326), the geometry is
    reprojected transiently to an equal-area projection (World Mollweide,
    ESRI:54009 — a standard, globally-valid equal-area projection, suitable
    regardless of the region's location) for accurate km² math, per
    DATA_FORMATS.md §1 ("Projected CRS is only acceptable transiently ... for
    calculations like accurate area").
    """
    _require_deps()
    if geom is None:
        return 0.0

    crs_obj = pyproj.CRS.from_user_input(working_crs)

    if crs_obj.is_geographic:
        # Reproject transiently to World Mollweide (equal-area) for area math.
        transformer = pyproj.Transformer.from_crs(
            crs_obj, "ESRI:54009", always_xy=True
        )
        equal_area_geom = shapely_transform(transformer.transform, geom)
        area_m2 = equal_area_geom.area
    else:
        # Already projected — but "projected" doesn't guarantee metres.
        # Verify the axis unit before trusting geom.area as square metres;
        # a small number of projected CRSs use US survey feet or other units.
        axis_units = {ax.unit_name.lower() for ax in crs_obj.axis_info}
        metre_aliases = {"metre", "meter"}
        if not axis_units & metre_aliases:
            raise ValueError(
                f"working_crs '{working_crs}' is projected but its unit is "
                f"{axis_units or 'unknown'}, not metres. calculate_area_km2() "
                "assumes metre-based projected CRSs; reproject to a metre-based "
                "CRS (e.g. an appropriate UTM zone) before calling this, or "
                "extend this function to handle the unit conversion explicitly."
            )
        area_m2 = geom.area

    return area_m2 / 1_000_000.0


def geometry_to_wkt(geom) -> Optional[str]:
    """Convenience helper: shapely geometry -> WKT string for ST_GeomFromText()."""
    return geom.wkt if geom is not None else None
