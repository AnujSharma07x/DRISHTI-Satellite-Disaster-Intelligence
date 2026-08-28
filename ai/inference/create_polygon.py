import json
from pathlib import Path

import rasterio
from rasterio.features import shapes
from shapely.geometry import shape, mapping
from shapely.ops import unary_union
import pyproj


MASK = r"ai\real_demo_output\flood_mask.tif"
OUTPUT = Path(r"ai\real_demo_output")


with rasterio.open(MASK) as src:

    mask = src.read(1)
    transform = src.transform
    crs = src.crs

    print("CRS:", crs)
    print("Flood pixels:", int(mask.sum()))

    geometries = []

    for geom, value in shapes(
        mask,
        mask=(mask == 1),
        transform=transform
    ):
        if value == 1:
            geometries.append(shape(geom))


if not geometries:
    print("No flood polygon found.")
    raise SystemExit


# Merge flood regions
merged = unary_union(geometries)


# Calculate area using equal-area projection
project = pyproj.Transformer.from_crs(
    crs,
    "EPSG:6933",
    always_xy=True
).transform

from shapely.ops import transform

area_m2 = transform(project, merged).area
area_km2 = area_m2 / 1_000_000


# Convert polygon to WGS84 for web maps
to_wgs84 = pyproj.Transformer.from_crs(
    crs,
    "EPSG:4326",
    always_xy=True
).transform

web_geometry = transform(to_wgs84, merged)


geojson = {
    "type": "Feature",
    "properties": {
        "flood_area_km2": round(area_km2, 4),
        "flood_pixels": int(mask.sum())
    },
    "geometry": mapping(web_geometry)
}


output_file = OUTPUT / "flood_polygon.geojson"

with open(output_file, "w") as f:
    json.dump(geojson, f, indent=2)


print("=" * 60)
print("FLOOD POLYGON GENERATED")
print("Flood pixels:", int(mask.sum()))
print("Flood area:", round(area_km2, 4), "km²")
print("GeoJSON:", output_file)
print("=" * 60)