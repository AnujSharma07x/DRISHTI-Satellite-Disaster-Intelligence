"""
dataset.py
==========
Training-data loader for `ai/models/unet.py::LightUNet`.

Dataset selected: **Sen1Floods11** (Cloud to Street / Google, CC BY 4.0),
the standard publicly available labelled Sentinel-1 flood-segmentation
dataset. See `ai/training/README.md` (or the top-level training plan
deliverable) for the full justification. Summary:

    - 446 hand-labelled 512x512 chips across 11 real flood events
      ("HandLabeled" subset).
    - Each chip ships:
        <chip>_S1Hand.tif     Sentinel-1 GRD, 2 bands (VV, VH), already
                               calibrated to dB, 10 m, EPSG:4326.
        <chip>_LabelHand.tif  1 band, values {-1: no data, 0: dry, 1: water}.
    - Distributed as Cloud-Optimized GeoTIFFs; small enough to keep locally
      per-chip (do NOT commit the dataset itself to this repo - see
      ARCHITECTURE.md #7 / DATA_FORMATS.md #2, large binaries never live in
      git).

IMPORTANT - why this file does NOT feed LightUNet a "pre/post" pair
---------------------------------------------------------------------
`LightUNet.__init__` expects `in_channels=2` and `inference/predict.py`
was originally written assuming those two channels are (pre-flood,
post-flood) SAR. Sen1Floods11's HandLabeled subset does **not** provide a
genuine pre-flood acquisition of the same chip - only a single S1
acquisition taken during/near the flood event, plus its ground-truth
label. There is no meaningful temporal pair to give the model.

Per the explicit instruction "Do NOT fabricate a second channel if the
dataset does not contain a meaningful temporal pair", this loader does
**not** duplicate the single image into two identical channels and does
**not** invent a synthetic "pre-flood" scene. Instead it uses the two
channels Sen1Floods11 actually provides for every chip: **VV and VH**
polarizations from the same acquisition. This is a real, physically
distinct 2-channel input (not fabricated data), it requires zero changes
to `LightUNet`'s `in_channels=2` architecture, and it is a standard input
choice in the SAR flood-mapping literature (dual-pol single-scene
segmentation, as opposed to bi-temporal change detection).

Consequence (documented limitation, not hidden): a LightUNet trained this
way is a **single-scene VV/VH flood segmenter**, not a change-detection
model. The existing `ThresholdFloodModel` bi-temporal baseline
(`ai/models/unet.py`) remains the pipeline's change-detection path and is
NOT replaced - see `ai/training/train.py` module docstring and Phase 6 of
the training plan ("KEEP the existing SAR threshold/change-detection
method").

This module does not duplicate anything already in `ai/preprocessing` or
`ai/utils` - where those already do the job (joint min-max normalization),
this file calls them directly instead of re-implementing.
"""

from __future__ import annotations

import csv
import logging
import os
import random
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

import numpy as np

try:
    import rasterio
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "rasterio is required for ai/training/dataset.py. "
        "Install with: pip install rasterio --break-system-packages"
    ) from exc

try:
    import torch
    from torch.utils.data import Dataset
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "torch is required for ai/training/dataset.py. "
        "Install with: pip install torch --break-system-packages"
    ) from exc

# Reuse the existing, already-working joint-normalization logic instead of
# re-implementing it (see module docstring - "Do not duplicate
# functionality that already exists"). The function is generic: it jointly
# min-max scales two same-shaped bands over their valid pixels together.
# Here it is applied to (VV, VH) rather than (pre, post); the maths are
# identical, only the physical meaning of the two channels differs.
from ai.preprocessing.sar_preprocessing import normalize_pair

logger = logging.getLogger("drishti.ai.training.dataset")

LABEL_NODATA = -1  # Sen1Floods11 LabelHand convention: -1 = no data


@dataclass
class ChipPair:
    """One Sen1Floods11 chip: paths to its S1 (VV, VH) image and label."""

    chip_id: str
    image_path: str
    label_path: str


def discover_chips(data_root: str, image_suffix: str = "_S1Hand.tif", label_suffix: str = "_LabelHand.tif") -> List[ChipPair]:
    """Scan `data_root` for `<chip>_S1Hand.tif` / `<chip>_LabelHand.tif`
    pairs (the Sen1Floods11 HandLabeled naming convention). Used when no
    explicit split CSV is supplied.

    Fails loudly (not silently skips) if an image has no matching label or
    vice versa, so a partially-downloaded dataset is caught early rather
    than silently training on fewer chips than expected.
    """
    root = Path(data_root)
    images = sorted(root.rglob(f"*{image_suffix}"))
    if not images:
        raise FileNotFoundError(
            f"No files matching *{image_suffix} found under {data_root!r}. "
            f"Expected the Sen1Floods11 HandLabeled layout, e.g. "
            f"'Bolivia_103757_S1Hand.tif'."
        )

    chips = []
    missing_labels = []
    for image_path in images:
        chip_id = image_path.name[: -len(image_suffix)]
        label_path = image_path.parent / f"{chip_id}{label_suffix}"
        if not label_path.exists():
            missing_labels.append(str(label_path))
            continue
        chips.append(ChipPair(chip_id=chip_id, image_path=str(image_path), label_path=str(label_path)))

    if missing_labels:
        raise FileNotFoundError(
            f"{len(missing_labels)} image(s) have no matching label file, e.g. "
            f"{missing_labels[0]!r}. Dataset download may be incomplete."
        )

    logger.info("Discovered %d chip pairs under %s", len(chips), data_root)
    return chips


def load_split_csv(csv_path: str, data_root: str) -> List[ChipPair]:
    """Load chip pairs from a Sen1Floods11-style split CSV: two columns,
    `image_filename,label_filename`, paths relative to `data_root`. This
    matches the official `flood_train_data.csv` / `flood_valid_data.csv` /
    `flood_test_data.csv` split files shipped with the dataset, so the
    documented train/val/test split is respected rather than re-randomized
    (avoids leaking the same flood event across splits).
    """
    chips = []
    with open(csv_path, newline="") as f:
        reader = csv.reader(f)
        for row in reader:
            if not row or row[0].startswith("#"):
                continue
            image_rel, label_rel = row[0].strip(), row[1].strip()
            chip_id = Path(image_rel).name.replace("_S1Hand.tif", "")
            chips.append(
                ChipPair(
                    chip_id=chip_id,
                    image_path=os.path.join(data_root, image_rel),
                    label_path=os.path.join(data_root, label_rel),
                )
            )
    if not chips:
        raise ValueError(f"Split CSV {csv_path!r} contained no rows.")
    return chips


def random_split_chips(chips: Sequence[ChipPair], val_frac: float = 0.15, test_frac: float = 0.15, seed: int = 42) -> Tuple[List[ChipPair], List[ChipPair], List[ChipPair]]:
    """Deterministic fallback split used only when no official split CSVs
    are available. Splits by CHIP (not by patch) so patches from the same
    chip never leak across train/val/test.
    """
    chips = list(chips)
    rng = random.Random(seed)
    rng.shuffle(chips)
    n = len(chips)
    n_val = max(1, int(n * val_frac)) if n > 2 else 0
    n_test = max(1, int(n * test_frac)) if n > 2 else 0
    test = chips[:n_test]
    val = chips[n_test : n_test + n_val]
    train = chips[n_test + n_val :]
    if not train:
        raise ValueError(
            f"Split produced an empty train set from {n} chips - need more "
            f"data or smaller val_frac/test_frac."
        )
    return train, val, test


def _load_chip(image_path: str, label_path: str) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Load one chip's (VV, VH) bands and its label.

    Returns:
        bands: float32 array, shape (2, H, W) - band 0 = VV (dB), band 1 = VH (dB)
        label: float32 array, shape (H, W), values {0, 1} (water=1)
        valid: bool array, shape (H, W) - True where the label is NOT the
            dataset's -1 no-data sentinel (LABEL_NODATA)
    """
    with rasterio.open(image_path) as src:
        if src.count < 2:
            raise ValueError(
                f"{image_path!r} has only {src.count} band(s); Sen1Floods11 "
                f"S1Hand chips must have 2 (VV, VH)."
            )
        bands = src.read([1, 2]).astype("float32")

    with rasterio.open(label_path) as src:
        label_raw = src.read(1).astype("float32")

    valid = label_raw != LABEL_NODATA
    label = np.clip(label_raw, 0.0, 1.0)  # nodata sentinel clipped out of range; masked by `valid` anyway
    return bands, label, valid


def _extract_patches(
    bands: np.ndarray, label: np.ndarray, valid: np.ndarray,
    patch_size: int, stride: Optional[int], random_crops: int = 0, rng: Optional[random.Random] = None,
):
    """Slice a (2, H, W) image + (H, W) label/valid pair into `patch_size` x
    `patch_size` patches.

    - `stride` given: deterministic sliding-window patches (used for
      val/test, so evaluation is reproducible and covers the whole chip).
    - `random_crops` given instead: that many random `patch_size` crops
      (used for train, for cheap data augmentation via random spatial
      offsets). Patches with zero valid pixels are skipped either way -
      training/evaluating on an all-nodata patch is meaningless.
    """
    _, h, w = bands.shape
    patches = []

    def _maybe_add(y, x):
        b = bands[:, y : y + patch_size, x : x + patch_size]
        l = label[y : y + patch_size, x : x + patch_size]
        v = valid[y : y + patch_size, x : x + patch_size]
        if b.shape[1] != patch_size or b.shape[2] != patch_size:
            return  # partial edge patch - dropped rather than zero-padded (avoids fake nodata-as-valid pixels)
        if not v.any():
            return
        patches.append((b, l, v))

    if stride is not None:
        for y in range(0, max(h - patch_size, 0) + 1, stride):
            for x in range(0, max(w - patch_size, 0) + 1, stride):
                _maybe_add(y, x)
    if random_crops:
        rng = rng or random.Random()
        max_y, max_x = max(h - patch_size, 0), max(w - patch_size, 0)
        for _ in range(random_crops):
            y = rng.randint(0, max_y) if max_y > 0 else 0
            x = rng.randint(0, max_x) if max_x > 0 else 0
            _maybe_add(y, x)

    return patches


class Sen1Floods11Patches(Dataset):
    """PyTorch Dataset of `patch_size` x `patch_size` (VV, VH) patches with
    flood labels, drawn from a list of `ChipPair`s.

    Normalization: each chip's VV/VH bands are jointly min-max normalized
    (via the existing `normalize_pair`) BEFORE patching, so a patch's
    intensity stays comparable to the rest of its source chip - patch-level
    normalization would let two patches of the same physical scene get
    scaled differently, which is undesirable.
    """

    def __init__(
        self,
        chips: Sequence[ChipPair],
        patch_size: int = 256,
        stride: Optional[int] = None,
        random_crops_per_chip: int = 0,
        seed: int = 42,
    ):
        if stride is None and not random_crops_per_chip:
            raise ValueError("Provide either `stride` (deterministic) or `random_crops_per_chip` (train-time).")

        self._rng = random.Random(seed)
        self.samples = []  # list of (bands_patch[2,H,W] float32, label_patch[H,W] float32, valid_patch[H,W] bool)

        for chip in chips:
            bands, label, valid = _load_chip(chip.image_path, chip.label_path)
            if not valid.any():
                logger.warning("Chip %s is entirely no-data - skipping.", chip.chip_id)
                continue
            vv_norm, vh_norm = normalize_pair(bands[0], bands[1], valid)
            norm_bands = np.stack([vv_norm, vh_norm], axis=0)

            patches = _extract_patches(
                norm_bands, label, valid,
                patch_size=patch_size, stride=stride,
                random_crops=random_crops_per_chip, rng=self._rng,
            )
            self.samples.extend(patches)

        if not self.samples:
            raise ValueError(
                "No usable patches were extracted from the given chips - "
                "check patch_size against chip dimensions and that labels "
                "aren't entirely no-data."
            )
        logger.info("Built %d patches from %d chips (patch_size=%d)", len(self.samples), len(chips), patch_size)

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, idx: int):
        bands, label, valid = self.samples[idx]
        return (
            torch.from_numpy(bands.copy()).float(),          # (2, P, P)
            torch.from_numpy(label.copy()).float().unsqueeze(0),   # (1, P, P)
            torch.from_numpy(valid.copy()).float().unsqueeze(0),   # (1, P, P) - 1.0 = valid
        )


def build_datasets(
    data_root: str,
    splits_dir: Optional[str] = None,
    patch_size: int = 256,
    val_stride: Optional[int] = None,
    random_crops_per_chip: int = 8,
    val_frac: float = 0.15,
    test_frac: float = 0.15,
    seed: int = 42,
) -> Tuple[Sen1Floods11Patches, Sen1Floods11Patches, Sen1Floods11Patches]:
    """Convenience entry point used by `train.py` / `evaluate.py`.

    If `splits_dir` is given, expects `flood_train_data.csv`,
    `flood_valid_data.csv`, `flood_test_data.csv` inside it (the official
    Sen1Floods11 split files). Otherwise falls back to a deterministic
    chip-level random split over everything found under `data_root`.
    """
    val_stride = val_stride or patch_size  # non-overlapping by default

    if splits_dir:
        train_chips = load_split_csv(os.path.join(splits_dir, "flood_train_data.csv"), data_root)
        val_chips = load_split_csv(os.path.join(splits_dir, "flood_valid_data.csv"), data_root)
        test_chips = load_split_csv(os.path.join(splits_dir, "flood_test_data.csv"), data_root)
    else:
        logger.warning(
            "No --splits-dir given - falling back to a random chip-level "
            "split (seed=%d). Prefer the official Sen1Floods11 split CSVs "
            "when available, so results are comparable to published "
            "baselines.", seed,
        )
        all_chips = discover_chips(data_root)
        train_chips, val_chips, test_chips = random_split_chips(all_chips, val_frac, test_frac, seed)

    train_ds = Sen1Floods11Patches(train_chips, patch_size=patch_size, random_crops_per_chip=random_crops_per_chip, seed=seed)
    val_ds = Sen1Floods11Patches(val_chips, patch_size=patch_size, stride=val_stride, seed=seed)
    test_ds = Sen1Floods11Patches(test_chips, patch_size=patch_size, stride=val_stride, seed=seed)
    return train_ds, val_ds, test_ds
