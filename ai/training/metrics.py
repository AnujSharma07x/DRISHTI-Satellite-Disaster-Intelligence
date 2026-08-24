"""
metrics.py
==========
Shared IoU / Dice / precision / recall computation for `train.py`
(validation-time monitoring) and `evaluate.py` (final test-set report), so
the two never compute metrics slightly differently.

All metrics are computed only over valid pixels (see `dataset.py` /
`losses.py`) and accumulate true/false positive/negative counts across an
entire epoch or split before dividing, rather than averaging per-batch
ratios - the latter is biased when batches have very different numbers of
positive (water) pixels, which is common with flood data.
"""

from __future__ import annotations

from dataclasses import dataclass

try:
    import torch
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "torch is required for ai/training/metrics.py. "
        "Install with: pip install torch --break-system-packages"
    ) from exc


@dataclass
class ConfusionAccumulator:
    """Accumulates TP/FP/FN/TN counts (as valid-pixel counts) across
    however many `update()` calls the caller makes, e.g. once per batch."""

    tp: float = 0.0
    fp: float = 0.0
    fn: float = 0.0
    tn: float = 0.0

    def update(self, pred_binary: "torch.Tensor", target: "torch.Tensor", valid: "torch.Tensor") -> None:
        pred_binary = pred_binary * valid
        target = target * valid

        self.tp += float(((pred_binary == 1) & (target == 1)).sum())
        self.fp += float(((pred_binary == 1) & (target == 0) & (valid == 1)).sum())
        self.fn += float(((pred_binary == 0) & (target == 1) & (valid == 1)).sum())
        self.tn += float(((pred_binary == 0) & (target == 0) & (valid == 1)).sum())

    def compute(self, eps: float = 1e-7) -> dict:
        iou = self.tp / (self.tp + self.fp + self.fn + eps)
        dice = (2 * self.tp) / (2 * self.tp + self.fp + self.fn + eps)
        precision = self.tp / (self.tp + self.fp + eps)
        recall = self.tp / (self.tp + self.fn + eps)
        accuracy = (self.tp + self.tn) / (self.tp + self.fp + self.fn + self.tn + eps)
        return {
            "iou": round(iou, 4),
            "dice": round(dice, 4),
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "accuracy": round(accuracy, 4),
            "valid_pixel_count": int(self.tp + self.fp + self.fn + self.tn),
        }


def binarize(logits: "torch.Tensor", threshold: float = 0.5) -> "torch.Tensor":
    return (torch.sigmoid(logits) >= threshold).float()
