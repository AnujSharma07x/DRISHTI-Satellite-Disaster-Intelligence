import geopandas as gpd
import osmnx as ox
from pathlib import Path

AOI = "data/aoi/demo_aoi.geojson"
OUTPUT = Path("data/roads")
OUTPUT.mkdir(parents=True, exist_ok=True)

print("Loading DRISHTI demo AOI...")

aoi = gpd.read_file(AOI).to_crs("EPSG:4326")

polygon = aoi.geometry.iloc[0]

print("Downloading road network...")
print("This may take a few minutes.")

G = ox.graph_from_polygon(
    polygon,
    network_type="drive",
    simplify=True
)

print("Road network downloaded.")
print("Nodes:", len(G.nodes))
print("Edges:", len(G.edges))

ox.save_graphml(
    G,
    filepath=OUTPUT / "guwahati_demo_roads.graphml"
)

edges = ox.graph_to_gdfs(G, nodes=False)

edges.to_file(
    OUTPUT / "guwahati_demo_roads.geojson",
    driver="GeoJSON"
)

print("Saved:")
print(OUTPUT / "guwahati_demo_roads.graphml")
print(OUTPUT / "guwahati_demo_roads.geojson")