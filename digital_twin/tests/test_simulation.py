"""
tests/test_simulation.py — unit tests for the core flood mask/depth math.

Deliberately independent of rasterio/shapely/pyproj: compute_flood_mask(),
compute_flood_depth(), and the zero-inundation path of run_simulation() only
need numpy, so these tests run even in environments where the full
geospatial stack isn't installed yet (e.g. CI setup, a fresh clone before
`pip install -r requirements.txt`).
"""

import math

import numpy as np
import pytest

from digital_twin import simulation
from digital_twin.dem import DEMData


# ---------------------------------------------------------------------------
# compute_flood_mask
# ---------------------------------------------------------------------------

def test_flood_mask_basic():
    """elevation <= flood_level -> True, per ENGG_3.txt's basic prototype."""
    elevation = np.array([[1.0, 3.0], [2.0, 5.0]])
    mask = simulation.compute_flood_mask(elevation, flood_level=2.0)
    assert mask.tolist() == [[True, False], [True, False]]


def test_flood_mask_inclusive_boundary():
    """elevation exactly equal to flood_level counts as flooded (<=, not <)."""
    elevation = np.array([[2.0, 2.0001]])
    mask = simulation.compute_flood_mask(elevation, flood_level=2.0)
    assert mask.tolist() == [[True, False]]


def test_flood_mask_excludes_nan():
    """NoData (NaN) pixels must NEVER be marked as flooded, at any flood level."""
    elevation = np.array([[np.nan, 0.0], [np.nan, 100.0]])
    mask = simulation.compute_flood_mask(elevation, flood_level=1000.0)
    # Even at an absurdly high flood level, NaN pixels stay False.
    assert mask.tolist() == [[False, True], [False, True]]


def test_flood_mask_zero_inundation():
    """flood_level below every elevation -> mask is entirely False."""
    elevation = np.array([[5.0, 6.0], [7.0, 8.0]])
    mask = simulation.compute_flood_mask(elevation, flood_level=0.0)
    assert not mask.any()


def test_flood_mask_full_inundation():
    """flood_level above every elevation -> every valid pixel is flooded."""
    elevation = np.array([[5.0, 6.0], [7.0, 8.0]])
    mask = simulation.compute_flood_mask(elevation, flood_level=100.0)
    assert mask.all()


@pytest.mark.parametrize("bad_level", [float("nan"), float("inf"), float("-inf")])
def test_flood_mask_rejects_non_finite_level(bad_level):
    elevation = np.array([[1.0, 2.0]])
    with pytest.raises(ValueError):
        simulation.compute_flood_mask(elevation, flood_level=bad_level)


# ---------------------------------------------------------------------------
# compute_flood_depth
# ---------------------------------------------------------------------------

def test_flood_depth_basic():
    elevation = np.array([[1.0, 3.0]])
    depth = simulation.compute_flood_depth(elevation, flood_level=2.0)
    assert np.allclose(depth, [[1.0, 0.0]])


def test_flood_depth_never_negative():
    """Depth must be clipped to >= 0, never negative, per ENGG_3.txt."""
    elevation = np.array([[10.0, 20.0, 30.0]])
    depth = simulation.compute_flood_depth(elevation, flood_level=15.0)
    assert (depth >= 0).all()
    assert np.allclose(depth, [[5.0, 0.0, 0.0]])


def test_flood_depth_nan_stays_zero_not_nan():
    """NoData pixels get depth 0 (not NaN, not negative) — never inundation."""
    elevation = np.array([[np.nan, 1.0]])
    depth = simulation.compute_flood_depth(elevation, flood_level=5.0)
    assert not np.isnan(depth[0, 0])
    assert depth[0, 0] == 0.0
    assert depth[0, 1] == 4.0


@pytest.mark.parametrize("bad_level", [float("nan"), float("inf")])
def test_flood_depth_rejects_non_finite_level(bad_level):
    elevation = np.array([[1.0, 2.0]])
    with pytest.raises(ValueError):
        simulation.compute_flood_depth(elevation, flood_level=bad_level)


def test_flood_level_negative_is_allowed():
    """
    No arbitrary flood_level >= 0 restriction: the project has no stated
    vertical-datum contract, so negative flood levels relative to some local
    benchmark are not, by themselves, invalid.
    """
    elevation = np.array([[-5.0, -1.0, 3.0]])
    mask = simulation.compute_flood_mask(elevation, flood_level=-2.0)
    assert mask.tolist() == [[True, False, False]]


# ---------------------------------------------------------------------------
# Pixel counting
# ---------------------------------------------------------------------------

def test_flooded_and_valid_pixel_counts():
    elevation = np.array([[1.0, 2.0, np.nan], [3.0, np.nan, 5.0]])
    mask = simulation.compute_flood_mask(elevation, flood_level=2.0)
    valid_count = int(np.sum(~np.isnan(elevation)))
    flooded_count = int(np.sum(mask))
    assert valid_count == 4          # 4 non-NaN cells
    assert flooded_count == 2        # elevation 1.0 and 2.0 are <= 2.0


# ---------------------------------------------------------------------------
# run_simulation — zero-inundation path only (no rasterio/shapely required,
# since SimulationResult short-circuits before any geometry work when the
# mask is entirely False).
# ---------------------------------------------------------------------------

def _fake_dem(elevation: np.ndarray) -> DEMData:
    """Build a minimal DEMData for tests that never reach geometry.py."""
    return DEMData(
        elevation=elevation,
        transform=None,       # unused on the zero-inundation early-return path
        crs="EPSG:4326",
        nodata=None,
        width=elevation.shape[1],
        height=elevation.shape[0],
        pixel_size_x=1.0,
        pixel_size_y=1.0,
    )


def test_run_simulation_zero_inundation_short_circuits():
    """
    When nothing is flooded, run_simulation() must return a valid
    SimulationResult without needing rasterio/shapely at all — this is the
    "zero-flood scenario" the review explicitly requires to work.
    """
    dem = _fake_dem(np.array([[10.0, 20.0], [30.0, 40.0]]))
    result = simulation.run_simulation(dem, flood_level=0.0)

    assert result.flooded_area_km2 == 0.0
    assert result.result_geometry_geojson is None
    assert result.result_geometry_wkt is None
    assert result.flooded_pixel_count == 0
    assert result.valid_pixel_count == 4


def test_run_simulation_rejects_invalid_flood_level():
    dem = _fake_dem(np.array([[1.0, 2.0]]))
    with pytest.raises(ValueError):
        simulation.run_simulation(dem, flood_level=math.nan)
