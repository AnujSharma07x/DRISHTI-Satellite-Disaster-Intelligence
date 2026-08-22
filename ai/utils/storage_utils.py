"""
storage_utils.py
=================
Optional helper to upload the AI-generated flood-mask raster to the
`flood-masks/` bucket in Supabase Storage, per the bucket layout locked in
DATA_FORMATS.md #2:

    satellite/        raw satellite imagery
    dem/               digital elevation model files
    flood-masks/       AI-generated flood mask rasters      <- this module
    model-outputs/     other AI model outputs
    generated-maps/    rendered map images / reports

This is OPTIONAL and gated: the rest of the `ai/` module runs and produces a
complete, contract-compliant payload whether or not Supabase is configured
(see the "DO NOT WORK ON ... database schema" constraint - actually writing
rows to `flood_predictions` is Engineer 1's integration layer; this file only
uploads the raster and returns the `storage_path` string for Engineer 1 to
put in that row).

Credentials are read ONLY from environment variables - never hardcoded, never
committed (see .env.example and the "Never commit secrets" project rule).
Required env vars (service-role key, backend-only, per ARCHITECTURE.md #7):
    SUPABASE_URL
    SUPABASE_SERVICE_ROLE_KEY
"""

from __future__ import annotations

import logging
import os
from typing import Optional

logger = logging.getLogger("drishti.ai.storage")


class StorageUploadError(RuntimeError):
    """Raised when an upload to Supabase Storage cannot be completed."""


def upload_mask_raster(
    local_path: str,
    region_slug: str,
    prediction_id: str,
    bucket: str = "flood-masks",
) -> str:
    """Upload a local flood-mask GeoTIFF to Supabase Storage and return the
    `storage_path` to store in `flood_predictions.mask_storage_path`.

    This function is best-effort: if the `supabase` client library isn't
    installed, or the required environment variables aren't set, it raises
    `StorageUploadError` with a clear message rather than crashing the whole
    pipeline - callers (e.g. run_pipeline.py) should catch this and continue
    without Storage upload for local/offline demo runs.
    """
    supabase_url = os.environ.get("SUPABASE_URL")
    service_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

    if not supabase_url or not service_key:
        raise StorageUploadError(
            "SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set as "
            "environment variables to upload to Supabase Storage. "
            "Skipping upload; the local mask file is still available."
        )

    try:
        from supabase import create_client
    except ImportError as exc:
        raise StorageUploadError(
            "The 'supabase' package is not installed. "
            "Install with: pip install supabase --break-system-packages"
        ) from exc

    storage_path = f"{bucket}/{region_slug}/{prediction_id}.tif"

    client = create_client(supabase_url, service_key)
    with open(local_path, "rb") as f:
        client.storage.from_(bucket).upload(
            path=storage_path.split("/", 1)[1],  # bucket name is separate from the object path
            file=f,
            file_options={"content-type": "image/tiff"},
        )

    logger.info("Uploaded flood mask to Supabase Storage: %s", storage_path)
    return storage_path
