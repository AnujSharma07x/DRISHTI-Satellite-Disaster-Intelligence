from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import rasterio
import torch

from ai.models.unet import load_model


def run_sen1_inference(
    image_path: str,
    weights_path: str,
    output_dir: str,
    threshold: float = 0.5,
):
    """
    Run LightUNet directly on a Sen1Floods11 S1Hand image.

    Input:
        2-band GeoTIFF
        Band 1 = VV
        Band 2 = VH

    Output:
        flood_mask.tif
        flood_probability.tif
        flood_prediction.json
    """

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    # ---------------------------------------------------------
    # 1. Load Sentinel-1 image
    # ---------------------------------------------------------
    with rasterio.open(image_path) as src:
        image = src.read().astype(np.float32)
        profile = src.profile.copy()
        transform = src.transform
        crs = src.crs

    if image.shape[0] != 2:
        raise ValueError(
            f"Expected 2 Sentinel-1 bands (VV + VH), got {image.shape[0]}"
        )

    print(f"Loaded Sentinel-1 image: {image.shape}")
    print(f"Band 1 = VV")
    print(f"Band 2 = VH")

    # ---------------------------------------------------------
    # 2. Handle NaN / NoData
    # ---------------------------------------------------------
    valid_mask = np.all(np.isfinite(image), axis=0)

    print(
        f"Valid pixels: {valid_mask.sum()} / {valid_mask.size}"
    )

    # ---------------------------------------------------------
    # 3. Normalize each channel
    # ---------------------------------------------------------
    normalized = np.zeros_like(image)

    for i in range(2):
        band = image[i]
        valid = np.isfinite(band)

        if valid.sum() == 0:
            raise ValueError(f"Band {i} contains no valid pixels.")

        values = band[valid]

        # Robust percentile normalization
        low = np.percentile(values, 2)
        high = np.percentile(values, 98)

        if high <= low:
            high = low + 1e-6

        normalized[i] = np.clip(
            (band - low) / (high - low),
            0,
            1,
        )

    normalized[:, ~valid_mask] = 0

    # ---------------------------------------------------------
    # 4. Load trained model
    # ---------------------------------------------------------
    model = load_model(weights_path=weights_path)
    model.eval()

    device = torch.device(
        "cuda" if torch.cuda.is_available() else "cpu"
    )

    model.to(device)

    print(f"Using device: {device}")

    # ---------------------------------------------------------
    # 5. Convert to tensor
    # ---------------------------------------------------------
    tensor = torch.from_numpy(normalized).unsqueeze(0).float()
    tensor = tensor.to(device)

    # ---------------------------------------------------------
    # 6. Run model
    # ---------------------------------------------------------
    with torch.no_grad():
        logits = model(tensor)

        probability = torch.sigmoid(logits)

    probability = probability.squeeze().cpu().numpy()

    # ---------------------------------------------------------
    # 7. Apply threshold
    # ---------------------------------------------------------
    flood_mask = (
        (probability >= threshold)
        & valid_mask
    ).astype(np.uint8)

    flooded_pixels = int(flood_mask.sum())
    valid_pixels = int(valid_mask.sum())

    flood_percentage = (
        flooded_pixels / valid_pixels * 100
        if valid_pixels > 0
        else 0
    )

    confidence = float(
        probability[valid_mask].mean()
        if valid_pixels > 0
        else 0
    )

    print("=" * 60)
    print("FLOOD DETECTION RESULT")
    print(f"Valid pixels:     {valid_pixels}")
    print(f"Flooded pixels:   {flooded_pixels}")
    print(f"Flood percentage: {flood_percentage:.2f}%")
    print(f"Mean probability: {confidence:.3f}")
    print("=" * 60)

    # ---------------------------------------------------------
    # 8. Save flood mask
    # ---------------------------------------------------------
    mask_path = output / "flood_mask.tif"

    mask_profile = profile.copy()
    mask_profile.update(
        count=1,
        dtype="uint8",
        nodata=0,
    )

    with rasterio.open(
        mask_path,
        "w",
        **mask_profile,
    ) as dst:
        dst.write(flood_mask, 1)

    # ---------------------------------------------------------
    # 9. Save probability raster
    # ---------------------------------------------------------
    probability_path = output / "flood_probability.tif"

    probability_profile = profile.copy()
    probability_profile.update(
        count=1,
        dtype="float32",
        nodata=0,
    )

    with rasterio.open(
        probability_path,
        "w",
        **probability_profile,
    ) as dst:
        dst.write(probability.astype(np.float32), 1)

    # ---------------------------------------------------------
    # 10. Save metadata
    # ---------------------------------------------------------
    metadata = {
        "input": str(image_path),
        "weights": str(weights_path),
        "model": "LightUNet",
        "bands": ["VV", "VH"],
        "width": int(image.shape[2]),
        "height": int(image.shape[1]),
        "valid_pixels": valid_pixels,
        "flooded_pixels": flooded_pixels,
        "flood_percentage": flood_percentage,
        "mean_probability": confidence,
        "threshold": threshold,
        "crs": str(crs),
    }

    metadata_path = output / "flood_prediction.json"

    with open(metadata_path, "w") as f:
        json.dump(metadata, f, indent=2)

    print(f"Mask:        {mask_path}")
    print(f"Probability: {probability_path}")
    print(f"Metadata:    {metadata_path}")

    return flood_mask, probability


if __name__ == "__main__":

    image = (
        r"data\sen1floods11\v1.1\data\flood_events"
        r"\HandLabeled\S1Hand\Bolivia_103757_S1Hand.tif"
    )

    weights = r"ai\weights\final_all_data.pth"

    run_sen1_inference(
        image_path=image,
        weights_path=weights,
        output_dir=r"ai\real_demo_output",
        threshold=0.5,
    )