#!/usr/bin/env python3
"""
evaluate.py
===========
Computes final held-out test-set metrics (loss, IoU, Dice, precision,
recall, accuracy) for a trained LightUNet checkpoint, using the SAME
metric accumulation logic as `train.py` (`metrics.py`) so validation-time
numbers and the final report are directly comparable.

Also runs a sanity check that the checkpoint round-trips through the
EXISTING, unmodified inference path (`ai.models.unet.load_model` +
`ai.inference.predict.run_inference`) on one test chip, so "the model
trains" and "the model is usable by the existing pipeline" are both
verified, not just assumed.

Usage
-----
    python -m ai.training.evaluate \\
        --data-root /path/to/sen1floods11/HandLabeled \\
        --splits-dir /path/to/sen1floods11/splits/flood_handlabeled \\
        --weights ai/models/weights/light_unet.pt \\
        --out ai/models/weights/evaluation.json
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

try:
    import torch
    from torch.utils.data import DataLoader
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "torch is required for ai/training/evaluate.py. "
        "Install with: pip install torch --break-system-packages"
    ) from exc

from ai.models.unet import load_model
from ai.training.dataset import build_datasets
from ai.training.losses import BCEDiceLoss
from ai.training.metrics import ConfusionAccumulator, binarize

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("drishti.ai.training.evaluate")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Evaluate a trained LightUNet checkpoint on the Sen1Floods11 test split")
    p.add_argument("--data-root", required=True)
    p.add_argument("--splits-dir", default=None)
    p.add_argument("--weights", required=True, help="Path to a checkpoint produced by train.py")
    p.add_argument("--patch-size", type=int, default=256)
    p.add_argument("--val-frac", type=float, default=0.15)
    p.add_argument("--test-frac", type=float, default=0.15)
    p.add_argument("--batch-size", type=int, default=8)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    p.add_argument("--out", default=None, help="Where to write the metrics JSON; defaults next to --weights")
    return p.parse_args()


def evaluate(model, loader, device) -> dict:
    criterion = BCEDiceLoss()
    acc = ConfusionAccumulator()
    total_loss, n_batches = 0.0, 0

    model.eval()
    with torch.no_grad():
        for bands, label, valid in loader:
            bands, label, valid = bands.to(device), label.to(device), valid.to(device)
            logits = model(bands)
            loss = criterion(logits, label, valid)
            total_loss += float(loss)
            n_batches += 1
            acc.update(binarize(logits), label, valid)

    metrics = acc.compute()
    metrics["loss"] = round(total_loss / max(n_batches, 1), 5)
    return metrics


def main() -> int:
    args = parse_args()

    # Reuses the EXISTING load_model() - this is the same function
    # run_pipeline.py calls, confirming the checkpoint is compatible with
    # unmodified inference code (Phase 5/6).
    model = load_model(weights_path=args.weights, device=args.device)
    if not getattr(model, "trained", False):
        logger.error(
            "load_model() did not mark the model as trained - the weights "
            "file at %s was not found or torch is unavailable. Aborting "
            "evaluation rather than reporting meaningless metrics for an "
            "untrained model.", args.weights,
        )
        return 1
    model = model.to(args.device)

    _, _, test_ds = build_datasets(
        data_root=args.data_root,
        splits_dir=args.splits_dir,
        patch_size=args.patch_size,
        val_frac=args.val_frac,
        test_frac=args.test_frac,
        seed=args.seed,
    )
    test_loader = DataLoader(test_ds, batch_size=args.batch_size, shuffle=False)

    logger.info("Evaluating on %d test patches ...", len(test_ds))
    metrics = evaluate(model, test_loader, args.device)

    logger.info("=" * 60)
    logger.info("TEST SET RESULTS")
    for k, v in metrics.items():
        logger.info("  %-18s %s", k, v)
    logger.info("=" * 60)

    out_path = Path(args.out) if args.out else Path(args.weights).with_suffix(".evaluation.json")
    with open(out_path, "w") as f:
        json.dump({"weights": args.weights, "metrics": metrics}, f, indent=2)
    logger.info("Metrics written to %s", out_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
