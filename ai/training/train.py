#!/usr/bin/env python3
"""
train.py
========
Trains the EXISTING `ai/models/unet.py::LightUNet` on Sen1Floods11 (VV, VH)
patches (see `dataset.py` docstring for why VV/VH rather than a fabricated
pre/post pair). Does not modify `LightUNet`, `predict.py`, or any other
already-working module - it only produces a `state_dict` checkpoint in the
exact format `ai.models.unet.load_model(weights_path=...)` already expects,
so the existing inference pipeline picks it up with zero changes.

This script does NOT replace or compete with `ai/run_pipeline.py`. That
remains the single inference entrypoint (Method A: trained LightUNet via
`--weights`, Method B: `ThresholdFloodModel` baseline, unchanged - Phase 6).

Usage
-----
    python -m ai.training.train \\
        --data-root /path/to/sen1floods11/HandLabeled \\
        --splits-dir /path/to/sen1floods11/splits/flood_handlabeled \\
        --epochs 30 \\
        --batch-size 8 \\
        --out ai/models/weights

Quick smoke run (tiny synthetic-friendly settings, see
`ai/tests/test_training.py` for a fully synthetic end-to-end version that
needs no downloaded dataset at all):

    python -m ai.training.train --data-root ./mini_data --epochs 1 \\
        --patch-size 64 --random-crops-per-chip 4 --batch-size 2 --out /tmp/ckpt
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

try:
    import torch
    from torch.utils.data import DataLoader
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "torch is required for ai/training/train.py. "
        "Install with: pip install torch --break-system-packages"
    ) from exc

from ai.models.unet import LightUNet
from ai.training.dataset import build_datasets
from ai.training.losses import BCEDiceLoss
from ai.training.metrics import ConfusionAccumulator, binarize

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("drishti.ai.training.train")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Train LightUNet on Sen1Floods11 VV/VH patches")
    p.add_argument("--data-root", required=True, help="Root dir containing Sen1Floods11 HandLabeled *_S1Hand.tif / *_LabelHand.tif")
    p.add_argument("--splits-dir", default=None, help="Dir with official flood_train/valid/test_data.csv; omit for a random chip-level split")
    p.add_argument("--patch-size", type=int, default=256)
    p.add_argument("--random-crops-per-chip", type=int, default=8, help="Random train-time crops drawn per chip per dataset build (not per epoch)")
    p.add_argument("--val-frac", type=float, default=0.15, help="Only used when --splits-dir is omitted")
    p.add_argument("--test-frac", type=float, default=0.15, help="Only used when --splits-dir is omitted")
    p.add_argument("--epochs", type=int, default=30)
    p.add_argument("--batch-size", type=int, default=8)
    p.add_argument("--lr", type=float, default=1e-3)
    p.add_argument(
        "--base-width", type=int, default=16,
        help=(
            "LightUNet base_width. WARNING: ai.models.unet.load_model() "
            "always reconstructs LightUNet with its class default "
            "(base_width=16, no override param) before loading the "
            "state_dict, so a checkpoint trained with any other value "
            "will fail to load at inference time via the existing, "
            "unmodified pipeline. Leave this at 16 unless load_model() is "
            "also updated (out of scope here - Engineer 2 owns ai/, but "
            "load_model()'s signature is part of the existing, working "
            "contract and is not being changed by this training addition)."
        ),
    )
    p.add_argument("--num-workers", type=int, default=2)
    p.add_argument("--out", default="ai/models/weights", help="Checkpoint output directory")
    p.add_argument("--checkpoint-name", default="light_unet.pt")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--device", default="cuda" if _cuda_available() else "cpu")
    p.add_argument("--limit-train-batches", type=int, default=None, help="Debug/smoke-test aid: cap batches/epoch")
    return p.parse_args()


def _cuda_available() -> bool:
    try:
        return torch.cuda.is_available()
    except Exception:  # pragma: no cover
        return False


def run_epoch(model, loader, criterion, optimizer, device, train: bool, limit_batches=None) -> dict:
    model.train(mode=train)
    total_loss, n_batches = 0.0, 0
    acc = ConfusionAccumulator()

    context = torch.enable_grad() if train else torch.no_grad()
    with context:
        for i, (bands, label, valid) in enumerate(loader):
            if limit_batches is not None and i >= limit_batches:
                break
            bands, label, valid = bands.to(device), label.to(device), valid.to(device)

            if train:
                optimizer.zero_grad()
            logits = model(bands)
            loss = criterion(logits, label, valid)
            if train:
                loss.backward()
                optimizer.step()

            total_loss += float(loss.detach())
            n_batches += 1
            acc.update(binarize(logits.detach()), label, valid)

    metrics = acc.compute()
    metrics["loss"] = round(total_loss / max(n_batches, 1), 5)
    return metrics


def main() -> int:
    args = parse_args()
    torch.manual_seed(args.seed)

    if args.base_width != 16:
        logger.warning(
            "base_width=%d != 16: the resulting checkpoint will NOT load "
            "via the existing ai.models.unet.load_model() (see --help). "
            "Only use a non-default width for local experimentation.",
            args.base_width,
        )

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    device = args.device
    logger.info("Device: %s", device)

    logger.info("Building datasets from %s ...", args.data_root)
    train_ds, val_ds, test_ds = build_datasets(
        data_root=args.data_root,
        splits_dir=args.splits_dir,
        patch_size=args.patch_size,
        random_crops_per_chip=args.random_crops_per_chip,
        val_frac=args.val_frac,
        test_frac=args.test_frac,
        seed=args.seed,
    )
    logger.info("train=%d val=%d test=%d patches", len(train_ds), len(val_ds), len(test_ds))

    train_loader = DataLoader(train_ds, batch_size=args.batch_size, shuffle=True, num_workers=args.num_workers, drop_last=False)
    val_loader = DataLoader(val_ds, batch_size=args.batch_size, shuffle=False, num_workers=args.num_workers)

    # in_channels=2 (VV, VH) matches LightUNet's existing default - see
    # dataset.py docstring for why this is 2 real channels, not a
    # fabricated pre/post pair.
    model = LightUNet(in_channels=2, base_width=args.base_width).to(device)
    criterion = BCEDiceLoss()
    optimizer = torch.optim.Adam(model.parameters(), lr=args.lr)

    best_val_iou = -1.0
    best_ckpt_path = out_dir / args.checkpoint_name
    history = []

    for epoch in range(1, args.epochs + 1):
        t0 = time.time()
        train_metrics = run_epoch(model, train_loader, criterion, optimizer, device, train=True, limit_batches=args.limit_train_batches)
        val_metrics = run_epoch(model, val_loader, criterion, optimizer, device, train=False)
        elapsed = time.time() - t0

        logger.info(
            "epoch %d/%d (%.1fs) train_loss=%.4f train_iou=%.4f | val_loss=%.4f val_iou=%.4f val_dice=%.4f",
            epoch, args.epochs, elapsed,
            train_metrics["loss"], train_metrics["iou"],
            val_metrics["loss"], val_metrics["iou"], val_metrics["dice"],
        )
        history.append({"epoch": epoch, "train": train_metrics, "val": val_metrics})

        if val_metrics["iou"] > best_val_iou:
            best_val_iou = val_metrics["iou"]
            # Plain state_dict, exactly what ai.models.unet.load_model()
            # already expects via torch.load(weights_path) +
            # model.load_state_dict(...) - no format change needed on the
            # inference side.
            torch.save(model.state_dict(), best_ckpt_path)
            logger.info("  -> new best (val_iou=%.4f), saved to %s", best_val_iou, best_ckpt_path)

    history_path = out_dir / "training_history.json"
    with open(history_path, "w") as f:
        json.dump({"args": vars(args), "history": history, "best_val_iou": best_val_iou}, f, indent=2)

    logger.info("=" * 60)
    logger.info("Training complete. Best val IoU: %.4f", best_val_iou)
    logger.info("Best checkpoint: %s", best_ckpt_path)
    logger.info("History:         %s", history_path)
    logger.info("Run ai/training/evaluate.py against the held-out test split for a final report.")
    logger.info("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
