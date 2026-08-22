"""
tests/test_geometry.py — raster-to-vector conversion, CRS reprojection, and
area calculation correctness, including the required invariant:

    area(2.5m) <= area(3.0m) <= area(3.5m)

Requires rasterio + shapely + pyproj; skipped cleanly if any are missing.
"""

import pytest

rasterio = pytest.importorskip("rasterio")
shapely = pytest.importorskip("shapely")
pytest.importorskip("pyproj")

from shapely.geometry import MultiPolygon, Polygon, shape

from digital_twin import dem as dem_mod
from digital_twin import geometry, simulation


# ---------------------------------------------------------------------------
# End-to-end: DEM -> simulation -> geometry, on the sloped fixture DEM
# ---------------------------------------------------------------------------

def test_area_monotonic_across_increasing_flood_levels(sloped_dem_path):
    """
    Required invariant: area(2.5m) <= area(3.0m) <= area(3.5m).
    On the fixture's monotonic row-ramp DEM, this should in fact be strict.
    """
    d = dem_mod.load_dem(sloped_dem_path)
    results = [simulation.run_simulation(d, level) for level in (2.5, 3.0, 3.5)]
    areas = [r.flooded_area_km2 for r in results]

    assert areas[0] <= areas[1] <= areas[2]
    assert areas[0] < areas[1] < areas[2]  # strict on this particular DEM


def test_result_geometry_is_multipolygon(sloped_dem_path):
    d = dem_mod.load_dem(sloped_dem_path)
    result = simulation.run_simulation(d, flood_level=3.0)
    assert result.result_geometry_geojson is not None
    assert result.result_geometry_geojson["type"] == "MultiPolygon"


def test_result_geometry_is_valid_and_nonempty(sloped_dem_path):
    d = dem_mod.load_dem(sloped_dem_path)
    result = simulation.run_simulation(d, flood_level=3.0)
    geom = shape(result.result_geometry_geojson)
    assert geom.is_valid
    assert not geom.is_empty


def test_result_geometry_coordinates_in_lon_lat_range(sloped_dem_path):
    """
    Persisted geometry must be EPSG:4326 — verify the coordinates actually
    look like lon/lat (not raw UTM easting/northing, which would be off by
    ~5 orders of magnitude and outside these bounds).
    """
    d = dem_mod.load_dem(sloped_dem_path)
    result = simulation.run_simulation(d, flood_level=3.0)

    def flatten(coords):
        if isinstance(coords[0], (int, float)):
            yield coords
        else:
            for sub in coords:
                yield from flatten(sub)

    for x, y in flatten(result.result_geometry_geojson["coordinates"]):
        assert -180.0 <= x <= 180.0
        assert -90.0 <= y <= 90.0


# ---------------------------------------------------------------------------
# mask_to_multipolygon_4326 — unit-level, synthetic masks
# ---------------------------------------------------------------------------

def test_mask_to_multipolygon_normalizes_single_blob_to_multipolygon():
    import numpy as np
    from rasterio.transform import from_origin

    mask = np.zeros((10, 10), dtype=bool)
    mask[3:6, 3:6] = True  # one connected 3x3 blob -> vectorizes to one Polygon
    transform = from_origin(500_000, 2_000_050, 5, 5)

    geom_4326, geom_source = geometry.mask_to_multipolygon_4326(
        mask, transform, src_crs="EPSG:32644"
    )
    assert isinstance(geom_4326, MultiPolygon)
    assert isinstance(geom_source, MultiPolygon)
    assert geom_4326.is_valid
    assert geom_source.is_valid


def test_mask_to_multipolygon_empty_mask_returns_none():
    import numpy as np
    from rasterio.transform import from_origin

    mask = np.zeros((10, 10), dtype=bool)
    transform = from_origin(500_000, 2_000_050, 5, 5)

    geom_4326, geom_source = geometry.mask_to_multipolygon_4326(
        mask, transform, src_crs="EPSG:32644"
    )
    assert geom_4326 is None
    assert geom_source is None


def test_mask_to_multipolygon_two_disjoint_blobs():
    """Two disconnected flooded regions should still merge into one MultiPolygon."""
    import numpy as np
    from rasterio.transform import from_origin

    mask = np.zeros((20, 20), dtype=bool)
    mask[1:3, 1:3] = True
    mask[15:18, 15:18] = True
    transform = from_origin(500_000, 2_000_100, 5, 5)

    geom_4326, _ = geometry.mask_to_multipolygon_4326(
        mask, transform, src_crs="EPSG:32644"
    )
    assert isinstance(geom_4326, MultiPolygon)
    assert len(geom_4326.geoms) >= 1  # unary_union may or may not merge disjoint blobs
    assert geom_4326.is_valid


# ---------------------------------------------------------------------------
# calculate_area_km2 — known-shape and unit-safety checks
# ---------------------------------------------------------------------------

def test_calculate_area_km2_known_square_metre_crs():
    """A 1000m x 1000m square in a metre-based projected CRS is exactly 1 km^2."""
    square = Polygon([(0, 0), (1000, 0), (1000, 1000), (0, 1000)])
    mp = MultiPolygon([square])
    area = geometry.calculate_area_km2(mp, working_crs="EPSG:32644")
    assert area == pytest.approx(1.0, rel=1e-6)


def test_calculate_area_km2_none_geometry_is_zero():
    assert geometry.calculate_area_km2(None, working_crs="EPSG:32644") == 0.0


def test_calculate_area_km2_rejects_non_metre_projected_crs():
    """
    A projected CRS whose unit isn't metres (e.g. US survey feet) must be
    rejected rather than silently treated as metres — this would otherwise
    inflate/deflate flooded_area by ~3.28^2x without any visible error.
    """
    square = Polygon([(0, 0), (1000, 0), (1000, 1000), (0, 1000)])
    mp = MultiPolygon([square])
    with pytest.raises(ValueError, match="not metres"):
        geometry.calculate_area_km2(mp, working_crs="EPSG:2229")  # CA State Plane, US ft


def test_calculate_area_km2_geographic_crs_reprojects_transiently():
    """
    A small square defined directly in EPSG:4326 degrees should be
    reprojected to an equal-area CRS internally, not have geom.area (in
    square degrees) misread as square metres.
    """
    # ~0.01 degree square near the equator, roughly 1.1km per side
    square = Polygon([(0, 0), (0.01, 0), (0.01, 0.01), (0, 0.01)])
    mp = MultiPolygon([square])
    area = geometry.calculate_area_km2(mp, working_crs="EPSG:4326")
    # Sanity range, not exact: a naive (wrong) treatment of degrees as
    # metres would produce an area around 1e-10 km^2, wildly off from this.
    assert 0.5 < area < 3.0


# ---------------------------------------------------------------------------
# geometry_to_wkt
# ---------------------------------------------------------------------------

def test_geometry_to_wkt_none_returns_none():
    assert geometry.geometry_to_wkt(None) is None


def test_geometry_to_wkt_roundtrip():
    square = Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])
    mp = MultiPolygon([square])
    wkt = geometry.geometry_to_wkt(mp)
    assert wkt is not None
    assert wkt.upper().startswith("MULTIPOLYGON")
