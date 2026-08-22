"""
sar_preprocessing.py
=====================
Preprocessing pipeline for Sentinel-1 SAR imagery (pre-flood / post-flood pair).

Scope (Engineer 2 ownership only):
    Satellite data -> Preprocessing -> AI flood detection -> Flood mask
                                                            -> Flood polygon
                                                            -> Flood statistics

This module handles ONLY the "Preprocessing" step above. It never writes to
Supabase/PostGIS directly and never touches the FastAPI/React/database layers
(see ARCHITECTURE.md, "Engineer Ownership & Data Flow").

Notes on CRS handling (DATA_FORMATS.md #1):
    Raster processing may use the native/projected CRS transiently. Nothing in
    this file writes to PostGIS, so no reprojection happens here - that occurs
    later in `utils/geo_utils.py` right before the vector result is produced.

Sentinel-1 assumption (documented, not silently assumed):
    Inputs are assumed to already be **analysis-ready Sentinel-1 GRD**
    products - i.e. already radiometrically calibrated to sigma-nought
    (linear power) and terrain-corrected/geocoded (e.g. via SNAP or the
    Copernicus/ASF on-demand pipelines), single-band GeoTIFFs. This module
    does NOT implement orbit-file application, thermal-noise removal, or
    range-Doppler terrain correction - building a full Sentinel-1 processing
    chain from raw Level-0/1 data is out of scope for the 10-day MVP
    (master prompt: "Do not create an unnecessarily complicated Sentinel-1
    processing chain"). `calibrate_sar()` below only performs the final
    linear-to-dB conversion, which is the step actually relevant to the
    flood-detection signal.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Optional, Tuple

import numpy as np

try:
    import rasterio
    from rasterio.io import DatasetReader
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "rasterio is required for sar_preprocessing.py. "
        "Install with: pip install rasterio --break-system-packages"
    ) from exc

try:
    from scipy.ndimage import median_filter, uniform_filter
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "scipy is required for speckle filtering. "
        "Install with: pip install scipy --break-system-packages"
    ) from exc

logger = logging.getLogger("drishti.ai.preprocessing")

# How closely two rasters' affine transforms must match to be considered
# "aligned" (STEP 4). Tolerance absorbs harmless floating-point drift in the
# geotransform (e.g. from repeated reprojection) without accepting a real
# misalignment. 1e-6 in transform units (degrees or metres, depending on CRS)
# is sub-millimetre in projected CRS and far below a pixel in any case.
_TRANSFORM_ATOL = 1e-6


@dataclass
class RasterData:
    """Container for a loaded raster band plus the georeferencing needed to
    later convert any derived vector result back to EPSG:4326, and a
    validity mask distinguishing real observations from NoData."""

    array: np.ndarray          # 2D float32 array, single band, raw values (NoData left as-is)
    valid_mask: np.ndarray     # 2D bool array, True where the pixel is real data (not NoData/NaN)
    transform: "rasterio.Affine"
    crs: "rasterio.crs.CRS"
    nodata: Optional[float]
    width: int
    height: int


def load_raster(path: str, band: int = 1) -> RasterData:
    """Load a single band of a raster file (GeoTIFF) from local/temp disk.

    Per ARCHITECTURE.md #7, this local file is expected to be a temporary
    scratch copy (downloaded from Supabase Storage `satellite/` bucket by the
    caller) - it is discarded after processing, never treated as the system
    of record.

    Raises FileNotFoundError / rasterio.errors.RasterioIOError with a clear,
    actionable message if the file is missing or unreadable (STEP 4/16).
    """
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"SAR input file not found: {path!r}. "
            f"Check the --pre/--post path, or that the file was downloaded "
            f"from Supabase Storage before running the pipeline."
        )

    try:
        with rasterio.open(path) as src:  # type: DatasetReader
            if band > src.count:
                raise ValueError(
                    f"Requested band {band} but {path!r} only has {src.count} band(s)."
                )
            array = src.read(band).astype("float32")
            nodata = src.nodata
            transform = src.transform
            crs = src.crs
            width, height = src.width, src.height
    except rasterio.errors.RasterioIOError as exc:
        raise rasterio.errors.RasterioIOError(
            f"Could not read raster data from {path!r}: {exc}. "
            f"Verify the file is a valid, uncorrupted GeoTIFF."
        ) from exc

    valid_mask = _compute_valid_mask(array, nodata)

    data = RasterData(
        array=array,
        valid_mask=valid_mask,
        transform=transform,
        crs=crs,
        nodata=nodata,
        width=width,
        height=height,
    )
    logger.info(
        "Loaded raster %s (%dx%d, crs=%s, nodata=%s, valid_pixels=%d/%d)",
        path, data.width, data.height, data.crs, nodata,
        int(valid_mask.sum()), valid_mask.size,
    )
    return data


def _compute_valid_mask(array: np.ndarray, nodata: Optional[float]) -> np.ndarray:
    """A pixel is valid unless it equals the raster's declared NoData value
    or is NaN/inf (STEP 5: 'identify NoData pixels where available')."""
    mask = np.isfinite(array)
    if nodata is not None:
        mask &= array != nodata
    return mask


def validate_raster_pair(pre: RasterData, post: RasterData) -> None:
    """Verify the pre/post rasters are actually the same grid before any
    pixel-wise comparison is done between them (STEP 4).

    Same array shape is NOT sufficient evidence of alignment - two rasters
    can have identical dimensions while covering completely different
    ground areas. This checks CRS, affine transform (which encodes origin,
    pixel size, and rotation together), and shape, and fails loudly and
    specifically rather than silently proceeding or silently resampling.
    """
    errors = []

    if pre.array.shape != post.array.shape:
        errors.append(
            f"shape mismatch: pre={pre.array.shape} vs post={post.array.shape}"
        )

    if pre.crs is None or post.crs is None:
        errors.append(
            f"missing CRS: pre.crs={pre.crs}, post.crs={post.crs} "
            f"(both rasters must carry a defined CRS)"
        )
    elif pre.crs != post.crs:
        errors.append(f"CRS mismatch: pre={pre.crs} vs post={post.crs}")

    if not _transforms_match(pre.transform, post.transform):
        errors.append(
            f"geotransform mismatch (origin/pixel-size/rotation differ): "
            f"pre={pre.transform} vs post={post.transform}"
        )

    if errors:
        raise ValueError(
            "Pre-flood and post-flood rasters are not geographically "
            "aligned, cannot proceed with pixel-wise change detection:\n  - "
            + "\n  - ".join(errors)
            + "\nThis module does not silently resample mismatched grids - "
              "co-register the pair (matching CRS, resolution, and origin) "
              "before running the pipeline."
        )


def _transforms_match(t1, t2, atol: float = _TRANSFORM_ATOL) -> bool:
    a1 = np.array([t1.a, t1.b, t1.c, t1.d, t1.e, t1.f])
    a2 = np.array([t2.a, t2.b, t2.c, t2.d, t2.e, t2.f])
    return bool(np.allclose(a1, a2, atol=atol))


def calibrate_sar(array: np.ndarray, valid_mask: np.ndarray, epsilon: float = 1e-6) -> np.ndarray:
    """Convert calibrated SAR backscatter (linear sigma-nought, per the
    analysis-ready-GRD assumption documented at the top of this file) to
    decibels (dB):

        sigma0_dB = 10 * log10(sigma0_linear)

    Invalid (NoData) pixels are left at 0.0 dB - a placeholder value that is
    never used downstream because `valid_mask` is carried through the rest
    of the pipeline and excludes these pixels from statistics, classification,
    and area calculations (STEP 5: "do not allow NoData values to become
    flood pixels").
    """
    safe = np.clip(array, epsilon, None)
    db = 10.0 * np.log10(safe)
    db = np.where(valid_mask, db, 0.0)
    return db.astype("float32")


def speckle_filter(array: np.ndarray, valid_mask: np.ndarray, method: str = "lee", size: int = 5) -> np.ndarray:
    """Reduce SAR speckle noise before change detection.

    Two lightweight, dependency-free options are provided - a full Lee/Refined
    Lee/Gamma-MAP filter is not implemented on purpose (out of scope for a
    10-day MVP: "Do NOT build an unnecessarily complex ... architecture"
    applies equally to preprocessing complexity).

    method:
        "median"  - simple median filter, robust to speckle outliers
        "lee"     - simplified Lee filter (local-statistics adaptive filter)

    NoData pixels are excluded from the local statistics used by the filter
    (STEP 5) so a single invalid neighbour doesn't bias a valid pixel's
    smoothed value; invalid pixels themselves are left unfiltered (they're
    excluded from every downstream calculation anyway via `valid_mask`).
    """
    if method == "median":
        # median_filter has no native mask support; substituting invalid
        # pixels with the array's valid-pixel median keeps them from
        # skewing neighbourhood statistics without needing a custom kernel.
        fill_value = float(np.median(array[valid_mask])) if valid_mask.any() else 0.0
        filled = np.where(valid_mask, array, fill_value)
        filtered = median_filter(filled, size=size).astype("float32")
        return np.where(valid_mask, filtered, array)

    if method == "lee":
        fill_value = float(np.mean(array[valid_mask])) if valid_mask.any() else 0.0
        filled = np.where(valid_mask, array, fill_value)

        mean = uniform_filter(filled, size=size)
        sq_mean = uniform_filter(filled ** 2, size=size)
        local_var = np.clip(sq_mean - mean ** 2, 0, None)
        overall_var = float(np.var(filled[valid_mask])) if valid_mask.any() else 1e-9
        overall_var = overall_var if overall_var > 1e-9 else 1e-9

        weight = local_var / (local_var + overall_var)
        result = mean + weight * (filled - mean)
        return np.where(valid_mask, result, array).astype("float32")

    raise ValueError(f"Unknown speckle filter method: {method!r} (use 'median' or 'lee')")


def normalize_pair(pre_db: np.ndarray, post_db: np.ndarray, valid_mask: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """Jointly min-max normalize a pre/post dB pair to [0, 1] for model
    (LightUNet) input.

    IMPORTANT: this uses ONE shared min/max computed across BOTH images'
    valid pixels together, then applies the same affine scaling to both.
    Normalizing pre and post independently (as an earlier version of this
    module did) each stretches to its own [0, 1] range, which distorts the
    physical relationship between them - a genuine backscatter drop between
    the two scenes can be partially or fully cancelled out by the two
    independent rescalings. Joint normalization preserves relative
    magnitude, so `post_norm - pre_norm` remains a meaningful (if unitless)
    proxy for the same physical change captured by `pre_db - post_db`.

    This function is ONLY used to prepare neural-network input
    (LightUNet). The threshold/change-detection baseline
    (`models.ThresholdFloodModel`) works directly on `pre_db`/`post_db` in
    real dB units and does not use this normalization at all - see STEP 3.
    """
    valid_values = (
        np.concatenate([pre_db[valid_mask], post_db[valid_mask]])
        if valid_mask.any() else np.array([0.0])
    )
    v_min, v_max = float(valid_values.min()), float(valid_values.max())

    if v_max - v_min < 1e-9:
        zeros = np.zeros_like(pre_db, dtype="float32")
        return zeros, zeros.copy()

    pre_norm = np.clip((pre_db - v_min) / (v_max - v_min), 0.0, 1.0).astype("float32")
    post_norm = np.clip((post_db - v_min) / (v_max - v_min), 0.0, 1.0).astype("float32")
    return pre_norm, post_norm


@dataclass
class PreprocessedPair:
    """Everything downstream stages (inference, geo_utils) need from
    preprocessing, bundled together so `valid_mask` can't accidentally be
    dropped on the way through the pipeline."""

    pre_db: np.ndarray          # calibrated dB, invalid pixels = 0.0 placeholder
    post_db: np.ndarray         # calibrated dB, invalid pixels = 0.0 placeholder
    pre_norm: np.ndarray        # jointly-normalized [0,1], for NN input only
    post_norm: np.ndarray       # jointly-normalized [0,1], for NN input only
    valid_mask: np.ndarray      # True = real data pixel (both pre AND post valid)
    reference: RasterData       # georeferencing (post-flood raster's transform/crs/etc.)


def preprocess_pair(
    pre_flood_path: str,
    post_flood_path: str,
    despeckle_method: str = "lee",
    despeckle_size: int = 5,
) -> PreprocessedPair:
    """Full preprocessing pipeline for a pre/post Sentinel-1 SAR pair.

    Steps: load -> validate alignment -> calibrate to dB -> despeckle ->
    joint-normalize (for NN input). NoData is tracked throughout via
    `valid_mask` rather than silently defaulting to some fill value that
    downstream code might mistake for a real observation.

    Both rasters are assumed to already be co-registered / same grid -
    reprojecting mismatched grids is a GIS preprocessing concern outside
    this module's scope; `validate_raster_pair()` fails loudly instead of
    silently resampling (STEP 4).
    """
    pre = load_raster(pre_flood_path)
    post = load_raster(post_flood_path)

    validate_raster_pair(pre, post)

    # A pixel only counts as valid data for change detection if it's valid
    # in BOTH scenes - a pixel with real pre-flood data but NoData
    # post-flood (or vice versa) can't support a change comparison.
    valid_mask = pre.valid_mask & post.valid_mask
    if not valid_mask.any():
        raise ValueError(
            "No valid (non-NoData) overlapping pixels between the pre-flood "
            "and post-flood rasters - cannot run change detection."
        )

    pre_db = calibrate_sar(pre.array, valid_mask)
    post_db = calibrate_sar(post.array, valid_mask)

    pre_db = speckle_filter(pre_db, valid_mask, method=despeckle_method, size=despeckle_size)
    post_db = speckle_filter(post_db, valid_mask, method=despeckle_method, size=despeckle_size)

    pre_norm, post_norm = normalize_pair(pre_db, post_db, valid_mask)

    # Carry the combined valid_mask forward on the reference raster so
    # downstream stages (inference, geo_utils) have a single source of
    # truth for "is this pixel real data".
    post.valid_mask = valid_mask

    return PreprocessedPair(
        pre_db=pre_db,
        post_db=post_db,
        pre_norm=pre_norm,
        post_norm=post_norm,
        valid_mask=valid_mask,
        reference=post,
    )
