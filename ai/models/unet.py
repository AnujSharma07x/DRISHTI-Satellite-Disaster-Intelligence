"""
unet.py
=======
Segmentation models for flood-mask generation.

Two models are provided, per the master prompt's AI-model guidance
("prioritize working inference, reproducibility, explainability, fast
execution... if a full training pipeline is too expensive for the 10-day
timeline, create a clean inference pipeline using a suitable
pretrained/trained model or a small demonstrable model"):

1. LightUNet
   A small, trainable U-Net for binary flood segmentation from a
   pre-flood + post-flood SAR stack. Ships untrained (no weights are
   bundled - training data collection is out of scope for this module).
   Use `load_model(weights_path=...)` once a team member trains weights.

2. ThresholdFloodModel
   A zero-training heuristic baseline: flood = a significant drop in SAR
   backscatter between pre- and post-flood images (open water strongly
   attenuates radar backscatter, which is the standard physical basis for
   SAR-based flood mapping, e.g. Twele et al. 2016). This runs out of the
   box with no weights and no GPU, so the pipeline is demoable on day 1.

`load_model()` picks LightUNet when trained weights are available and
transparently falls back to ThresholdFloodModel otherwise, so the rest of
the pipeline (inference/predict.py) doesn't need to care which one is active.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

import numpy as np

logger = logging.getLogger("drishti.ai.models")

try:
    import torch
    import torch.nn as nn

    _TORCH_AVAILABLE = True
except ImportError:  # pragma: no cover
    _TORCH_AVAILABLE = False
    nn = object  # type: ignore


if _TORCH_AVAILABLE:

    class _ConvBlock(nn.Module):
        def __init__(self, in_ch: int, out_ch: int):
            super().__init__()
            self.block = nn.Sequential(
                nn.Conv2d(in_ch, out_ch, 3, padding=1),
                nn.BatchNorm2d(out_ch),
                nn.ReLU(inplace=True),
                nn.Conv2d(out_ch, out_ch, 3, padding=1),
                nn.BatchNorm2d(out_ch),
                nn.ReLU(inplace=True),
            )

        def forward(self, x):
            return self.block(x)

    class LightUNet(nn.Module):
        """A deliberately small U-Net (4 encoder/decoder levels, base width
        16) - enough capacity to learn flood/no-flood segmentation without
        requiring a large labelled dataset or long training time.

        Input:  (B, in_channels, H, W)  - default in_channels=2
                (channel 0 = preprocessed pre-flood SAR, channel 1 = post-flood SAR)
        Output: (B, 1, H, W) raw logits (apply sigmoid for probability)
        """

        def __init__(self, in_channels: int = 2, base_width: int = 16):
            super().__init__()
            # Explicit, queryable flag - True only once `load_model()` has
            # loaded real trained weights into this instance. Freshly
            # constructed weights are random; STEP 6 requires that we never
            # let random-weight output be mistaken for a real prediction.
            self.trained = False
            w = base_width
            self.enc1 = _ConvBlock(in_channels, w)
            self.enc2 = _ConvBlock(w, w * 2)
            self.enc3 = _ConvBlock(w * 2, w * 4)
            self.pool = nn.MaxPool2d(2)

            self.bottleneck = _ConvBlock(w * 4, w * 8)

            self.up3 = nn.ConvTranspose2d(w * 8, w * 4, 2, stride=2)
            self.dec3 = _ConvBlock(w * 8, w * 4)
            self.up2 = nn.ConvTranspose2d(w * 4, w * 2, 2, stride=2)
            self.dec2 = _ConvBlock(w * 4, w * 2)
            self.up1 = nn.ConvTranspose2d(w * 2, w, 2, stride=2)
            self.dec1 = _ConvBlock(w * 2, w)

            self.out_conv = nn.Conv2d(w, 1, kernel_size=1)

        def forward(self, x):
            e1 = self.enc1(x)
            e2 = self.enc2(self.pool(e1))
            e3 = self.enc3(self.pool(e2))
            b = self.bottleneck(self.pool(e3))

            d3 = self.up3(b)
            d3 = self.dec3(torch.cat([d3, e3], dim=1))
            d2 = self.up2(d3)
            d2 = self.dec2(torch.cat([d2, e2], dim=1))
            d1 = self.up1(d2)
            d1 = self.dec1(torch.cat([d1, e1], dim=1))

            return self.out_conv(d1)

else:  # pragma: no cover

    class LightUNet:  # type: ignore
        def __init__(self, *args, **kwargs):
            raise ImportError(
                "PyTorch is not installed. Install with: "
                "pip install torch --break-system-packages"
            )


class ThresholdFloodModel:
    """Zero-training SAR change-detection baseline. This is the MVP's
    reliable fallback (STEP 6) - clearly a heuristic, not a calibrated
    classifier, and labelled as such everywhere it's reported.

    Physical basis: standing/flowing water is a smooth, specular reflector
    for radar, so it strongly attenuates the SAR backscatter returned to the
    sensor. A pixel is flagged as "newly flooded" when the post-flood
    backscatter drops well below its pre-flood value, measured directly in
    decibels:

        change_db = pre_db - post_db      (positive => backscatter fell)

    Working in real dB units (rather than on independently min-max-scaled
    [0,1] arrays, as an earlier version of this module did) is important:
    two images min-max-normalized *separately* can each get stretched to
    fill [0, 1] regardless of their actual physical backscatter levels,
    which can shrink or inflate a genuine flood signal in the difference.
    dB values from `preprocessing.calibrate_sar()` are physically comparable
    across the pair, so differencing them directly is the physically
    meaningful formulation requested for this baseline.

    Documented assumption on the threshold: SAR flood-mapping literature
    (e.g. Sentinel-1-based flood studies such as Twele et al. 2016)
    typically reports open-water backscatter drops of roughly 3-10 dB
    relative to the same area's pre-flood (usually vegetated/bare-soil)
    return. `drop_threshold_db=3.0` is chosen as a conservative default
    inside that range, deliberately configurable via `--drop-threshold-db`
    on the CLI since the right value depends on land cover, incidence
    angle, and the specific Sentinel-1 product - it is NOT tuned/validated
    against ground truth for this MVP.
    """

    DEFAULT_DROP_THRESHOLD_DB = 3.0

    def __init__(self, drop_threshold_db: float = DEFAULT_DROP_THRESHOLD_DB):
        self.drop_threshold_db = drop_threshold_db

    def predict(self, pre_db: np.ndarray, post_db: np.ndarray, valid_mask: Optional[np.ndarray] = None) -> np.ndarray:
        """Returns a heuristic flood-likelihood proxy in [0, 1], same shape
        as input - NOT a calibrated statistical probability (STEP 7). It is
        a monotonic function of the dB backscatter drop, scaled so that
        `drop_threshold_db` sits at proxy value 0.5 (i.e. thresholding this
        output at 0.5 reproduces classifying `change_db >= drop_threshold_db`).

        Invalid pixels (per `valid_mask`, if supplied) are forced to 0 so
        NoData can never be classified as flooded downstream.
        """
        change_db = pre_db - post_db  # positive where backscatter fell (flood signal)

        steepness = 1.0
        proxy = 1.0 / (1.0 + np.exp(-steepness * (change_db - self.drop_threshold_db)))

        if valid_mask is not None:
            proxy = np.where(valid_mask, proxy, 0.0)

        return proxy.astype("float32")


def load_model(
    weights_path: Optional[str] = None,
    in_channels: int = 2,
    device: str = "cpu",
):
    """Load the best available model.

    - If `weights_path` is given and exists and torch is installed: loads a
      trained LightUNet.
    - Otherwise: falls back to the no-training ThresholdFloodModel so the
      pipeline always runs end-to-end.

    `weights_path` may point at either:
      - a full training checkpoint dict (as saved by `ai/training/train.py`),
        containing "model_state_dict" plus metadata such as
        "input_channels"/"base_width"/"normalization_stats"/etc., or
      - a raw state_dict (a plain mapping of parameter name -> tensor), e.g.
        exported/saved some other way.
    In the first case, the architecture (`in_channels`, `base_width`) is
    reconstructed from the checkpoint's own recorded values when present, so
    it always matches what was actually trained - the caller-supplied
    `in_channels` argument is only used as a fallback when the checkpoint
    doesn't record it (e.g. a bare state_dict).
    """
    if weights_path and os.path.exists(weights_path) and _TORCH_AVAILABLE:
        checkpoint = torch.load(weights_path, map_location=device, weights_only=False)

        if isinstance(checkpoint, dict) and "model_state_dict" in checkpoint:
            state_dict = checkpoint["model_state_dict"]
            ckpt_in_channels = checkpoint.get("input_channels", in_channels)
            ckpt_base_width = checkpoint.get("base_width", 16)
            logger.info(
                "Loading full training checkpoint from %s "
                "(model_version=%s, epoch=%s, input_channels=%s, base_width=%s)",
                weights_path,
                checkpoint.get("model_version"),
                checkpoint.get("epoch"),
                ckpt_in_channels,
                ckpt_base_width,
            )
        else:
            # Raw state_dict - no architecture metadata available, fall back
            # to the caller-supplied in_channels and the LightUNet default
            # base_width.
            state_dict = checkpoint
            ckpt_in_channels = in_channels
            ckpt_base_width = 16
            logger.info(
                "Loading raw state_dict from %s (no checkpoint metadata "
                "found - assuming in_channels=%d, base_width=%d)",
                weights_path, ckpt_in_channels, ckpt_base_width,
            )

        model = LightUNet(in_channels=ckpt_in_channels, base_width=ckpt_base_width)
        model.load_state_dict(state_dict)
        model.eval()
        model.trained = True
        logger.info("Loaded trained LightUNet weights from %s", weights_path)
        return model

    if weights_path and not os.path.exists(weights_path):
        logger.warning(
            "Weights path %s not found - falling back to ThresholdFloodModel "
            "heuristic baseline.",
            weights_path,
        )
    else:
        logger.info(
            "No trained weights configured - using ThresholdFloodModel "
            "heuristic baseline (no training required)."
        )

    return ThresholdFloodModel()
