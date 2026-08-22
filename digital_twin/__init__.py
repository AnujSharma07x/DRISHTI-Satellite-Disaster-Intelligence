"""
digital_twin — Engineer 3's module: Geospatial Digital Twin, DEM processing,
and flood scenario simulation for DRISHTI.

Public API:
    dem.load_dem(path) -> DEMData
    simulation.run_simulation(dem, flood_level) -> SimulationResult
    simulation.run_scenarios(dem_path, flood_levels) -> list[SimulationResult]
    geometry.mask_to_multipolygon_4326(...) -> (geom_4326, geom_source_crs)
    geometry.calculate_area_km2(geom, working_crs) -> float
    impact.calculate_all_impacts(conn, region_id, flood_wkt) -> ImpactResult
    impact.save_simulation_scenario(conn, ...) -> scenario_id

See README.md for the end-to-end usage example.
"""

from . import dem, simulation, geometry, impact

__all__ = ["dem", "simulation", "geometry", "impact"]
