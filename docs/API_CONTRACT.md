# DRISHTI — API Contract (Phase 1, Locked)

FastAPI backend. All vector data in requests/responses is **GeoJSON, EPSG:4326**
(see `DATA_FORMATS.md` §1). All endpoints return JSON. Errors return a JSON body
`{ "error": "..." }` with an appropriate HTTP status code.

The service-role Supabase key is used only inside FastAPI and is never sent to the
frontend (see `ARCHITECTURE.md` §7).

---

## Implementation Priority

### PHASE 1 / MVP CORE API (build these first)

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | Health check |
| GET | `/api/regions` | List regions |
| POST | `/api/simulation` | Run a flood-level scenario simulation |
| GET | `/api/simulation/{scenario_id}` | Fetch a simulation result |
| GET | `/api/risk-zones` | Fetch risk zones (optionally filtered by region) |

### LATER IMPLEMENTATION API (kept in contract, not blocking MVP)

| Method | Path | Purpose | Depends on |
|---|---|---|---|
| GET | `/api/flood/{event_id}` | Fetch a flood event / prediction map | `flood_events` (optional table) |
| POST | `/api/response-plan` | Generate a response plan | Engineer 4 (risk + routing) |
| POST | `/api/route` | Compute an emergency route | Engineer 4 (routing module) |

---

## Endpoint Definitions

### `GET /api/health`
Response:
```json
{ "status": "ok" }
```

### `GET /api/regions`
Response:
```json
{
  "regions": [
    {
      "id": "uuid",
      "name": "string",
      "state": "string",
      "country": "string",
      "geometry": { "type": "Polygon", "coordinates": [...] },
      "created_at": "2026-08-22T00:00:00Z"
    }
  ]
}
```

### `POST /api/simulation`
Runs a what-if flood-level simulation for a region and stores it in
`simulation_scenarios`.

Request:
```json
{
  "region_id": "uuid",
  "flood_level": 3.0
}
```

Response (`201 Created`):
```json
{
  "scenario_id": "uuid",
  "region_id": "uuid",
  "flood_level": 3.0,
  "status": "completed",
  "flooded_area": 42.3,
  "population_affected": 27431,
  "buildings_affected": 1327,
  "roads_affected_count": 31,
  "hospitals_affected": 3,
  "result_geometry": { "type": "MultiPolygon", "coordinates": [...] },
  "created_at": "2026-08-22T00:00:00Z"
}
```

Notes:
- `flood_level` is in **metres** (see `DATA_FORMATS.md` §3).
- `flooded_area` is in **km²**.
- `roads_affected_count` is always an integer count of road segments/features
  intersected by the flood extent. It is never a length/distance value. A future,
  optional `affected_road_length_km` field may be added separately if road-length
  reporting is needed — see `DATABASE_SCHEMA.md` §7.
- `buildings_affected` is `null` if the `buildings` table is not populated for the
  region (optional table).
- `status` starts as `pending`/`running` while processing and becomes `completed` or
  `failed`; the response above reflects a synchronous, already-completed simulation
  for the MVP. If simulation becomes asynchronous later, `POST /api/simulation`
  should return `status: "pending"` immediately and the client polls
  `GET /api/simulation/{scenario_id}`.

### `GET /api/simulation/{scenario_id}`
Response: same shape as the `POST /api/simulation` response above, fetched by ID.
If `status` is `pending` or `running`, impact fields may be `null`.

### `GET /api/risk-zones`
Query params: `region_id` (optional), `scenario_id` (optional).

Response:
```json
{
  "risk_zones": [
    {
      "id": "uuid",
      "region_id": "uuid",
      "scenario_id": "uuid",
      "risk_score": 0.82,
      "risk_level": "HIGH",
      "population_exposed": 12000,
      "infrastructure_exposed": 4,
      "geometry": { "type": "Polygon", "coordinates": [...] },
      "created_at": "2026-08-22T00:00:00Z"
    }
  ]
}
```

`risk_level` is one of `LOW`, `MODERATE`, `HIGH`, `VERY_HIGH`, `CRITICAL`
(see `DATABASE_SCHEMA.md` §8, `DATA_FORMATS.md` §4).

---

### `GET /api/flood/{event_id}` *(later)*
Response:
```json
{
  "event_id": "uuid",
  "region_id": "uuid",
  "predictions": [
    {
      "id": "uuid",
      "status": "completed",
      "confidence": 0.91,
      "flood_area": 40.1,
      "geometry": { "type": "MultiPolygon", "coordinates": [...] },
      "created_at": "2026-08-22T00:00:00Z"
    }
  ]
}
```
Depends on the optional `flood_events` table (`DATABASE_SCHEMA.md`). Until that
table is adopted, this endpoint is not implemented.

### `POST /api/response-plan` *(later)*
Request:
```json
{ "scenario_id": "uuid" }
```
Response: array of `response_plans` rows (see `DATABASE_SCHEMA.md` §9) as GeoJSON
routes.

### `POST /api/route` *(later)*
Request:
```json
{ "origin": { "lat": 0.0, "lng": 0.0 }, "facility_id": "uuid" }
```
Response:
```json
{
  "route_geometry": { "type": "LineString", "coordinates": [...] },
  "estimated_distance_km": 4.2,
  "estimated_time_minutes": 9.5
}
```

---

## Resolved: `roads_affected_count`

Earlier drafts left it ambiguous whether the roads-affected metric was a count or a
length. This is now locked: `roads_affected_count` is always an integer count. See
`DATABASE_SCHEMA.md` §7 and `DATA_FORMATS.md` §3 for the full definition and the
optional future `affected_road_length_km` extension.
