"""
predict.py
==========
Runs flood-mask inference given a preprocessed pre/post SAR pair.

Pipeline position:
    Preprocessing -> [THIS FILE: AI flood detection -> Flood mask] -> Flood polygon

This module is model-agnostic: it works identically whether `load_model()`
returned a trained LightUNet (PyTorch) or the ThresholdFloodModel heuristic
baseline, so the pipeline is never blocked on having trained weights.

NoData handling (STEP 5): every code path here takes `valid_mask` and forces
invalid pixels' probability to 0 before thresholding, so a NoData pixel can
never end up classified as flooded, and confidence/statistics are computed
only over valid pixels.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np

from ai.models.unet import ThresholdFloodModel

logger = logging.getLogger("drishti.ai.inference")

try:
    import torch

    _TORCH_AVAILABLE = True
except ImportError:  # pragma: no cover
    _TORCH_AVAILABLE = False


@dataclass
class InferenceResult:
    mask: np.ndarray            # binary uint8 array, 1 = flooded, 0 = not flooded (never 1 at invalid pixels)
    probability: np.ndarray     # float32 array in [0, 1] - see `is_calibrated_probability`
    confidence: float           # single scalar confidence score for the whole prediction, 0.0-1.0
    model_name: str
    is_calibrated_probability: bool  # False for the heuristic baseline - see STEP 7


def run_inference(
    pre_db: np.ndarray,
    post_db: np.ndarray,
    valid_mask: np.ndarray,
    pre_norm: np.ndarray = None,
    post_norm: np.ndarray = None,
    model=None,
    threshold: float = 0.5,
    device: str = "cpu",
) -> InferenceResult:
    """Run flood segmentation on a preprocessed pre/post SAR pair.

    Args:
        pre_db, post_db: calibrated dB bands (real physical units) - used
            directly by ThresholdFloodModel.
        valid_mask: True where both pre and post pixels are real data (not
            NoData). Required - invalid pixels are always forced to
            probability 0 / mask 0, never classified as flooded.
        pre_norm, post_norm: jointly-normalized [0,1] bands - only needed
            when `model` is a LightUNet; ignored for ThresholdFloodModel.
        model: a LightUNet instance, a ThresholdFloodModel instance, or None
            (defaults to ThresholdFloodModel()).
        threshold: probability threshold above which a pixel is classified
            as flooded.
        device: torch device string, only used for LightUNet.

    Returns:
        InferenceResult with a binary mask, a per-pixel probability/proxy
        map, a scalar confidence score, and `is_calibrated_probability`
        which is False for the heuristic baseline (STEP 7: never represent
        a heuristic score as a calibrated probability without saying so).
    """
    if model is None:
        model = ThresholdFloodModel()

    if isinstance(model, ThresholdFloodModel):
        probability = model.predict(pre_db, post_db, valid_mask=valid_mask)
        model_name = "sar_change_threshold_baseline_v1"
        is_calibrated = False
    elif _TORCH_AVAILABLE and isinstance(model, torch.nn.Module):
        if not getattr(model, "trained", False):
            logger.warning(
                "Running inference with an UNTRAINED LightUNet (random "
                "weights) - this output is NOT a meaningful flood "
                "prediction. Provide trained weights via --weights, or use "
                "the ThresholdFloodModel baseline for real results."
            )
        if pre_norm is None or post_norm is None:
            raise ValueError("LightUNet inference requires pre_norm and post_norm (normalized [0,1] bands).")
        probability = _run_torch_inference(model, pre_norm, post_norm, device)
        probability = np.where(valid_mask, probability, 0.0).astype("float32")
        model_name = "light_unet_v1" if getattr(model, "trained", False) else "light_unet_v1_UNTRAINED"
        is_calibrated = bool(getattr(model, "trained", False))
    else:
        raise TypeError(
            f"Unsupported model type: {type(model)!r}. Expected "
            f"ThresholdFloodModel or a torch.nn.Module (LightUNet)."
        )

    mask = ((probability >= threshold) & valid_mask).astype("uint8")
    confidence = _estimate_confidence(probability, mask, valid_mask)

    logger.info(
        "Inference complete (%s): %d / %d valid pixels flooded, confidence=%.3f%s",
        model_name,
        int(mask.sum()),
        int(valid_mask.sum()),
        confidence,
        "" if is_calibrated else " [heuristic proxy, not a calibrated probability]",
    )

    return InferenceResult(
        mask=mask,
        probability=probability,
        confidence=confidence,
        model_name=model_name,
        is_calibrated_probability=is_calibrated,
    )


def _run_torch_inference(model, pre_norm: np.ndarray, post_norm: np.ndarray, device: str) -> np.ndarray:
    model.eval()
    stack = np.stack([pre_norm, post_norm], axis=0)  # (2, H, W)
    tensor = torch.from_numpy(stack).unsqueeze(0).float().to(device)  # (1, 2, H, W)

    with torch.no_grad():
        logits = model(tensor)
        probs = torch.sigmoid(logits)

    return probs.squeeze(0).squeeze(0).cpu().numpy().astype("float32")


def _estimate_confidence(probability: np.ndarray, mask: np.ndarray, valid_mask: np.ndarray) -> float:
    """Confidence score reported alongside the prediction (0.0-1.0), matching
    `flood_predictions.confidence` in DATABASE_SCHEMA.md.

    Computed only over VALID pixels (STEP 5: NoData must not influence
    statistics). Defined as the mean predicted probability/proxy over
    pixels classified as flooded. If no pixels are classified as flooded,
    confidence reflects how far the valid scene sits below the decision
    threshold (i.e. how confidently "no flood" was predicted).
    """
    flooded_valid = mask == 1
    if flooded_valid.sum() > 0:
        return float(np.clip(probability[flooded_valid].mean(), 0.0, 1.0))
    if valid_mask.sum() > 0:
        return float(np.clip(1.0 - probability[valid_mask].mean(), 0.0, 1.0))
    return 0.0
