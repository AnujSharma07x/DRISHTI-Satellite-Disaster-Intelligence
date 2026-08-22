# DRISHTI Backend — Phase 2 Infrastructure

This is the FastAPI backend foundation for DRISHTI (Engineer 1's Phase 2
deliverable). It implements the **Phase 1 MVP Core API** exactly as locked in
[`../docs/API_CONTRACT.md`](../docs/API_CONTRACT.md):

- `GET /api/health`
- `GET /api/regions`
- `POST /api/simulation`
- `GET /api/simulation/{scenario_id}`
- `GET /api/risk-zones`

The **Later Implementation** endpoints (`/api/flood/{event_id}`,
`/api/response-plan`, `/api/route`) are intentionally not wired up yet — they
depend on modules owned by Engineers 2 and 4.

> ⚠️ **A live Supabase project has not been created or connected by this
> assistant.** No Supabase credentials and no network egress to `supabase.co`
> were available in the working environment (see "Manual Setup Checklist"
> below, which is exactly what Phase 2 asked for in that situation). Everything
> below has been validated as far as possible without those two things — see
> "What Was Actually Tested" at the bottom of this file.

---

## 1. Manual Setup Checklist (do this by hand, once)

1. **Create a Supabase project** at [supabase.com](https://supabase.com) (free tier is fine for the MVP).
2. **Enable PostGIS:** Project → Database → Extensions → search "postgis" → enable.
   (`database/schema.sql` also runs `create extension if not exists postgis;`
   itself, so this step is a safety net, not strictly required twice.)
3. **Apply the schema:** Project → SQL Editor → paste and run, in this order:
   1. [`../database/schema.sql`](../database/schema.sql) — the 9 locked MVP core tables.
   2. [`../database/views.sql`](../database/views.sql) — read-only GeoJSON views used by the API (see §5 below for why).
4. **Create the Storage buckets:** Project → Storage → "New bucket", create each of:
   - `satellite`
   - `dem`
   - `flood-masks`
   - `model-outputs`
   - `generated-maps`

   Recommended: keep all five **private** (not public). The backend uses the
   service-role key server-side, so it can read/write private buckets
   directly; the frontend never touches Storage directly (see §7 Security).
5. **Copy your credentials:** Project Settings → API. You need:
   - `Project URL` → `SUPABASE_URL`
   - `anon public` key → `SUPABASE_ANON_KEY` (not used by the backend yet, but recorded for completeness / future frontend use)
   - `service_role` key → `SUPABASE_SERVICE_ROLE_KEY` — **treat this like a root password**
   - Project Settings → Database → Connection string → `DATABASE_URL` (only needed if you prefer applying `schema.sql` via `psql` instead of the SQL Editor)
6. **Configure your local `.env`:**
   ```bash
   cp .env.example .env   # from the repo root
   # then fill in the five values above
   ```
7. **Seed one region.** Nothing in the pipeline works until at least one row
   exists in `regions` (every other table has a `region_id` foreign key). No
   seed script exists yet in Phase 2 — this is Day 1 work per
   `docs/ARCHITECTURE.md` §2, to be done by whoever ingests the first region's
   boundary (Engineer 1 or 3, by team agreement).

---

## 2. Running the Backend

```bash
# from the repo root
pip install -r backend/requirements.txt
cp .env.example .env   # then fill in your Supabase credentials (§1 above)

uvicorn backend.app.main:app --reload --port 8000
```

Then visit:
- `http://localhost:8000/api/health` — connectivity check (will return `503`
  with a clear `{"error": "..."}` message until `.env` is filled in and the
  schema has been applied — this is correct, expected behavior, not a bug)
- `http://localhost:8000/docs` — interactive Swagger UI, auto-generated from
  the Pydantic schemas in `backend/app/schemas/`

**Requires Python 3.10+** (the codebase uses `str | None` union-type syntax).

---

## 3. Required Environment Variables

See [`.env.example`](../.env.example) at the repo root. Summary:

| Variable | Required | Purpose |
|---|---|---|
| `SUPABASE_URL` | Yes | Your project's REST API URL |
| `SUPABASE_SERVICE_ROLE_KEY` | Yes | Server-side only — full read/write access. **Never** send to the frontend. |
| `SUPABASE_ANON_KEY` | Recorded, not yet used | For a future direct-frontend-to-Supabase read path, if ever added (not part of MVP architecture) |
| `DATABASE_URL` | Optional | Only needed to apply `schema.sql`/`views.sql` via `psql` instead of the Supabase SQL Editor |
| `FRONTEND_ORIGINS` | Optional | Comma-separated CORS allow-list; defaults to `localhost:3000,localhost:5173` |

`.env` is git-ignored at the repo root — never commit the real file.

---

## 4. Project Structure

```
backend/
├── app/
│   ├── main.py          # FastAPI app, CORS, error-shape handlers, router registration
│   ├── config.py         # env var loading (Settings)
│   ├── database.py        # Supabase client factory (service-role key, server-side only)
│   ├── api/                 # thin route handlers — one file per resource
│   │   ├── health.py
│   │   ├── regions.py
│   │   ├── simulation.py
│   │   └── risk.py
│   ├── schemas/              # Pydantic request/response models — mirror API_CONTRACT.md exactly
│   │   ├── geometry.py
│   │   ├── region.py
│   │   ├── simulation.py
│   │   └── risk.py
│   └── services/
│       └── supabase_service.py   # all Supabase table/view queries live here
├── requirements.txt
└── README.md (this file)
```

---

## 5. Implementation Note: Geometry → GeoJSON (`database/views.sql`)

`docs/API_CONTRACT.md` requires every API geometry field to be **GeoJSON**.
Supabase's REST layer (PostgREST) returns PostGIS `geometry` columns as raw
WKB by default — not GeoJSON. Rather than changing any locked table (which
would need team sign-off per `docs/ARCHITECTURE.md` §4 rule 5), Phase 2 adds
[`../database/views.sql`](../database/views.sql): simple, additive, **read-only**
views (`regions_geojson`, `simulation_scenarios_geojson`, `risk_zones_geojson`)
that expose `ST_AsGeoJSON(geometry)` instead of the raw column. No table is
modified. Writes (e.g. `POST /api/simulation`) go directly against the base
tables in `schema.sql` — the views are for reads only.

This was validated against a real local PostgreSQL + PostGIS instance during
Phase 2 (see §9) and produces correct GeoJSON output.

---

## 6. Known Deferrals (flagged, not silent)

- **`flood_predictions.flood_event_id`** is created as a plain nullable
  `uuid` column (matching `docs/DATABASE_SCHEMA.md` exactly in name, type,
  and nullability), but its foreign-key constraint to `flood_events(id)` is
  **deferred** — `flood_events` is an Optional/Future MVP Extension and is not
  created by `schema.sql`. The commented-out `ALTER TABLE ... ADD CONSTRAINT`
  statement is at the bottom of `schema.sql`, ready to run once `flood_events`
  is adopted. This does not change the contract — the column is exactly as
  documented — it only defers enforcement of a constraint that would
  otherwise fail against a non-existent table.
- **`buildings`** and **`flood_events`** tables are not created at all, per
  the Phase 2 instruction not to implement Optional/Future MVP Extensions
  unless explicitly required.
- **`POST /api/simulation`** currently only creates a `status: "pending"` row
  with all impact fields `null`. The actual elevation-threshold simulation
  math and `ST_Intersects` impact calculation is Engineer 3's module — this
  endpoint deliberately does not invent flooded-area/population-affected
  numbers (Phase 2 Step 9 explicitly forbids this).

---

## 7. Security Rules (do not violate)

1. `SUPABASE_SERVICE_ROLE_KEY` is used **only** in `backend/app/database.py`,
   server-side. It is never sent to, stored in, or imported by anything in
   `frontend/`.
2. `.env` is git-ignored. Never commit real credentials, in code, docs, or
   `.env.example` (which contains placeholders only).
3. CORS is restricted to `FRONTEND_ORIGINS` (default: localhost dev ports
   only) — not wildcard-open in a way that would matter once deployed.
4. All request bodies are validated via Pydantic schemas before touching the
   database.
5. No authentication is implemented in Phase 2 (Supabase Auth remains a
   `NICE TO HAVE`, per `docs/ARCHITECTURE.md` §2) — the API is intentionally
   open for the MVP demo.

---

## 8. How Other Engineers Connect Their Modules

All of you read/write through the **same Supabase project** using the schema
in `database/schema.sql` — there is no separate local database per module.

- **Engineer 2 (AI flood detection):** write your U-Net output directly to
  the `flood_predictions` table (via the Supabase Python client, same pattern
  as `backend/app/services/supabase_service.py`) — set `status: "processing"`
  while running, `"completed"` with `geometry`/`flood_area` filled in when
  done, or `"failed"` on error. Upload the raster mask to the `flood-masks`
  Storage bucket and store its path in `mask_storage_path`. Do not call any
  Digital Twin/simulation code directly — Engineer 3 reads `flood_predictions`
  on its own.
- **Engineer 3 (Digital Twin + simulation):** poll or watch
  `simulation_scenarios` rows created by `POST /api/simulation` (`status:
  "pending"`). Compute the elevation-threshold inundation and
  `ST_Intersects`-based impact numbers, then `UPDATE` that same row with
  `status: "completed"` (or `"failed"`) and the computed fields. Use
  `flood_predictions` as your baseline flood extent when relevant.
- **Engineer 4 (risk + response):** read completed `simulation_scenarios`
  rows, write `risk_zones` (linked via `scenario_id`), and — once you're
  ready to build response planning — `response_plans` (linked via
  `priority_zone_id` to your own `risk_zones` rows). The `/api/response-plan`
  and `/api/route` endpoints aren't wired into FastAPI yet; ping Engineer 1
  when your service functions are ready so the corresponding `api/*.py` route
  files can be added (mirroring `api/simulation.py` and `api/risk.py`).
- **Engineer 5 (frontend):** call only the FastAPI endpoints listed at the
  top of this file. Never call Supabase directly, and never compute risk or
  simulation results client-side (`docs/ARCHITECTURE.md` §4 rule 4).

If any of the above needs a contract change (new field, new table, new
endpoint), propose it to the team and update all four `docs/*.md` files
together first — see `docs/ARCHITECTURE.md` §4 rule 5.

---

## 9. What Was Actually Tested (Phase 2)

Since no live Supabase project or network access to `supabase.co` was
available in the working environment:

✅ **Validated for real, against a local PostgreSQL 16 + PostGIS 3 instance:**
- `database/schema.sql` applies with zero errors, is idempotent (safe to
  re-run), and produces all 9 tables with exactly the geometry types/SRIDs
  specified in `docs/DATABASE_SCHEMA.md` (confirmed via `geometry_columns`).
- Status/enum `CHECK` constraints correctly reject invalid values (tested:
  an invalid `flood_predictions.status` value is rejected as expected).
- `ST_Intersects` and other PostGIS spatial queries work against the schema.
- `database/views.sql` applies cleanly and `ST_AsGeoJSON(...)` produces
  correct GeoJSON output matching `docs/API_CONTRACT.md`'s format.

✅ **Validated via FastAPI's `TestClient` (no network needed):**
- The app imports cleanly and all 5 MVP Core API routes register at the
  correct paths.
- Every error path (missing config, business-logic errors, and Pydantic
  request-validation errors) returns the exact `{"error": "..."}` shape
  locked in `docs/API_CONTRACT.md` — not FastAPI's default `{"detail": ...}`.
- `GET /api/health` correctly returns `503` with a clear, actionable message
  when Supabase credentials are not configured (the expected state until a
  human completes §1 above).

❌ **Not tested (requires a live Supabase project):**
- Actually connecting `backend/app/database.py` to a real Supabase instance
  over the network.
- End-to-end `POST /api/simulation` → row appears in Supabase → `GET
  /api/simulation/{id}` returns it.
- Storage bucket creation/access.

Once a human completes the Manual Setup Checklist (§1) and fills in `.env`,
re-run `uvicorn backend.app.main:app --reload` and hit `/api/health` — it
should return `{"status": "ok"}`.
