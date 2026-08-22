"""
tests/test_dem.py — DEM loading correctness, including the missing-CRS
critical fix from the code review.

Requires rasterio; skipped cleanly (not failed) if it isn't installed, via
pytest.importorskip.
"""

import numpy as np
import pytest

rasterio = pytest.importorskip("rasterio")

from digital_twin import dem as dem_mod


def test_load_dem_basic_shape_and_georeferencing(sloped_dem_path):
    d = dem_mod.load_dem(sloped_dem_path)
    assert d.width == 20
    assert d.height == 20
    assert d.pixel_size_x == pytest.approx(5.0)
    assert d.pixel_size_y == pytest.approx(5.0)
    assert "32644" in d.crs


def test_load_dem_elevation_values_preserved(sloped_dem_path):
    d = dem_mod.load_dem(sloped_dem_path)
    # Row 0 should be ~0.0m, row 10 should be ~5.0m (row_step=0.5 in fixture)
    assert d.elevation[0, 0] == pytest.approx(0.0)
    assert d.elevation[10, 0] == pytest.approx(5.0)


def test_load_dem_missing_crs_raises_not_defaults(sloped_dem_no_crs_path):
    """
    Critical-fix regression test: a DEM with no embedded CRS must raise,
    never silently default to EPSG:4326 or any other CRS.
    """
    with pytest.raises(ValueError, match="no embedded CRS"):
        dem_mod.load_dem(sloped_dem_no_crs_path)


def test_load_dem_missing_crs_accepts_explicit_override(sloped_dem_no_crs_path):
    d = dem_mod.load_dem(sloped_dem_no_crs_path, crs_override="EPSG:32644")
    assert d.crs == "EPSG:32644"


def test_load_dem_all_nodata_raises_clear_error(all_nodata_dem_path):
    with pytest.raises(ValueError, match="zero valid"):
        dem_mod.load_dem(all_nodata_dem_path)


def test_load_dem_file_not_found():
    with pytest.raises(FileNotFoundError):
        dem_mod.load_dem("/definitely/not/a/real/path/dem.tif")


def test_load_dem_nodata_becomes_nan(partial_nodata_dem_path):
    d = dem_mod.load_dem(partial_nodata_dem_path)
    assert np.isnan(d.elevation[0, 0])
    assert np.isnan(d.elevation[5, 5])
    # A pixel that was NOT set to nodata should remain a real number
    assert not np.isnan(d.elevation[1, 1])


def test_dem_stats_ignores_nan(partial_nodata_dem_path):
    d = dem_mod.load_dem(partial_nodata_dem_path)
    stats = dem_mod.dem_stats(d)
    assert stats["valid_pixels"] == d.elevation.size - 2  # 2 nodata pixels
    assert stats["min"] is not None and not np.isnan(stats["min"])


def test_cleanup_local_file_removes_file(sloped_dem_path):
    import os

    assert os.path.exists(sloped_dem_path)
    dem_mod.cleanup_local_file(sloped_dem_path)
    assert not os.path.exists(sloped_dem_path)
