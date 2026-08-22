"""
simulation.py — Flood scenario simulation (Engineer 3).

Implements the basic scenario-based inundation model specified in ENGG_3.txt:

    if elevation <= flood_level:
        potentially_flooded = True
    else:
        potentially_flooded = False

    flood_depth = flood_level - elevation   (only positive values are inundation)

IMPORTANT (per ENGG_3.txt "IMPORTANT" section):
This is a scenario-based *potential* inundation model, NOT an accurate
hydrodynamic flood prediction. It answers the question:
"If water reaches this elevation, which areas could potentially be affected?"

It does not model water flow, connectivity to a water source, infiltration,
drainage, or time. A low-elevation pixel that is hydrologically disconnected
from the flood source will still be marked as "potentially flooded" — this is
a known and accepted MVP simplification (see COMMON.txt constraint #5:
"Do NOT build a full hydrodynamic flood model").
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

import numpy as np

from .dem import DEMData, load_dem
from .geometry import mask_to_multipolygon_4326, calculate_area_km2


@dataclass
class SimulationResult:
    """Result of a single flood-level scenario simulation, pre-persistence."""

    flood_level: float                     # metres
    flood_mask: np.ndarray                 # boolean array, True = potentially flooded
    flood_depth: np.ndarray                # float array, metres, 0 where not flooded
    flooded_area_km2: float
    result_geometry_geojson: Optional[dict]  # MultiPolygon, EPSG:4326 (per DATA_FORMATS.md §1)
    result_geometry_wkt: Optional[str]       # convenience form for ST_GeomFromText in impact.py
    valid_pixel_count: int
    flooded_pixel_count: int


def _validate_flood_level(flood_level: float) -> None:
    """
    Reject non-finite flood levels (NaN/inf) — these can't mean anything as
    a water elevation and would otherwise silently propagate into a mask
    that's all-True or all-False.

    Deliberately does NOT enforce flood_level >= 0: the project has no
    stated vertical-datum contract (see dem.py docstring / README.md
    "Documented assumptions"), so a legitimate DEM referenced to a local
    benchmark could have "ground" below 0. Adding that restriction would be
    an unjustified guess, not a correctness fix.
    """
    if flood_level is None or not np.isfinite(flood_level):
        raise ValueError(
            f"flood_level must be a finite number (metres), got: {flood_level!r}"
        )


def compute_flood_mask(elevation: np.ndarray, flood_level: float) -> np.ndarray:
    """
    Boolean mask of potentially-flooded pixels.

    elevation <= flood_level -> True (potentially flooded)
    NaN (nodata) pixels are always False — we never guess for missing terrain data.
    """
    _validate_flood_level(flood_level)
    valid = ~np.isnan(elevation)
    mask = np.zeros_like(elevation, dtype=bool)
    mask[valid] = elevation[valid] <= flood_level
    return mask


def compute_flood_depth(elevation: np.ndarray, flood_level: float) -> np.ndarray:
    """
    Flood depth in metres: flood_level - elevation, clipped to >= 0.

    Only positive values represent inundation (per ENGG_3.txt). Depth is 0
    (not negative) for dry or nodata pixels — depth is only meaningful where
    compute_flood_mask() is True; callers should mask accordingly for display.
    """
    _validate_flood_level(flood_level)
    valid = ~np.isnan(elevation)
    depth = np.zeros_like(elevation, dtype="float64")
    depth[valid] = flood_level - elevation[valid]
    depth = np.clip(depth, a_min=0.0, a_max=None)
    return depth


def run_simulation(
    dem: DEMData,
    flood_level: float,
    simplify_tolerance: Optional[float] = None,
) -> SimulationResult:
    """
    Run one flood-level scenario against an already-loaded DEM.

    Parameters
    ----------
    dem : DEMData
        Output of dem.load_dem().
    flood_level : float
        Flood level in metres (same vertical datum as the DEM).
    simplify_tolerance : float, optional
        Optional polygon simplification tolerance (in the DEM's working CRS
        units) to keep result_geometry lightweight for the dashboard/API.

    Returns
    -------
    SimulationResult
    """
    mask = compute_flood_mask(dem.elevation, flood_level)
    depth = compute_flood_depth(dem.elevation, flood_level)

    valid_pixel_count = int(np.sum(~np.isnan(dem.elevation)))
    flooded_pixel_count = int(np.sum(mask))

    if flooded_pixel_count == 0:
        # No inundation at this flood level — valid outcome, not an error.
        return SimulationResult(
            flood_level=flood_level,
            flood_mask=mask,
            flood_depth=depth,
            flooded_area_km2=0.0,
            result_geometry_geojson=None,
            result_geometry_wkt=None,
            valid_pixel_count=valid_pixel_count,
            flooded_pixel_count=0,
        )

    geom_4326, geom_working_crs = mask_to_multipolygon_4326(
        mask=mask,
        transform=dem.transform,
        src_crs=dem.crs,
        simplify_tolerance=simplify_tolerance,
    )
    area_km2 = calculate_area_km2(geom_working_crs, working_crs=dem.crs)

    return SimulationResult(
        flood_level=flood_level,
        flood_mask=mask,
        flood_depth=depth,
        flooded_area_km2=area_km2,
        result_geometry_geojson=geom_4326.__geo_interface__ if geom_4326 else None,
        result_geometry_wkt=geom_4326.wkt if geom_4326 else None,
        valid_pixel_count=valid_pixel_count,
        flooded_pixel_count=flooded_pixel_count,
    )


def run_scenarios(
    dem_path: str,
    flood_levels: List[float],
    simplify_tolerance: Optional[float] = None,
) -> List[SimulationResult]:
    """
    Convenience wrapper: load a DEM once and run several flood-level scenarios
    against it (e.g. the 2.5m / 3.0m / 3.5m example set in ENGG_3.txt).

    Loading the DEM once and reusing it avoids repeated disk/Storage reads —
    important for the 10-day MVP timeline where the "SIMULATE" slider in the
    dashboard may be dragged through several values in a demo.
    """
    dem = load_dem(dem_path)
    return [run_simulation(dem, level, simplify_tolerance) for level in flood_levels]
