"""
DRISHTI — Engineer 4
Lightweight tests for the risk module.

No test framework dependency beyond the standard library (`assert` +
a tiny runner) — per project scope, no large testing framework is
introduced. Run with:

    python3 tests/test_risk.py

from the project root (DRISHTI/), or:

    python3 -m tests.test_risk
"""

from __future__ import annotations

import sys
from pathlib import Path

# Allow running this file directly (`python3 tests/test_risk.py`) without
# having installed the project as a package.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from risk.risk_engine import (
    ScenarioImpact,
    RiskLevel,
    assess,
    classify_risk_level,
    compute_risk_score,
)
from risk.impact import ZoneCandidate, prioritize_zones


def test_risk_level_thresholds():
    # Boundaries per risk_engine.classify_risk_level docstring:
    # [0,20) LOW, [20,40) MODERATE, [40,60) HIGH, [60,80) VERY HIGH, [80,100] CRITICAL
    assert classify_risk_level(0) == RiskLevel.LOW
    assert classify_risk_level(19.99) == RiskLevel.LOW
    assert classify_risk_level(20) == RiskLevel.MODERATE
    assert classify_risk_level(39.99) == RiskLevel.MODERATE
    assert classify_risk_level(40) == RiskLevel.HIGH
    assert classify_risk_level(59.99) == RiskLevel.HIGH
    assert classify_risk_level(60) == RiskLevel.VERY_HIGH
    assert classify_risk_level(79.99) == RiskLevel.VERY_HIGH
    assert classify_risk_level(80) == RiskLevel.CRITICAL
    assert classify_risk_level(100) == RiskLevel.CRITICAL


def test_weighted_score_matches_manual_calculation():
    # flood_level=2.5m -> 2.5/5.0*100 = 50
    # population=25000 -> 25000/50000*100 = 50
    # hospitals_affected=0, no critical_infra info -> infra score = 0
    # roads_affected_km=5km, total_road_km_in_region=50km -> 5/50*100=10
    impact = ScenarioImpact(
        scenario_id="manual_check",
        flood_level=2.5,
        flooded_area=10.0,
        population_affected=25_000,
        buildings_affected=100,
        roads_affected_km=5.0,
        hospitals_affected=0,
        total_road_km_in_region=50.0,
    )
    expected = round(0.30 * 50 + 0.30 * 50 + 0.25 * 0 + 0.15 * 10, 2)  # 31.5
    actual = compute_risk_score(impact)
    assert actual == expected, f"expected {expected}, got {actual}"

    result = assess(impact)
    assert result["accessibility_fallback_used"] is False, (
        "total_road_km_in_region was supplied — the DEMO FALLBACK must not fire"
    )
    assert result["components"]["accessibility_score"] == 10.0


def test_accessibility_demo_fallback_is_flagged():
    # No total_road_km_in_region supplied -> DEMO FALLBACK path must be used
    # and explicitly flagged, never silently treated as real data.
    impact = ScenarioImpact(
        scenario_id="fallback_check",
        flood_level=1.0,
        flooded_area=1.0,
        population_affected=100,
        buildings_affected=5,
        roads_affected_km=5.0,
        hospitals_affected=0,
        total_road_km_in_region=None,
    )
    result = assess(impact)
    assert result["accessibility_fallback_used"] is True


def test_priority_ordering_uses_risk_score_not_flood_depth():
    """Regression test for Fix #1.

    Zone A has a DEEPER flood but far fewer people affected.
    Zone B has a shallower flood but a much larger population affected,
    and therefore a genuinely higher risk score.

    Before the fix, sorting was lexicographic on (flood_level,
    population, infra, risk_score), so Zone A would incorrectly outrank
    Zone B purely because 4.0m > 3.0m. After the fix, risk_score is the
    primary sort key, so Zone B must rank first.
    """
    zone_a = ZoneCandidate(
        "zone_a",
        "Zone A (deep flood, low population)",
        ScenarioImpact(
            scenario_id="a",
            flood_level=4.0,
            flooded_area=10,
            population_affected=500,
            buildings_affected=50,
            roads_affected_km=2,
            hospitals_affected=0,
        ),
    )
    zone_b = ZoneCandidate(
        "zone_b",
        "Zone B (shallower flood, high population)",
        ScenarioImpact(
            scenario_id="b",
            flood_level=3.0,
            flooded_area=40,
            population_affected=50_000,
            buildings_affected=2000,
            roads_affected_km=2,
            hospitals_affected=0,
        ),
    )

    ranked = prioritize_zones([zone_a, zone_b])
    assert ranked[0]["zone_id"] == "zone_b", (
        f"Fix #1 regression: expected zone_b first (higher risk_score), "
        f"got ranking {[z['zone_id'] for z in ranked]}"
    )
    assert ranked[0]["risk_score"] > ranked[1]["risk_score"]


def test_priority_ordering_tiebreak_uses_flood_depth():
    """When risk_score ties exactly, flood_level is the first tie-breaker."""
    base_kwargs = dict(
        flooded_area=10,
        buildings_affected=50,
        roads_affected_km=2,
        hospitals_affected=0,
        total_road_km_in_region=50.0,
    )
    # Construct two scenarios with identical risk_score by giving them
    # identical population/infra/accessibility inputs but different flood
    # depths is actually impossible without changing risk_score itself
    # (flood_level feeds the score). Instead, verify the *documented*
    # tie-break key ordering directly against _rank_key's contract: given
    # equal risk_score (simulated via monkeypatched equal scores is out of
    # scope for this lightweight test), we instead verify the simpler,
    # directly observable property that flood_level is compared before
    # population/infra/accessibility in the tuple returned by _rank_key.
    from risk.impact import _rank_key

    impact_high_flood = ScenarioImpact(
        scenario_id="tie1", flood_level=5.0, population_affected=100, **base_kwargs
    )
    impact_low_flood = ScenarioImpact(
        scenario_id="tie2", flood_level=1.0, population_affected=100, **base_kwargs
    )
    zone_high = ZoneCandidate("zh", "High flood", impact_high_flood)
    zone_low = ZoneCandidate("zl", "Low flood", impact_low_flood)

    # Fabricate identical risk_score results but differing flood_level to
    # isolate the tie-breaker behaviour of _rank_key directly.
    fake_result = {"risk_score": 50.0, "breakdown": {"accessibility_score": 10.0}}
    key_high = _rank_key(zone_high, fake_result)
    key_low = _rank_key(zone_low, fake_result)
    assert key_high[0] == key_low[0] == 50.0  # same risk_score
    assert key_high[1] > key_low[1], "flood_level must be the first tie-breaker"


def test_road_impact_fields_are_separate_and_pass_through():
    """Regression test for the integration-round road-impact naming fix:
    `roads_affected_km` (a LENGTH used by the accessibility formula) and
    `affected_road_segments` (an optional COUNT, pass-through only) must
    stay distinct and both survive into assess()'s output."""
    impact = ScenarioImpact(
        scenario_id="naming_check",
        flood_level=2.0,
        flooded_area=5.0,
        population_affected=1000,
        buildings_affected=20,
        roads_affected_km=12.5,
        affected_road_segments=7,
        hospitals_affected=1,
        total_road_km_in_region=50.0,
    )
    result = assess(impact)
    assert result["roads_affected_km"] == 12.5
    assert result["affected_road_segments"] == 7
    # affected_road_segments must NOT influence the accessibility score —
    # only roads_affected_km / total_road_km_in_region does.
    assert result["components"]["accessibility_score"] == round(100 * 12.5 / 50.0, 2)


def test_affected_road_segments_optional_and_defaults_to_none():
    impact = ScenarioImpact(
        scenario_id="no_segments",
        flood_level=1.0,
        flooded_area=1.0,
        population_affected=10,
        buildings_affected=1,
        roads_affected_km=1.0,
        hospitals_affected=0,
    )
    result = assess(impact)
    assert result["affected_road_segments"] is None


TESTS = [
    test_risk_level_thresholds,
    test_weighted_score_matches_manual_calculation,
    test_accessibility_demo_fallback_is_flagged,
    test_priority_ordering_uses_risk_score_not_flood_depth,
    test_priority_ordering_tiebreak_uses_flood_depth,
    test_road_impact_fields_are_separate_and_pass_through,
    test_affected_road_segments_optional_and_defaults_to_none,
]


def run():
    failures = 0
    for test in TESTS:
        try:
            test()
            print(f"PASS  {test.__name__}")
        except AssertionError as e:
            failures += 1
            print(f"FAIL  {test.__name__}: {e}")
    print(f"\n{len(TESTS) - failures}/{len(TESTS)} tests passed")
    if failures:
        sys.exit(1)


if __name__ == "__main__":
    run()
