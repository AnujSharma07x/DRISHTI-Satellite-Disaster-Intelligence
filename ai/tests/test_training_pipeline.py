"""
test_training_pipeline.py
==========================
Lightweight, dependency-free-beyond-torch/rasterio regression checks for the
Engineer 2 training pipeline (`ai/training/`), matching the style of
`ai/tests/test_pipeline.py` (plain assert + a runner, no pytest dependency).

Covers:
    1. S1/Label pairing by event ID (correct + mismatch detection)
    2. NoData / label==-1 valid_mask computation
    3. Masked loss excludes label==-1 pixels from gradient signal
    4. Masked loss excludes NaN-input (already-masked) pixels
    5. One training batch (forward + backward + optimizer step)
    6. One validation batch (evaluate_dataset on a tiny dataset)

Run:
    python ai/tests/test_training_pipeline.py
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import traceback

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import torch
import rasterio
from rasterio.transform import from_origin

from ai.models.unet import LightUNet
from ai.training.dataset import (
    find_sample_pairs,
    resolve_split,
    load_sample,
    compute_normalization_stats,
    Sen1Floods11Dataset,
    SamplePair,
)
from ai.training.losses import MaskedBCEDiceLoss, masked_bce_loss, masked_dice_loss
from ai.training.evaluate import evaluate_dataset


def _write_pair(s1_dir, label_dir, event_id, h=32, w=32, seed=0, nodata_strip=True):
    rng = np.random.default_rng(seed)
    transform = from_origin(90.0, 20.0, 0.0001, 0.0001)

    vv = rng.normal(-12, 1, size=(h, w)).astype("float32")
    vh = rng.normal(-18, 1, size=(h, w)).astype("float32")
    label = np.zeros((h, w), dtype="int16")
    label[h // 4: h // 2, w // 4: w // 2] = 1
    vv[h // 4: h // 2, w // 4: w // 2] -= 8
    vh[h // 4: h // 2, w // 4: w // 2] -= 8

    if nodata_strip:
        vv[0:4, :] = np.nan
        vh[0:4, :] = np.nan
        label[0:4, :] = -1

    with rasterio.open(f"{s1_dir}/{event_id}_S1Hand.tif", "w", driver="GTiff",
                        height=h, width=w, count=2, dtype="float32",
                        crs="EPSG:4326", transform=transform, nodata=np.nan) as dst:
        dst.write(vv, 1)
        dst.write(vh, 2)

    with rasterio.open(f"{label_dir}/{event_id}_LabelHand.tif", "w", driver="GTiff",
                        height=h, width=w, count=1, dtype="int16",
                        crs="EPSG:4326", transform=transform, nodata=-1) as dst:
        dst.write(label, 1)


def _make_fixture_dataset(tmpdir, event_ids):
    root = os.path.join(tmpdir, "sen1floods11", "v1.1")
    s1_dir = os.path.join(root, "data", "flood_events", "HandLabeled", "S1Hand")
    label_dir = os.path.join(root, "data", "flood_events", "HandLabeled", "LabelHand")
    os.makedirs(s1_dir, exist_ok=True)
    os.makedirs(label_dir, exist_ok=True)
    for i, event_id in enumerate(event_ids):
        _write_pair(s1_dir, label_dir, event_id, seed=i)
    return root, s1_dir, label_dir


# ---------------------------------------------------------------------------
# 1. Pairing
# ---------------------------------------------------------------------------

def test_pairing_correct(tmpdir):
    root, _, _ = _make_fixture_dataset(tmpdir, ["Bolivia_1", "Bolivia_2", "Mekong_1"])
    pairs = find_sample_pairs(root)
    ids = sorted(p.event_id for p in pairs)
    assert ids == ["Bolivia_1", "Bolivia_2", "Mekong_1"]
    for p in pairs:
        assert p.event_id in p.s1_path
        assert p.event_id in p.label_path


def test_pairing_detects_mismatch(tmpdir):
    root, s1_dir, label_dir = _make_fixture_dataset(tmpdir, ["Bolivia_1", "Bolivia_2"])
    # Remove one label file so Bolivia_2's S1 has no matching label.
    os.remove(os.path.join(label_dir, "Bolivia_2_LabelHand.tif"))
    try:
        find_sample_pairs(root)
        assert False, "expected ValueError for mismatched pair"
    except ValueError as exc:
        assert "Bolivia_2" in str(exc)


# ---------------------------------------------------------------------------
# 2. Splits (event-level fallback, no leakage)
# ---------------------------------------------------------------------------

def test_fallback_split_has_no_region_leakage(tmpdir):
    event_ids = [f"{region}_{i}" for region in ("A", "B", "C", "D", "E", "F") for i in range(3)]
    root, _, _ = _make_fixture_dataset(tmpdir, event_ids)
    pairs = find_sample_pairs(root)
    split = resolve_split(root, pairs, seed=1)
    assert split.source == "fallback-event-level"

    def regions_of(ids):
        return {i.rsplit("_", 1)[0] for i in ids}

    r_train, r_val, r_test = regions_of(split.train), regions_of(split.val), regions_of(split.test)
    assert not (r_train & r_val), "train/val region leakage"
    assert not (r_train & r_test), "train/test region leakage"
    assert not (r_val & r_test), "val/test region leakage"
    assert len(split.train) + len(split.val) + len(split.test) == len(event_ids)


# ---------------------------------------------------------------------------
# 3. valid_mask / NoData handling
# ---------------------------------------------------------------------------

def test_valid_mask_excludes_nan_and_label_nodata(tmpdir):
    root, s1_dir, label_dir = _make_fixture_dataset(tmpdir, ["X_1"])
    pairs = find_sample_pairs(root)
    sample = load_sample(pairs[0])

    assert sample.valid_mask[0:4, :].sum() == 0, "NaN VV/VH rows must be invalid"
    assert sample.valid_mask[4:, :].all(), "non-NoData rows must be valid"
    # label -1 was never turned into class 0 at those rows:
    assert (sample.label[0:4, :] == -1).all()


def test_normalization_stats_exclude_invalid_pixels(tmpdir):
    root, _, _ = _make_fixture_dataset(tmpdir, ["X_1", "X_2"])
    pairs = find_sample_pairs(root)
    stats = compute_normalization_stats(pairs)
    # Sanity: stats should be close to the true generating distribution
    # (mean ~ -12 for VV, ~ -18 for VH), not skewed by NaNs (which would
    # have produced NaN stats if leaked through).
    assert np.isfinite(stats.vv_mean) and np.isfinite(stats.vv_std)
    assert np.isfinite(stats.vh_mean) and np.isfinite(stats.vh_std)
    assert -16 < stats.vv_mean < -8
    assert -22 < stats.vh_mean < -14


# ---------------------------------------------------------------------------
# 4/5. Masked loss correctness
# ---------------------------------------------------------------------------

def test_masked_bce_ignores_invalid_pixels():
    torch.manual_seed(0)
    logits = torch.randn(1, 1, 4, 4)
    target = torch.zeros(1, 1, 4, 4)
    valid = torch.ones(1, 1, 4, 4)

    loss_all_valid = masked_bce_loss(logits, target, valid)

    # Now corrupt an "invalid" region's target to look like strong positive
    # signal (as label==-1 pixels do in this dataset) and mark it invalid.
    # If masking works, the loss must be UNCHANGED apart from the removed
    # pixels' contribution being gone - i.e. it must not chase the corrupted
    # target at all.
    target_corrupted = target.clone()
    target_corrupted[:, :, 0, :] = 1.0  # looks like flood
    valid_masked = valid.clone()
    valid_masked[:, :, 0, :] = 0.0  # ...but marked invalid

    loss_masked = masked_bce_loss(logits, target_corrupted, valid_masked)
    loss_only_valid_rows = masked_bce_loss(logits[:, :, 1:, :], target[:, :, 1:, :], valid[:, :, 1:, :])

    assert torch.isclose(loss_masked, loss_only_valid_rows, atol=1e-5), (
        "masked BCE must be identical to computing loss over only the valid "
        "rows, regardless of what garbage target values sit at invalid pixels"
    )
    assert not torch.isclose(loss_masked, loss_all_valid), "sanity: corrupting target should change the naive (unmasked) loss"


def test_masked_dice_ignores_invalid_pixels():
    torch.manual_seed(0)
    logits = torch.randn(2, 1, 6, 6)
    target = (torch.rand(2, 1, 6, 6) > 0.7).float()
    valid = torch.ones(2, 1, 6, 6)
    valid[:, :, 0, :] = 0.0  # top row invalid

    target_corrupted = target.clone()
    target_corrupted[:, :, 0, :] = 1.0  # garbage at invalid row

    loss_masked = masked_dice_loss(logits, target_corrupted, valid)
    loss_reference = masked_dice_loss(logits, target, valid)  # same valid region, clean target elsewhere
    assert torch.isclose(loss_masked, loss_reference, atol=1e-5), (
        "Dice loss must not be affected by target values at invalid pixels"
    )


def test_combined_loss_raises_on_all_invalid_batch():
    criterion = MaskedBCEDiceLoss()
    logits = torch.randn(1, 1, 4, 4)
    target = torch.zeros(1, 1, 4, 4)
    valid = torch.zeros(1, 1, 4, 4)  # nothing valid
    try:
        criterion(logits, target, valid)
        assert False, "expected ValueError for all-invalid batch"
    except ValueError:
        pass


# ---------------------------------------------------------------------------
# 6/7. One training batch, one validation batch
# ---------------------------------------------------------------------------

def test_one_training_batch_updates_weights(tmpdir):
    event_ids = [f"R{r}_{i}" for r in range(4) for i in range(2)]
    root, _, _ = _make_fixture_dataset(tmpdir, event_ids)
    pairs = find_sample_pairs(root)
    stats = compute_normalization_stats(pairs)

    ds = Sen1Floods11Dataset(pairs, stats, patch_size=None, seed=0)
    from torch.utils.data import DataLoader
    loader = DataLoader(ds, batch_size=2, shuffle=True)

    model = LightUNet(in_channels=2, base_width=4)  # tiny width for a fast test
    optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)
    criterion = MaskedBCEDiceLoss()

    before = [p.clone() for p in model.parameters()]

    images, labels, valid = next(iter(loader))
    labels = labels.unsqueeze(1)
    valid = valid.unsqueeze(1)

    optimizer.zero_grad()
    logits = model(images)
    loss, components = criterion(logits, labels, valid)
    loss.backward()
    optimizer.step()

    after = list(model.parameters())
    changed = any(not torch.equal(b, a) for b, a in zip(before, after))
    assert changed, "model parameters must change after one training step"
    assert torch.isfinite(loss)
    assert "bce" in components and "dice" in components


def test_one_validation_batch(tmpdir):
    event_ids = [f"R{r}_{i}" for r in range(3) for i in range(2)]
    root, _, _ = _make_fixture_dataset(tmpdir, event_ids)
    pairs = find_sample_pairs(root)
    stats = compute_normalization_stats(pairs)
    ds = Sen1Floods11Dataset(pairs, stats, patch_size=None, seed=0)

    model = LightUNet(in_channels=2, base_width=4)
    metrics = evaluate_dataset(model, ds, device="cpu", batch_size=2)

    for key in ("iou", "dice_f1", "precision", "recall", "n_samples"):
        assert key in metrics
    assert 0.0 <= metrics["iou"] <= 1.0
    assert metrics["n_samples"] == len(event_ids)


TESTS = [
    test_pairing_correct,
    test_pairing_detects_mismatch,
    test_fallback_split_has_no_region_leakage,
    test_valid_mask_excludes_nan_and_label_nodata,
    test_normalization_stats_exclude_invalid_pixels,
    test_masked_bce_ignores_invalid_pixels,
    test_masked_dice_ignores_invalid_pixels,
    test_combined_loss_raises_on_all_invalid_batch,
    test_one_training_batch_updates_weights,
    test_one_validation_batch,
]


def main():
    passed, failed = 0, 0
    for test_fn in TESTS:
        name = test_fn.__name__
        needs_tmpdir = "tmpdir" in test_fn.__code__.co_varnames[: test_fn.__code__.co_argcount]
        try:
            if needs_tmpdir:
                tmpdir = tempfile.mkdtemp(prefix="drishti_training_test_")
                try:
                    test_fn(tmpdir)
                finally:
                    shutil.rmtree(tmpdir, ignore_errors=True)
            else:
                test_fn()
            print(f"PASS  {name}")
            passed += 1
        except Exception as exc:  # noqa: BLE001
            print(f"FAIL  {name}: {exc}")
            traceback.print_exc()
            failed += 1

    print(f"\n{passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
