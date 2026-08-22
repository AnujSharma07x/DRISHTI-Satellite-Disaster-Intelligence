"""
DRISHTI — Engineer 4
Impact / Priority-Zone Module

Takes risk-scored zones (output of risk_engine.assess(), one per
region/sub-area or per simulation scenario) and produces a ranked list of
priority zones for emergency response, per the brief's rule:

    Prioritize based on:
    1. High flood depth
    2. High population
    3. Critical infrastructure
    4. Poor accessibility

This module does NOT recompute risk — it consumes risk_engine output and
adds ranking / selection logic on top, so risk scoring stays in one place
(risk_engine.py) as the single source of truth.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

# Support both:
#   - running/importing this file directly from inside risk/ (flat scripts,
#     as used by the standalone `python3 impact.py` demo below), and
#   - importing it as a package from the project root, e.g.
#     `from risk.impact import prioritize_zones` (FastAPI backend).
try:  # pragma: no cover - import-path shim, not business logic
    from .risk_engine import RiskLevel, ScenarioImpact, assess
except ImportError:  # pragma: no cover
    from risk_engine import RiskLevel, ScenarioImpact, assess


@dataclass
class ZoneCandidate:
    """A candidate priority zone: a named area tied to one simulated
    scenario/impact. `zone_id` should map to a region/geometry the
    frontend can highlight on the map (owned by Engineer 1's schema —
    typically a risk_zones.id or a named sub-area within region_id).

    `geometry` (Fix #3, integration round): optional GeoJSON-compatible
    geometry (e.g. a Polygon/MultiPolygon) for this zone. Engineer 4
    does NOT compute, simulate, or invent this geometry — it is supplied
    by the caller (Engineer 3's flood-extent output / Engineer 1's
    PostGIS `risk_zones.geometry` column) and passed straight through so
    downstream consumers (the dashboard map, the routing module's origin
    derivation — see routing/emergency_route.py::zone_centroid) have
    access to it without this module reaching into PostGIS itself.
    """

    zone_id: str
    zone_name: str
    impact: ScenarioImpact
    geometry: Optional[dict] = None


# FIX (priority-zone ordering): the risk score — which already blends
# flood severity, population exposure, infrastructure importance and
# accessibility per the weighted formula in risk_engine.py — is the
# PRIMARY ranking criterion. The individual components are only used as
# deterministic tie-breakers when two zones land on the same risk score.
#
# Previous bug: this function compared flood_level first, which meant a
# zone with a deeper flood but much lower population/risk could outrank
# a genuinely higher-risk zone purely because of lexicographic ordering
# (e.g. 4.0m flood / 500 people/24.3 risk incorrectly beat 3.0m flood /
# 50,000 people/48.0 risk). Sorting by risk_score first fixes this.
def _rank_key(candidate: ZoneCandidate, result: dict):
    impact = candidate.impact
    accessibility_score = result["breakdown"]["accessibility_score"]
    return (
        result["risk_score"],                                   # 1. PRIMARY: risk score
        impact.flood_level,                                      # 2. tie-break: flood depth
        impact.population_affected,                              # 3. tie-break: population
        impact.hospitals_affected
        + (impact.critical_infrastructure_affected or 0),        # 4. tie-break: critical infra
        accessibility_score,                                      # 5. tie-break: accessibility
    )


def prioritize_zones(
    candidates: List[ZoneCandidate], top_n: Optional[int] = None
) -> List[dict]:
    """Returns zones ranked most-urgent first.

    Each returned dict merges the risk_engine assessment with zone
    identity, ready to feed both the dashboard's priority list and the
    routing module (which needs to know WHERE to send help first).
    """
    scored = []
    for c in candidates:
        result = assess(c.impact)
        scored.append((c, result))

    scored.sort(
        key=lambda pair: _rank_key(pair[0], pair[1]),
        reverse=True,
    )

    ranked = []
    for rank, (candidate, result) in enumerate(scored, start=1):
        ranked.append(
            {
                "rank": rank,
                "zone_id": candidate.zone_id,
                "zone_name": candidate.zone_name,
                "scenario_id": candidate.impact.scenario_id,
                "risk_level": result["risk_level"],
                "risk_score": result["risk_score"],
                "flood_level": candidate.impact.flood_level,
                "population_affected": candidate.impact.population_affected,
                "hospitals_affected": candidate.impact.hospitals_affected,
                "roads_affected_km": candidate.impact.roads_affected_km,
                "affected_road_segments": candidate.impact.affected_road_segments,
                "accessibility_score": result["breakdown"]["accessibility_score"],
                "accessibility_fallback_used": result["accessibility_fallback_used"],
                # Fix #3: pass-through only — geometry is supplied by the
                # caller (Engineer 3 / PostGIS), never invented here.
                "geometry": candidate.geometry,
            }
        )

    if top_n is not None:
        ranked = ranked[:top_n]
    return ranked


def critical_zones_only(candidates: List[ZoneCandidate]) -> List[dict]:
    """Convenience filter: zones classified CRITICAL or VERY HIGH — the
    set the response module should act on first."""
    ranked = prioritize_zones(candidates)
    return [
        z
        for z in ranked
        if z["risk_level"] in (RiskLevel.CRITICAL.value, RiskLevel.VERY_HIGH.value)
    ]


def summarize_impact(candidates: List[ZoneCandidate]) -> dict:
    """Aggregate totals across all simulated zones — useful for the
    dashboard's top-line statistics panel."""
    total_population = sum(c.impact.population_affected for c in candidates)
    total_buildings = sum(c.impact.buildings_affected for c in candidates)
    total_roads_km = sum(c.impact.roads_affected_km for c in candidates)
    total_hospitals = sum(c.impact.hospitals_affected for c in candidates)

    ranked = prioritize_zones(candidates)
    level_counts = {level.value: 0 for level in RiskLevel}
    for z in ranked:
        level_counts[z["risk_level"]] += 1

    return {
        "total_zones": len(candidates),
        "total_population_affected": total_population,
        "total_buildings_affected": total_buildings,
        "total_roads_affected_km": round(total_roads_km, 2),
        "total_hospitals_affected": total_hospitals,
        "risk_level_counts": level_counts,
        "top_priority_zones": ranked[:5],
    }


if __name__ == "__main__":
    import json

    candidates = [
        ZoneCandidate(
            zone_id="zone_a",
            zone_name="Riverside Ward",
            impact=ScenarioImpact(
                scenario_id="scn_001",
                flood_level=3.0,
                flooded_area=42.3,
                population_affected=27431,
                buildings_affected=1327,
                roads_affected_km=31,
                affected_road_segments=18,
                hospitals_affected=3,
            ),
        ),
        ZoneCandidate(
            zone_id="zone_b",
            zone_name="Hillside Colony",
            impact=ScenarioImpact(
                scenario_id="scn_002",
                flood_level=1.2,
                flooded_area=8.1,
                population_affected=4200,
                buildings_affected=210,
                roads_affected_km=4.5,
                affected_road_segments=3,
                hospitals_affected=0,
            ),
        ),
    ]

    print(json.dumps(summarize_impact(candidates), indent=2))
