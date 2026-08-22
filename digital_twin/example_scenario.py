"""
example_scenario.py — End-to-end usage example for the digital_twin module.

Demonstrates the flow ENGG_3.txt asks for under "SCENARIOS":

    Scenario 1: 2.5m
    Scenario 2: 3.0m
    Scenario 3: 3.5m

Run standalone (no live Supabase connection needed) to sanity-check the DEM
-> mask -> polygon -> area pipeline:

    python -m digital_twin.example_scenario /path/to/region_dem.tif

Add a region_id as a second argument to run the full pipeline instead
(impact calculation + persistence), which does then require a live DB
connection — see run_with_db() below:

    DATABASE_URL="..." python -m digital_twin.example_scenario \
        /path/to/region_dem.tif <region_id>

If a psycopg2-style connection is available (e.g. via a DATABASE_URL env var
pointing at the Supabase Postgres instance), impact numbers and persistence
are also demonstrated — see `run_with_db()` below. Nothing in this file
hardcodes credentials; the connection string is only ever read from the
environment (COMMON.txt #11).
"""

from __future__ import annotations

import os
import sys

from . import dem as dem_mod
from . import simulation, impact


SCENARIO_LEVELS = [2.5, 3.0, 3.5]  # metres, matches ENGG_3.txt example


def run_simulation_only(dem_path: str) -> None:
    """Run the three example scenarios and print results, no DB required."""
    results = simulation.run_scenarios(dem_path, SCENARIO_LEVELS)
    for r in results:
        print(
            f"flood_level={r.flood_level}m  "
            f"flooded_area={r.flooded_area_km2:.3f} km^2  "
            f"flooded_pixels={r.flooded_pixel_count}/{r.valid_pixel_count}"
        )


def run_with_db(dem_path: str, region_id: str) -> None:
    """
    Full pipeline including impact calculation and persistence.

    Requires:
        - DATABASE_URL env var (Supabase Postgres connection string)
        - psycopg2 installed
    """
    import psycopg2  # local import: optional dependency, only needed for this path

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError(
            "Set DATABASE_URL to a Supabase Postgres connection string to run "
            "the full example (impact calculation + persistence). Never "
            "hardcode this value in source."
        )

    dem_data = dem_mod.load_dem(dem_path)
    conn = psycopg2.connect(database_url)
    try:
        buildings_exists = impact.buildings_table_exists(conn)
        for level in SCENARIO_LEVELS:
            sim = simulation.run_simulation(dem_data, level)
            if sim.result_geometry_wkt is None:
                print(f"flood_level={level}m -> no inundation, skipping impact calc")
                continue

            impact_result = impact.calculate_all_impacts(
                conn, region_id, sim.result_geometry_wkt, buildings_exists=buildings_exists
            )
            scenario_id = impact.save_simulation_scenario(
                conn,
                region_id=region_id,
                scenario_name=f"Scenario {level}m",
                flood_level=level,
                flooded_area_km2=sim.flooded_area_km2,
                impact=impact_result,
                result_geometry_wkt=sim.result_geometry_wkt,
            )
            print(
                f"Saved scenario {scenario_id}: level={level}m "
                f"area={sim.flooded_area_km2:.2f}km^2 "
                f"population_affected={impact_result.population_affected} "
                f"roads_affected_count={impact_result.roads_affected_count} "
                f"hospitals_affected={impact_result.hospitals_affected}"
            )
    finally:
        conn.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m digital_twin.example_scenario <dem_path> [region_id]")
        sys.exit(1)

    dem_path_arg = sys.argv[1]
    if len(sys.argv) >= 3:
        run_with_db(dem_path_arg, sys.argv[2])
    else:
        run_simulation_only(dem_path_arg)
