# DRISHTI — AI Flood Detection Module (Engineer 2)

Owns exactly this slice of the DRISHTI pipeline (`docs/ARCHITECTURE.md` §3):

```
Satellite data
      ↓
Preprocessing
      ↓
AI flood detection
      ↓
Flood mask
      ↓
Flood polygon
      ↓
Flood statistics
```

This module **does not** touch React, FastAPI routing, the database schema,
routing/emergency response, or the risk engine — see "Do not work on" below.

---

## 1. Status at a glance

| Piece | Status |
|---|---|
| SAR preprocessing (calibration, despeckle, joint normalization) | ✅ Working |
| Input validation (shape/CRS/transform alignment) | ✅ Working |
| NoData handling | ✅ Working |
| **`ThresholdFloodModel`** (SAR dB change-detection baseline) | ✅ Working — **this is the reliable MVP path, used by default** |
| **`LightUNet`** (trainable PyTorch U-Net) | ⚠️ Implemented, **ships untrained**. Do not use for real predictions until trained — see §4. |
| Flood mask → GeoJSON polygon, area (km²) | ✅ Working |
| Supabase Storage upload (mask raster) | ✅ Working, optional, env-var gated |
| `flood_predictions` payload contract | ✅ Working, schema-validated |

---

## 2. What this module produces

Given a pre-flood and post-flood Sentinel-1 SAR image pair, running the
pipeline produces **three output files** plus a console summary:

1. **`flood_prediction.json`** — a dict matching the `flood_predictions`
   table contract **exactly** (`docs/DATABASE_SCHEMA.md` §3,
   `docs/API_CONTRACT.md`) — nothing more, nothing less, so Engineer 1 can
   insert it directly:

   ```json
   {
     "region_id": "uuid-or-slug",
     "flood_event_id": null,
     "satellite_observation_id": null,
     "model_version": "sar_change_threshold_baseline_v1",
     "confidence": 0.9953,
     "flood_area": 0.6895,
     "mask_storage_path": null,
     "geometry": { "type": "MultiPolygon", "coordinates": [ ... ] },
     "status": "completed"
   }
   ```

2. **`flood_polygon.geojson`** — the flood polygon alone, as a standalone
   GeoJSON file (same geometry as above).

3. **`inference_metadata.json`** — diagnostic info that is **deliberately
   kept out of `flood_prediction.json`** so the DB-contract file never grows
   extra columns Engineer 1 didn't define: whether the confidence value is a
   calibrated probability or a heuristic proxy, valid/invalid pixel counts,
   the threshold(s) used, and whether the run was `--demo`.

- `geometry` is always `EPSG:4326` (`docs/DATA_FORMATS.md` §1), always a
  `MultiPolygon` (never a bare `Polygon`), and `null` only when zero flooded
  pixels were detected.
- `flood_area` is always **km²**, computed via a temporary equal-area
  reprojection — never from raw lat/lon degree math.
- `confidence` is always a float in `[0.0, 1.0]` — see §5 for what it
  actually means for each model.
- `status` is one of `processing | completed | failed`.
- `id` and `created_at` are intentionally omitted — the database assigns
  those.

This module **does not insert into Supabase itself**. It hands Engineer 1 a
contract-compliant payload to insert, or to expose through a thin FastAPI
endpoint that calls into `ai/`.

---

## 3. Quick start

```bash
cd ai
pip install -r requirements.txt --break-system-packages

# Demo mode — SYNTHETIC data only (clearly labelled in the logs). Generates
# a pre/post SAR pair over a sample flood-prone Odisha region, including a
# NoData strip, so the demo exercises NoData handling too.
python run_pipeline.py --demo --region-id demo-region-001 --out ./sample_output

# Equivalently, as a module:
python -m ai.run_pipeline --demo --out ./sample_output

# Real data
python -m ai.run_pipeline \
    --pre  /path/to/pre_flood.tif \
    --post /path/to/post_flood.tif \
    --region-id <uuid-from-regions-table> \
    --out ./output \
    [--drop-threshold-db 3.0] \
    [--weights models/weights/light_unet.pt] \
    [--upload]
```

The CLI reports, for every run: preprocessing status (valid vs. NoData pixel
counts), the detection method used, flooded pixel count, flood area,
confidence (labelled as calibrated or heuristic), and the paths to all three
output files. Errors (missing file, misaligned raster pair, etc.) are
reported clearly and the process exits non-zero.

`sample_output/` in this directory holds real output from a `--demo` run —
not a hand-written example.

---

## 4. The AI model — and an explicit assumption

The master prompt allows: *"If a full training pipeline is too expensive for
the 10-day timeline, create a clean inference pipeline using a suitable
pretrained/trained model or a small demonstrable model."* It also requires:
*"Do NOT pretend that an untrained U-Net is a trained AI model."*

**Assumption made here (flagged explicitly, not silently decided):** no
labelled Sentinel-1 flood dataset or trained weights were available within
this task's scope, so **no training was performed.** Two models are shipped:

1. **`ThresholdFloodModel`** (`models/unet.py`) — the MVP's **reliable
   default**. A zero-training SAR change-detection heuristic:

   ```
   change_db = pre_db - post_db      (positive => backscatter dropped)
   ```

   computed directly on calibrated dB values (not on independently
   normalized [0,1] arrays — see §7 for why that distinction matters). A
   pixel is flagged flooded when the drop exceeds a configurable threshold
   (`--drop-threshold-db`, default **3.0 dB**). This default sits inside the
   ~3–10 dB open-water backscatter drop range reported in SAR flood-mapping
   literature (e.g. Twele et al. 2016) but **is not tuned/validated against
   ground truth for this project** — treat it as a reasonable starting
   point, not a calibrated value.

2. **`LightUNet`** (`models/unet.py`) — a small, trainable U-Net (4
   encoder/decoder levels, base width 16). **It ships with random,
   untrained weights.** To make this impossible to miss or misuse:
   - Every `LightUNet` instance has a `.trained` flag, `False` by default.
   - `load_model(weights_path=...)` only sets `.trained = True` after
     successfully loading a real weights file; without `--weights`, the CLI
     never touches `LightUNet` at all — it uses `ThresholdFloodModel`.
   - If `run_inference()` ever receives an untrained `LightUNet` (e.g. via
     direct Python use, bypassing `load_model`), it logs an explicit
     warning and labels the output `model_version: "light_unet_v1_UNTRAINED"`
     with `is_calibrated_probability: false` in the metadata sidecar — it
     is structurally impossible for untrained-model output to look
     identical to a trained result.

`inference/predict.py` is model-agnostic — swapping in a trained LightUNet
later requires no changes to preprocessing, validation, geometry conversion,
or the output contract.

---

## 5. Confidence semantics (Step 7)

| Model | `confidence` meaning | `is_calibrated_probability` |
|---|---|---|
| `ThresholdFloodModel` | Mean value of a **logistic proxy** centered on `drop_threshold_db` — monotonic in the dB drop, bounded to [0,1], **not** a statistically calibrated probability | `false` |
| `LightUNet` (trained) | Mean sigmoid output of the network over flooded pixels — a genuine model probability, calibrated only to the extent the training process calibrated it | `true` |
| `LightUNet` (untrained) | Meaningless — random-weight sigmoid output | `false`, and the model_version is suffixed `_UNTRAINED` |

---

## 6. Input validation & NoData handling (Steps 4–5)

**Validation** (`preprocessing/sar_preprocessing.py::validate_raster_pair`):
same array shape is **not** treated as proof of alignment. Before any
pixel-wise comparison, the pipeline checks CRS equality, affine-transform
equality (origin + pixel size + rotation, within floating-point tolerance),
and shape — and raises a specific, actionable `ValueError` naming exactly
which check failed rather than silently proceeding or silently resampling.

**NoData** (`preprocessing/sar_preprocessing.py`): each raster's NoData
value (or NaN/inf) is turned into a `valid_mask`. A pixel is only usable for
change detection if it's valid in **both** the pre- and post-flood image.
`valid_mask` is threaded through every stage:
- excluded from despeckle-filter local statistics and from the joint
  normalization min/max,
- forced to probability 0 in `inference/predict.py` (can never be
  classified as flooded),
- excluded from vectorization in `geo_utils.py::mask_to_geometry` (defence
  in depth, even though inference already zeroes them),
- therefore excluded from `flood_area_km2` too, since area comes from the
  vectorized geometry.

## 7. Normalization — the bug this revision fixes

An earlier version of this module normalized the pre- and post-flood dB
bands **independently** (each min-max scaled to its own [0,1] range) before
differencing them for the threshold baseline. That destroys the very signal
change-detection depends on: two images stretched to fill [0,1]
*independently* no longer preserve their real relative backscatter levels,
so a genuine flood-driven drop can be partially or fully cancelled out.

Fixed by splitting normalization into two clearly separate paths:
- **`ThresholdFloodModel`** now differences the **raw calibrated dB values**
  directly (`pre_db - post_db`) — physically meaningful, no normalization
  involved.
- **`LightUNet`** (which does benefit from normalized input) uses
  **`normalize_pair()`**, which computes ONE shared min/max across both
  images' valid pixels and applies the same scaling to both — preserving
  their relative relationship, unlike independent per-image normalization.

---

## 8. Module layout

```
ai/
├── preprocessing/
│   └── sar_preprocessing.py   Load+validate+calibrate+despeckle+joint-normalize
├── models/
│   ├── unet.py                 LightUNet (untrained) + ThresholdFloodModel (baseline)
│   └── weights/                Trained weights go here (not bundled — see §4)
├── inference/
│   └── predict.py              Model-agnostic inference → mask + confidence, NoData-aware
├── utils/
│   ├── geo_utils.py            Mask → EPSG:4326 MultiPolygon, area (km²)
│   ├── schema.py                Builds/validates the flood_predictions-shaped payload
│   └── storage_utils.py        Optional Supabase Storage upload for the mask raster
├── tests/
│   └── test_pipeline.py        Lightweight regression checks (no pytest dependency) — run directly
├── run_pipeline.py             CLI entrypoint — runs everything end-to-end
├── requirements.txt
└── sample_output/
    ├── flood_prediction.json     Example flood_predictions-contract output
    ├── flood_polygon.geojson     Example standalone polygon
    └── inference_metadata.json   Example diagnostic sidecar
```

---

## 9. CRS / units — how this module follows `DATA_FORMATS.md`

| Stage | CRS / unit | Where |
|---|---|---|
| Raw/preprocessed SAR raster | native or projected (e.g. UTM), **transient only** | `preprocessing/` |
| Vectorized mask (mid-pipeline) | source raster CRS, **transient only** | `utils/geo_utils.py::mask_to_geometry` (before reprojection) |
| Final geometry (what leaves this module) | **EPSG:4326**, always | `utils/geo_utils.py::mask_to_geometry` (after `.to_crs("EPSG:4326")`) |
| Area calculation | temporarily reprojected to an equal-area CRS (`EPSG:6933`), **never persisted** in that CRS | `utils/geo_utils.py::calculate_area_km2` |

---

## 10. Data storage principle

- This module never treats local disk as a database. `--out` is scratch
  space for a single run.
- Large binaries (the mask raster) belong in Supabase Storage's
  `flood-masks/` bucket, not in Postgres — `utils/storage_utils.py` uploads
  there when `--upload` is passed and `SUPABASE_URL` /
  `SUPABASE_SERVICE_ROLE_KEY` are set as environment variables (never
  hardcoded, never committed). Pass `--delete-local-mask-after-upload` to
  remove the local copy once the upload is confirmed, avoiding duplicate
  persistence.
- If Supabase isn't configured, the pipeline still completes successfully
  and just leaves `mask_storage_path: null`.

---

## 11. CLI reference

```
python -m ai.run_pipeline
  --pre PATH                       Pre-flood SAR GeoTIFF
  --post PATH                      Post-flood SAR GeoTIFF
  --region-id ID                   regions.id this prediction belongs to
  --flood-event-id ID              Optional flood_events.id
  --satellite-observation-id ID    Optional satellite_observations.id
  --weights PATH                   Trained LightUNet weights (.pt); omit to use the baseline
  --drop-threshold-db FLOAT        ThresholdFloodModel dB threshold (default 3.0)
  --threshold FLOAT                Probability/proxy cutoff for the binary mask (default 0.5)
  --min-region-pixels INT          Drop vectorized flood regions smaller than this (noise filtering)
  --out DIR                        Output directory (alias: --output-dir)
  --upload                         Upload mask raster to Supabase Storage
  --delete-local-mask-after-upload Delete local mask once upload is confirmed
  --demo                           Use synthetic SAR data instead of --pre/--post
```

---

## 12. Testing (Step 16)

```bash
python ai/tests/test_pipeline.py
```

Covers: missing-file input, mismatched raster pairs (both shape+origin and
CRS mismatches), NoData exclusion from stats and classification, end-to-end
mask→GeoJSON→area generation, the empty/no-flood case, and a check that area
is computed via equal-area reprojection rather than raw lat/lon degrees. All
7 checks currently pass. `--demo` mode itself doubles as an end-to-end smoke
test and is run as part of manual verification before each change lands.

---

## 13. Do not work on

This module intentionally does **not** touch:
- React / the dashboard
- FastAPI route definitions or the API contract shape
- The database schema (`flood_predictions` and all other tables are owned
  by Engineer 1 — this module only produces payloads matching the existing,
  locked contract, and deliberately keeps extra diagnostic fields in a
  separate sidecar file rather than adding columns to that payload)
- Emergency routing / the risk engine (Engineer 4)
- Any Supabase `INSERT`/`UPDATE` — uploading the *raster* to Storage is the
  one exception, and even that is optional and gated

---

## 14. Known limitations

- `ThresholdFloodModel`'s dB threshold is a documented, literature-informed
  default — **not validated against ground truth** for this specific
  region/dataset. Treat detected flood extent as indicative, not
  survey-grade.
- `LightUNet` ships **untrained** and is guarded against accidental misuse
  (see §4) — do not use it for real predictions until trained on labelled
  data.
- No automated pre/post image co-registration or resampling — mismatched
  grids are rejected with a clear error rather than silently fixed; the
  pair must already share CRS, resolution, and origin.
- No full hydrodynamic modelling, no multi-temporal (>2 image) time series
  — matches the project's explicit "Future Extensions (out of scope for
  Phase 1)" list in `docs/ARCHITECTURE.md`.
- Sentinel-1 inputs are assumed to already be analysis-ready GRD (calibrated
  to sigma-nought, terrain-corrected/geocoded) — this module does not
  implement orbit-file application, thermal-noise removal, or range-Doppler
  terrain correction.

## 15. Future improvements (not started)

- Train `LightUNet` on a labelled Sentinel-1 flood dataset once one is
  available, and validate the threshold-baseline's dB cutoff against
  ground-truthed flood extents for the chosen demo region.
- Optional: report per-flood-region confidence (rather than one scene-wide
  scalar) if Engineer 4's risk engine would benefit from it — would need
  coordination since it changes the payload shape.
