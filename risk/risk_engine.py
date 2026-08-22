"""
DRISHTI — Engineer 4
Risk Engine

Consumes the impact-simulation output produced by Engineer 3
(simulation_scenarios) and produces a transparent, explainable risk score
and risk_level classification.

NO ML MODEL. This is intentional per the SIH 10-day scope: a weighted,
documented formula is easier to justify to judges and to debug under time
pressure than an opaque model trained on very little labeled data.

------------------------------------------------------------------------
INPUT CONTRACT (from Engineer 3 / simulation_scenarios)
------------------------------------------------------------------------
{
    "scenario_id": "uuid",
    "flood_level": 3.0,             # metres
    "flooded_area": 42.3,           # km^2
    "population_affected": 27431,
    "buildings_affected": 1327,
    "roads_affected_km": 31,        # LENGTH of flooded road network (km)
    "affected_road_segments": 18,   # optional: COUNT of flooded segments (not a length)
    "hospitals_affected": 3
}

NAMING FIX: the field previously named `roads_affected` was ambiguous —
it could plausibly mean either a road count or a road length. It has
been split into two separate, unambiguous fields:
  - `roads_affected_km` — total flooded road LENGTH, in kilometres. This
    is the field the accessibility formula actually uses.
  - `affected_road_segments` — optional COUNT of individual flooded road
    segments, kept purely as pass-through context for the dashboard /
    response_plans; it does not feed the risk formula.

ASSUMPTION (documented per project rule #16 — "if unclear, document the
assumption instead of silently changing architecture"):
The upstream contract does not include a raw "accessibility" number.
Accessibility is derived here from roads_affected_km as a fraction of
the total road length in the region (total_road_km), which must be
supplied by the caller (it lives in the `roads` table / region metadata
owned by Engineer 1's schema). If total_road_km is not supplied, a
**DEMO FALLBACK** constant is used instead — see `_accessibility_penalty()`
below. The fallback is explicitly flagged in `assess()`'s output
(`accessibility_fallback_used: true`) so it is never silently mistaken
for real GIS data by the dashboard or by judges inspecting output. This
fallback should be replaced once the real region road-length figure is
wired in from Supabase; it does not change the public function
signatures.
------------------------------------------------------------------------
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class RiskLevel(str, Enum):
    LOW = "LOW"
    MODERATE = "MODERATE"
    HIGH = "HIGH"
    VERY_HIGH = "VERY HIGH"
    CRITICAL = "CRITICAL"


@dataclass
class ScenarioImpact:
    """Mirrors the simulation_scenarios output contract from Engineer 3.

    NAMING FIX: `roads_affected` (ambiguous — could read as a count or a
    length) has been split into `roads_affected_km` (length, used by the
    accessibility formula) and the separate optional `affected_road_segments`
    (a count, pass-through only, not used in scoring). See the module
    docstring's "NAMING FIX" note for the full rationale.
    """

    scenario_id: str
    flood_level: float          # metres
    flooded_area: float         # km^2
    population_affected: int
    buildings_affected: int
    roads_affected_km: float    # LENGTH of flooded road network, in km
    hospitals_affected: int

    # Optional context, supplied by the caller when available (region
    # metadata owned by Engineer 1's schema). Used only to make the
    # accessibility component more accurate; safe to omit.
    total_road_km_in_region: Optional[float] = None
    critical_infrastructure_affected: Optional[int] = None

    # Optional pass-through context — a COUNT of individual flooded road
    # segments (distinct from roads_affected_km, which is a LENGTH). Not
    # used by any scoring formula; carried through to output purely for
    # dashboard/response_plans context if the caller supplies it.
    affected_road_segments: Optional[int] = None


# ------------------------------------------------------------------------
# WEIGHTS — the entire risk formula lives here so judges/reviewers can see
# it at a glance. Weights sum to 1.0 across the four sub-scores.
# ------------------------------------------------------------------------
WEIGHTS = {
    "flood_severity": 0.30,
    "population_exposure": 0.30,
    "infrastructure_importance": 0.25,
    "accessibility": 0.15,
}

# Normalization caps. Values at/above the cap score 100 on that sub-metric.
# These are deliberately simple, round numbers tuned for a single
# flood-prone Indian district/city-scale region (the SIH prototype scope),
# not a state- or national-scale deployment.
CAPS = {
    "flood_level_m": 5.0,            # 5m+ treated as maximum severity
    "population_affected": 50_000,   # 50k+ treated as maximum exposure
    "hospitals_affected": 5,         # 5+ hospitals affected = maximum
    "critical_infra_affected": 10,   # 10+ critical facilities = maximum
}

RISK_THRESHOLDS = [
    (20, RiskLevel.LOW),
    (40, RiskLevel.MODERATE),
    (60, RiskLevel.HIGH),
    (80, RiskLevel.VERY_HIGH),
    (101, RiskLevel.CRITICAL),  # 80-100 -> CRITICAL
]


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def _flood_severity_score(impact: ScenarioImpact) -> float:
    """0-100. Blends flood depth (primary driver) with flooded area share
    of population/building impact already captured elsewhere, so we keep
    this component focused on depth to avoid double-counting."""
    return _clamp(100 * impact.flood_level / CAPS["flood_level_m"])


def _population_exposure_score(impact: ScenarioImpact) -> float:
    """0-100, scaled against a regional cap."""
    return _clamp(100 * impact.population_affected / CAPS["population_affected"])


def _infrastructure_importance_score(impact: ScenarioImpact) -> float:
    """0-100. Hospitals are weighted heaviest (life-safety critical),
    other critical infrastructure (fire/police/relief/bridges) adds the
    remainder if the count is available."""
    hospital_component = 70 * _clamp(
        impact.hospitals_affected / CAPS["hospitals_affected"], 0, 1
    )
    if impact.critical_infrastructure_affected is not None:
        other_component = 30 * _clamp(
            impact.critical_infrastructure_affected
            / CAPS["critical_infra_affected"],
            0,
            1,
        )
    else:
        # No data on other critical infra — don't penalize or reward,
        # just scale the hospital component up to fill the 0-100 range.
        hospital_component = 100 * _clamp(
            impact.hospitals_affected / CAPS["hospitals_affected"], 0, 1
        )
        other_component = 0
    return _clamp(hospital_component + other_component)


# DEMO FALLBACK — NOT real GIS data. Used ONLY for offline/local testing
# when the caller cannot supply total_road_km_in_region (e.g. before
# Engineer 1's PostGIS road-length query is wired into the FastAPI/
# service layer). This number is a rough placeholder tuned for a typical
# district-scale demo region. It must never be presented as authoritative
# regional data — assess() flags every use of this fallback via
# `accessibility_fallback_used`.
#
# PRODUCTION PATH (Fix #2, integration round): `total_road_km_in_region`
# is kept as an optional dev/test input on ScenarioImpact — this module
# does NOT connect to Supabase/PostGIS itself and does NOT introduce any
# new table. In the real demo pipeline, the FastAPI/service layer is
# responsible for computing this value from Engineer 1's `roads` table
# and passing it in alongside the scenario output, conceptually:
#
#     SELECT SUM(ST_Length(roads.geometry::geography)) / 1000
#     FROM roads
#     WHERE roads.region_id = :region_id
#
# and supplying the result (km) as `total_road_km_in_region` when
# constructing ScenarioImpact. The fallback below exists purely so this
# module remains runnable/testable in isolation before that wiring is in
# place.
DEMO_FALLBACK_TOTAL_ROAD_KM = 25.0


def _accessibility_penalty(impact: ScenarioImpact) -> tuple[float, bool]:
    """Returns (score, fallback_used).

    score: 0-100, where 100 = worst accessibility (most roads cut off).
    fallback_used: True if DEMO_FALLBACK_TOTAL_ROAD_KM was used because
    the real regional road length wasn't supplied by the caller.

    Preferred path: roads_affected_km / total_road_km_in_region, where
    total_road_km_in_region should ultimately come from the PostGIS
    query documented above (SUM(ST_Length(...))/1000 over Engineer 1's
    `roads` table), computed and passed in by the FastAPI/service layer
    — not queried by this module directly.
    """
    if impact.total_road_km_in_region and impact.total_road_km_in_region > 0:
        fraction = impact.roads_affected_km / impact.total_road_km_in_region
        return _clamp(100 * fraction), False

    fraction = impact.roads_affected_km / DEMO_FALLBACK_TOTAL_ROAD_KM
    return _clamp(100 * fraction), True


def compute_risk_score(impact: ScenarioImpact) -> float:
    """Returns a single 0-100 risk score, weighted per WEIGHTS."""
    flood = _flood_severity_score(impact)
    population = _population_exposure_score(impact)
    infra = _infrastructure_importance_score(impact)
    access, _fallback_used = _accessibility_penalty(impact)

    score = (
        WEIGHTS["flood_severity"] * flood
        + WEIGHTS["population_exposure"] * population
        + WEIGHTS["infrastructure_importance"] * infra
        + WEIGHTS["accessibility"] * access
    )
    return round(_clamp(score), 2)


def classify_risk_level(score: float) -> RiskLevel:
    """Thresholds (inclusive lower bound, exclusive upper bound):

        [0, 20)    LOW
        [20, 40)   MODERATE
        [40, 60)   HIGH
        [60, 80)   VERY HIGH
        [80, 100]  CRITICAL

    These are the actual boundaries enforced by RISK_THRESHOLDS below —
    documented explicitly here since threshold-boundary bugs are easy to
    introduce silently.
    """
    for upper_bound, level in RISK_THRESHOLDS:
        if score < upper_bound:
            return level
    return RiskLevel.CRITICAL


def score_breakdown(impact: ScenarioImpact) -> dict:
    """Returns each sub-score plus the weighted total, for the dashboard
    to display an explainable breakdown (judges will ask 'why CRITICAL?').
    """
    flood = _flood_severity_score(impact)
    population = _population_exposure_score(impact)
    infra = _infrastructure_importance_score(impact)
    access, fallback_used = _accessibility_penalty(impact)
    total = compute_risk_score(impact)

    return {
        "flood_severity_score": round(flood, 2),
        "population_exposure_score": round(population, 2),
        "infrastructure_importance_score": round(infra, 2),
        "accessibility_score": round(access, 2),
        "accessibility_fallback_used": fallback_used,
        "weights": WEIGHTS,
        "risk_score": total,
        "risk_level": classify_risk_level(total).value,
    }


def assess(impact: ScenarioImpact) -> dict:
    """Public entrypoint. Matches the shape expected by risk_zones /
    the FastAPI response for GET /api/risk-zones.

    Includes both:
      - "components": the flat 4-value shape from the task contract
        (flood_severity_score, population_exposure_score,
        infrastructure_importance_score, accessibility_score) for
        callers that just want the explainability breakdown.
      - "breakdown": the same values plus weights/fallback flag, kept
        for backward compatibility with existing callers.
    """
    breakdown = score_breakdown(impact)
    components = {
        "flood_severity_score": breakdown["flood_severity_score"],
        "population_exposure_score": breakdown["population_exposure_score"],
        "infrastructure_importance_score": breakdown[
            "infrastructure_importance_score"
        ],
        "accessibility_score": breakdown["accessibility_score"],
    }
    return {
        "scenario_id": impact.scenario_id,
        "risk_score": breakdown["risk_score"],
        "risk_level": breakdown["risk_level"],
        "population_exposed": impact.population_affected,
        "infrastructure_exposed": impact.hospitals_affected
        + (impact.critical_infrastructure_affected or 0),
        "roads_affected_km": impact.roads_affected_km,
        "affected_road_segments": impact.affected_road_segments,
        "accessibility_fallback_used": breakdown["accessibility_fallback_used"],
        "components": components,
        "breakdown": breakdown,
    }


if __name__ == "__main__":
    # Example matching the sample input in the task brief.
    example = ScenarioImpact(
        scenario_id="scn_001",
        flood_level=3.0,
        flooded_area=42.3,
        population_affected=27431,
        buildings_affected=1327,
        roads_affected_km=31,
        affected_road_segments=18,
        hospitals_affected=3,
    )
    import json

    print(json.dumps(assess(example), indent=2))
