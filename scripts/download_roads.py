import osmnx as ox

PLACE = "Morigaon, Assam, India"

GRAPH_OUTPUT = "data/roads/morigaon_road_network.graphml"
GPKG_OUTPUT = "data/roads/morigaon_roads.gpkg"

print(f"Downloading road network for: {PLACE}")
print("This may take a while...")

G = ox.graph_from_place(
    PLACE,
    network_type="drive",
    simplify=True
)

print(f"Downloaded {len(G.nodes)} road nodes and {len(G.edges)} road segments.")

# Save graph for routing
ox.save_graphml(G, GRAPH_OUTPUT)

# Convert to GeoDataFrames
nodes, edges = ox.graph_to_gdfs(G)

# Save road network for GIS processing
edges.to_file(
    GPKG_OUTPUT,
    layer="roads",
    driver="GPKG"
)

print("\nSUCCESS!")
print(f"GraphML: {GRAPH_OUTPUT}")
print(f"GeoPackage: {GPKG_OUTPUT}")