"""
losses.py
=========
Segmentation loss for LightUNet training: BCE + Dice, both masked by the
per-pixel `valid` map so no-data pixels (Sen1Floods11 LabelHand's -1
sentinel, see `dataset.py`) never contribute to the gradient - consistent
with the rest of this codebase's rule that NoData must never influence
statistics or classification (see `ai/preprocessing/sar_preprocessing.py`
and `ai/inference/predict.py`).

Combining BCE (stable gradients, pixel-wise) with soft Dice (directly
optimizes overlap, robust to the class imbalance typical of flood masks
where "water" pixels are usually a minority) is a standard, simple choice
for binary segmentation - deliberately not a more elaborate loss (e.g.
focal + Lovasz + boundary terms), per the "keep the model lightweight and
training practical" / "do not spend the project timeline on complex
architectures" constraint.
"""

from __future__ import annotations

try:
    import torch
    import torch.nn as nn
    import torch.nn.functional as F
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "torch is required for ai/training/losses.py. "
        "Install with: pip install torch --break-system-packages"
    ) from exc


def masked_bce_loss(logits: "torch.Tensor", target: "torch.Tensor", valid: "torch.Tensor", eps: float = 1e-7) -> "torch.Tensor":
    """Pixel-wise BCE-with-logits, averaged only over `valid` pixels."""
    per_pixel = F.binary_cross_entropy_with_logits(logits, target, reduction="none")
    masked = per_pixel * valid
    denom = valid.sum().clamp_min(eps)
    return masked.sum() / denom


def masked_dice_loss(logits: "torch.Tensor", target: "torch.Tensor", valid: "torch.Tensor", eps: float = 1e-6) -> "torch.Tensor":
    """Soft Dice loss (1 - Dice coefficient), computed on sigmoid
    probabilities restricted to valid pixels only (invalid pixels are
    zeroed out of both the prediction and target before the overlap sums,
    so they contribute 0/0 -> excluded rather than biasing the score).
    """
    probs = torch.sigmoid(logits) * valid
    target = target * valid

    dims = tuple(range(1, probs.dim()))  # reduce over C,H,W but keep batch dim
    intersection = (probs * target).sum(dim=dims)
    union = probs.sum(dim=dims) + target.sum(dim=dims)
    dice = (2.0 * intersection + eps) / (union + eps)
    return 1.0 - dice.mean()


class BCEDiceLoss(nn.Module):
    """Combined loss: `bce_weight * BCE + dice_weight * Dice`, both masked
    by `valid`. Defaults to an equal 0.5/0.5 blend - a simple, commonly
    used starting point, exposed as constructor args rather than hardcoded
    so it can be tuned without touching the training loop.
    """

    def __init__(self, bce_weight: float = 0.5, dice_weight: float = 0.5):
        super().__init__()
        self.bce_weight = bce_weight
        self.dice_weight = dice_weight

    def forward(self, logits: "torch.Tensor", target: "torch.Tensor", valid: "torch.Tensor") -> "torch.Tensor":
        bce = masked_bce_loss(logits, target, valid)
        dice = masked_dice_loss(logits, target, valid)
        return self.bce_weight * bce + self.dice_weight * dice
