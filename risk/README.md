# Risk Module — DRISHTI (Engineer 4)

Transparent, explainable risk scoring and priority-zone ranking for
flood scenarios. No ML — a documented weighted formula, per the SIH
10-day scope. This README reflects the state after the Engineer 4 Fix
Prompt (see "Fixes applied" below).

## Files

| File | Purpose |
|---|---|
| `risk_engine.py` | Computes a 0–100 risk score and `risk_level` for one simulated scenario. |
| `impact.py` | Ranks multiple scenarios/zones into a priority order and produces summary stats for the dashboard. |

## Package usage

Both files support being imported either as a package from the project
root, or run as flat standalone scripts:

```python
# From project root (e.g. FastAPI backend):
from risk.risk_engine import assess, ScenarioImpact
from risk.impact import prioritize_zones, ZoneCandidate

# Or run directly for the demo output:
#   python3 risk_engine.py
#   python3 impact.py
```

`impact.py` imports `risk_engine` via a relative-import-with-fallback
shim so both modes work without any `sys.path` hacking.

## Current Engineer 3 contract (input)

```json
{
  "scenario_id": "...",
  "flood_level": 3.0,
  "flooded_area": 42.3,
  "population_affected": 27431,
  "buildings_affected": 1327,
  "roads_affected_km": 31,
  "affected_road_segments": 18,
  "hospitals_affected": 3
}
```

Maps directly onto `risk_engine.ScenarioImpact`. Note the two
road-impact fields are deliberately separate (see Fix #0 below):

- `roads_affected_km` — **length** (km) of flooded road network. This is
  the field the accessibility formula uses.
- `affected_road_segments` — optional **count** of individual flooded
  road segments. Pass-through only, not used in scoring.

Two additional **optional** fields are accepted, populated by the
FastAPI layer from Engineer 1's schema when available — omitting them is
safe and does not break the contract:

- `total_road_km_in_region` — total road length (km) for the region, for
  an accurate accessibility calculation (see Fix #2 below).
- `critical_infrastructure_affected` — count of non-hospital critical
  facilities affected (fire/police/relief/bridges), for a fuller
  infrastructure score (see MVP limitation below).

## Risk formula (unchanged from the target formula — not modified)

```
risk_score = 0.30 * flood_severity_score
           + 0.30 * population_exposure_score
           + 0.25 * infrastructure_importance_score
           + 0.15 * accessibility_score
```

Each sub-score is normalized to 0–100 against a fixed cap (see `CAPS` in
`risk_engine.py`):

- **flood_severity_score** — `flood_level / 5.0m`, capped at 100.
- **population_exposure_score** — `population_affected / 50,000`, capped at 100.
- **infrastructure_importance_score** — hospitals weighted heaviest
  (life-safety critical); other critical infrastructure adds up to 30
  points if that count is supplied (see MVP limitation below).
- **accessibility_score** — fraction of regional road network flooded.
  See Fix #2.

## Risk levels (unchanged — actual thresholds enforced by the code)

| Score range | Level |
|---|---|
| [0, 20) | LOW |
| [20, 40) | MODERATE |
| [40, 60) | HIGH |
| [60, 80) | VERY HIGH |
| [80, 100] | CRITICAL |

These are inclusive-lower/exclusive-upper except the final CRITICAL
band, which is closed at 100. Documented directly in
`classify_risk_level()`'s docstring so a future edit can't silently
shift a boundary.

---

## Fixes applied (per the Engineer 4 Fix Prompt)

### Fix #1 — Priority-zone ordering

**Bug:** `impact._rank_key()` previously sorted zones lexicographically
on `(flood_level, population_affected, critical_infrastructure,
risk_score)`. Because Python tuple comparison checks the first element
first, a zone with a *deeper flood but far lower population/risk* could
outrank a zone with a *shallower flood but much higher risk* — exactly
the Zone A / Zone B example in the fix brief.

**Fix:** `risk_score` (which already blends all four weighted factors)
is now the **primary** sort key. The individual components remain as
deterministic tie-breakers for when two zones land on the same score:

```
Primary:      risk_score
Tie-break 1:  flood_level
Tie-break 2:  population_affected
Tie-break 3:  hospitals_affected + critical_infrastructure_affected
Tie-break 4:  accessibility_score
```

Verified by `tests/test_risk.py::test_priority_ordering_uses_risk_score_not_flood_depth`,
which reproduces the exact brief example (4.0m/500-people zone vs.
3.0m/50,000-people zone) and asserts the higher-risk zone ranks first.

### Fix #2 — Accessibility score / DEMO FALLBACK

**Problem:** the fallback total-road-length constant (previously a bare
`25.0` used silently whenever `total_road_km_in_region` wasn't supplied)
could be mistaken for real regional data.

**Fix:**
- The constant is now named `DEMO_FALLBACK_TOTAL_ROAD_KM` with an
  explicit "NOT real GIS data" comment.
- `assess()` now always returns `accessibility_fallback_used: bool`, so
  the dashboard/backend can visibly flag (or simply avoid trusting) any
  score computed with the fallback rather than a real regional figure.
- When `total_road_km_in_region` **is** supplied (ideally from a PostGIS
  `ST_Length` sum over Engineer 1's `roads` table for the region, passed
  in by the caller), the real fraction is used and the flag is `false`.
- No new database table was introduced — this module still only
  *consumes* a number passed in by the caller.

```
DEMO FALLBACK:
total_road_km_in_region = 25 km   (used ONLY if the real value is absent)
```

### Fix #3 — Infrastructure score (MVP limitation, unchanged design)

Kept as the existing simple, explainable approach — **not redesigned**.
`hospitals_affected` remains required (per Engineer 3's current
contract); `critical_infrastructure_affected` remains optional. If the
optional field is absent, the hospital-only component is scaled to fill
the full 0–100 range rather than being penalized for missing data.

**MVP limitation:** the current Engineer 3 output only reports
`hospitals_affected`. Fire stations, police stations, relief centres,
schools, and bridges are part of the master architecture's
`critical_infrastructure` table but are not yet broken out in the
simulation output. This module is ready to use that count the moment
it's available (via the optional field) without any interface change.

---

## Testing

```bash
python3 tests/test_risk.py
```

Covers: risk-level thresholds, weighted-score calculation against a
manual reference computation, the DEMO FALLBACK flag, and the Fix #1
priority-ordering regression (including tie-break behaviour).

## Example

```bash
python3 risk_engine.py   # single-scenario breakdown
python3 impact.py        # two-zone ranked summary
```

## Explicitly out of scope (per project constraints)

- No ML-based risk model, no learned weights.
- No modification of the AI flood-detection model, React UI, database
  schema, or Digital Twin architecture — this module only *consumes*
  `simulation_scenarios` output and *produces* data for `risk_zones` /
  `response_plans`.
- No new persistent storage or database table.
