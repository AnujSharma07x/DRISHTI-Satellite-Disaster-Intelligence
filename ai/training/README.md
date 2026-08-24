# DRISHTI — AI Training Module (`ai/training/`)

Extends the existing, unmodified `ai/` inference pipeline with a training path
for `ai/models/unet.py::LightUNet`. Does not replace or duplicate anything —
see `ai/README.md` for the pipeline this plugs into.

---

## 1. Dataset selected: Sen1Floods11

**Sen1Floods11** (Cloud to Street / Google, CC BY 4.0) — the standard public
labelled Sentinel-1 flood-segmentation dataset:
[github.com/cloudtostreet/Sen1Floods11](https://github.com/cloudtostreet/Sen1Floods11).

- **HandLabeled subset**: 446 chips, 512x512, 10 m, EPSG:4326, from 11 real
  flood events worldwide.
- Per chip: `<chip>_S1Hand.tif` (Sentinel-1 GRD, VV+VH, already calibrated to
  dB) and `<chip>_LabelHand.tif` (hand-labeled water mask: `-1`=no data,
  `0`=dry, `1`=water).
- Ships official `flood_train_data.csv` / `flood_valid_data.csv` /
  `flood_test_data.csv` split lists — used automatically via `--splits-dir`
  so results stay comparable to the published baseline.

**Why this dataset is compatible with `LightUNet`, with one honest caveat:**
`LightUNet.__init__` takes `in_channels=2`. Sen1Floods11's HandLabeled subset
does **not** provide a genuine second (pre-flood) acquisition of the same
chip — only one S1 scene near the flood event, plus its label. There is no
real temporal pair to feed the model. Per the explicit instruction *"Do NOT
fabricate a second channel if the dataset does not contain a meaningful
temporal pair,"* this module does **not** duplicate the single image or
invent a synthetic pre-flood scene. Instead it uses the two channels the
dataset actually and genuinely provides for every chip — **VV and VH**
polarization — which is a real 2-channel input, matches `in_channels=2`
with zero architecture changes, and is a standard input choice in SAR
flood-mapping literature for single-scene segmentation.

**Consequence, stated plainly:** a `LightUNet` trained by this module is a
**single-scene VV/VH flood segmenter**, not a bi-temporal change detector.
The existing `ThresholdFloodModel` bi-temporal baseline is **not** replaced
and remains the pipeline's change-detection path (Phase 6 / "KEEP the
existing SAR threshold/change-detection method"). If a genuine pre/post
labelled dataset becomes available later, `dataset.py`'s loader can be
swapped without touching `train.py`'s loop, `losses.py`, `metrics.py`, or
anything in `ai/models/`, `ai/inference/`, or `ai/utils/`.

## 2. Files added

```
ai/training/
├── dataset.py     Sen1Floods11 chip discovery, patching, NoData handling,
│                  train/val/test split (official CSVs or deterministic
│                  chip-level random fallback)
├── losses.py      Masked BCE + Dice loss (invalid pixels never contribute)
├── metrics.py     Shared IoU / Dice / precision / recall accumulator
├── train.py       CLI training loop -> checkpoint (plain state_dict,
│                  loadable by the EXISTING ai.models.unet.load_model())
└── evaluate.py    CLI test-set metrics report for a trained checkpoint

ai/download/
└── sentinel1.py   Small ASF-based Sentinel-1 acquisition utility for the
                   Assam demo AOI (Phase 4/5) — search + fetch-pair

ai/tests/test_training.py   Synthetic, dependency-free-of-pytest smoke
                             tests (see §4)
```

Nothing in `ai/models/unet.py`, `ai/inference/predict.py`,
`ai/preprocessing/`, `ai/utils/`, or `ai/run_pipeline.py` was modified.

## 3. Commands, in order

```bash
# 1. Install (adds asf_search as an optional extra; torch/rasterio/etc.
#    already required by the base pipeline — see ../requirements.txt)
pip install -r ai/requirements.txt --break-system-packages

# 2. Get Sen1Floods11 HandLabeled + its official splits (see the dataset's
#    own repo/GCS bucket for current access instructions — not mirrored
#    here, per "do NOT commit huge satellite datasets")
#    Expected local layout:
#      <data_root>/<chip>_S1Hand.tif
#      <data_root>/<chip>_LabelHand.tif
#      <splits_dir>/flood_train_data.csv
#      <splits_dir>/flood_valid_data.csv
#      <splits_dir>/flood_test_data.csv

# 3. Train
python -m ai.training.train \
    --data-root  /path/to/sen1floods11/HandLabeled \
    --splits-dir /path/to/sen1floods11/splits/flood_handlabeled \
    --epochs 30 --batch-size 8 \
    --out ai/models/weights

# 4. Evaluate on the held-out test split
python -m ai.training.evaluate \
    --data-root  /path/to/sen1floods11/HandLabeled \
    --splits-dir /path/to/sen1floods11/splits/flood_handlabeled \
    --weights ai/models/weights/light_unet.pt

# 5. (Separate machine with internet + Earthdata credentials — see
#    ai/download/sentinel1.py docstring; ASF endpoints are not reachable
#    from this sandboxed dev environment)
export EARTHDATA_USERNAME=... EARTHDATA_PASSWORD=...
python -m ai.download.sentinel1 fetch-pair \
    --pre-date 2026-06-01 --post-date 2026-06-05 \
    --out data/satellite/raw

# 6. Run the EXISTING, unmodified inference entrypoint with the trained
#    checkpoint — Method A. Omit --weights to use Method B
#    (ThresholdFloodModel baseline) instead; both remain available.
python -m ai.run_pipeline \
    --pre  data/satellite/raw/pre_flood/... \
    --post data/satellite/raw/post_flood/... \
    --region-id <uuid> --weights ai/models/weights/light_unet.pt \
    --out ./output
```

⚠️ Step 6 caveat: `run_pipeline.py`'s `--pre`/`--post` path feeds
`pre_norm`/`post_norm` from a genuine bi-temporal pair into the LightUNet
input slots. A checkpoint trained per §1 was trained on VV/VH from a single
acquisition, not a temporal pair — the two channels are architecturally
identical (2 x float32 in [0,1]) so nothing crashes, but semantically the
model expects VV/VH, not pre/post. For a real Assam demo, either (a) feed
same-date VV/VH bands into the `--pre`/`--post` slots instead of a temporal
pair, or (b) use `ThresholdFloodModel` (no `--weights`) for genuine
bi-temporal change detection, which remains the recommended default per
Phase 6. This mismatch is a direct, documented consequence of the dataset
limitation in §1, not a bug in `run_pipeline.py`.

## 4. Testing

```bash
python ai/tests/test_training.py
```

No real Sen1Floods11 download or network access is available in this
development environment, so these tests generate small SYNTHETIC chips
(clearly labelled, same spirit as `run_pipeline.py --demo`) to verify, end
to end:

1. Chip discovery + NoData-aware loading (`dataset.py`)
2. Patch extraction skips all-nodata patches
3. `build_datasets()` produces normalized `[0,1]` patches with a correct
   deterministic split
4. Masked BCE+Dice loss is provably invariant to invalid-pixel values
5. IoU/Dice/precision/recall match a hand-computed confusion matrix
6. A full (tiny) training loop runs and saves a checkpoint
7. **Integration**: that checkpoint loads via the existing, unmodified
   `ai.models.unet.load_model()` and runs through the existing, unmodified
   `ai.inference.predict.run_inference()` — proving new training code
   produces output the old inference code can actually consume, not just
   that training "runs".

All 8 checks currently pass. A full CLI smoke run (`python -m
ai.training.train ...` → `python -m ai.training.evaluate ...` → `python -m
ai.run_pipeline --demo --weights ...`) was also run manually against a
synthetic mini-dataset and completed without error.

## 5. Known limitations / blockers

- **No real training run performed.** This environment has no access to
  Sen1Floods11 (needs external download) or ASF/Earthdata (not in the
  network allowlist), so no real IoU/Dice numbers exist yet — only the
  synthetic smoke-test numbers in §4, which are not meaningful accuracy
  figures. Running §3 steps 2–4 on a machine with real data access is the
  next step before any real metrics can be reported.
- **VV/VH vs pre/post mismatch** at inference time — see the §3 step 6
  caveat. Not fabricating a second channel from a single-pair dataset was
  an explicit constraint; this is the direct, honest consequence.
- `base_width` for a checkpoint MUST stay at `LightUNet`'s default (16) —
  `ai.models.unet.load_model()` does not expose a `base_width` override, so
  a checkpoint trained with any other width cannot be loaded by the
  existing inference code without also changing `load_model()` (out of
  scope for this addition — see `train.py --help`).
- Patch-based training with `random_crops_per_chip` currently redraws the
  same fixed set of random crops once per dataset build (not re-sampled
  every epoch) — a simple, working choice; resampling crops per-epoch would
  be a straightforward future improvement, not implemented here to keep
  scope tight.
