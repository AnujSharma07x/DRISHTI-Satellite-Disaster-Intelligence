"""
tests/conftest.py — shared fixtures for building small synthetic DEM GeoTIFFs
in-memory/on-disk, so geometry/dem tests don't depend on a real regional DEM.

All fixtures use pytest.importorskip("rasterio") so the whole test session
still collects (and the pure-math tests in test_simulation.py still run)
in an environment where the geospatial stack isn't installed yet.
"""

import numpy as np
import pytest

# Roughly central-meridian-ish UTM 44N coordinates over India, so the
# synthetic DEM reprojects to plausible lon/lat rather than a mathematically
# valid but geographically meaningless point.
_ORIGIN_EASTING = 500_000.0
_ORIGIN_NORTHING = 2_000_000.0
_PIXEL_SIZE = 5.0  # metres


def _make_sloped_elevation(rows=20, cols=20, row_step=0.5):
    """
    elevation[i, j] = i * row_step — a monotonic ramp along rows, flat along
    columns. Used for the area-monotonicity test: as flood_level increases,
    strictly more rows (and therefore strictly more area) become flooded.
    """
    ramp = np.arange(rows, dtype="float64") * row_step
    return np.tile(ramp.reshape(-1, 1), (1, cols))


def _write_dem(path, elevation, crs, nodata=-9999.0):
    import rasterio
    from rasterio.transform import from_origin

    transform = from_origin(
        _ORIGIN_EASTING,
        _ORIGIN_NORTHING + elevation.shape[0] * _PIXEL_SIZE,
        _PIXEL_SIZE,
        _PIXEL_SIZE,
    )
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=elevation.shape[0],
        width=elevation.shape[1],
        count=1,
        dtype="float64",
        crs=crs,
        transform=transform,
        nodata=nodata,
    ) as dst:
        dst.write(elevation, 1)
    return transform


@pytest.fixture
def sloped_dem_path(tmp_path):
    """A 20x20 sloped DEM (0.0m to 9.5m), projected CRS (EPSG:32644, metres)."""
    pytest.importorskip("rasterio")
    elevation = _make_sloped_elevation()
    path = tmp_path / "sloped_dem.tif"
    _write_dem(path, elevation, crs="EPSG:32644")
    return str(path)


@pytest.fixture
def sloped_dem_no_crs_path(tmp_path):
    """Same ramp DEM, but with no embedded CRS — for the missing-CRS test."""
    pytest.importorskip("rasterio")
    elevation = _make_sloped_elevation()
    path = tmp_path / "no_crs_dem.tif"
    _write_dem(path, elevation, crs=None)
    return str(path)


@pytest.fixture
def all_nodata_dem_path(tmp_path):
    """A DEM where every pixel is NoData — for the empty-DEM test."""
    pytest.importorskip("rasterio")
    nodata_val = -9999.0
    elevation = np.full((10, 10), nodata_val, dtype="float64")
    path = tmp_path / "empty_dem.tif"
    _write_dem(path, elevation, crs="EPSG:32644", nodata=nodata_val)
    return str(path)


@pytest.fixture
def partial_nodata_dem_path(tmp_path):
    """A ramp DEM with a couple of pixels explicitly set to NoData."""
    pytest.importorskip("rasterio")
    nodata_val = -9999.0
    elevation = _make_sloped_elevation(rows=10, cols=10)
    elevation[0, 0] = nodata_val
    elevation[5, 5] = nodata_val
    path = tmp_path / "partial_nodata_dem.tif"
    _write_dem(path, elevation, crs="EPSG:32644", nodata=nodata_val)
    return str(path)
