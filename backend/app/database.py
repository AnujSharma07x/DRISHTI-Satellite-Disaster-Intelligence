"""
Supabase client factory for the FastAPI backend.

CRITICAL: uses SUPABASE_SERVICE_ROLE_KEY, server-side only. Never expose this
client, this key, or any wrapper around it to the React frontend — see
docs/ARCHITECTURE.md §7 and the security notes in backend/README.md.
"""
from functools import lru_cache

from supabase import create_client, Client

from backend.app.config import get_settings


class SupabaseNotConfiguredError(RuntimeError):
    """Raised when SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY are not set."""


@lru_cache(maxsize=1)
def get_supabase_client() -> Client:
    """
    Returns a cached Supabase client using the service-role key.

    Raises SupabaseNotConfiguredError at call time (not import time) if
    credentials are missing, so the FastAPI app can still start and report a
    clear, actionable error via /api/health instead of crashing on boot.
    """
    settings = get_settings()
    if not settings.is_supabase_configured():
        raise SupabaseNotConfiguredError(
            "SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set. Copy "
            ".env.example to .env at the repo root and fill in your Supabase "
            "project credentials (Project Settings -> API in the Supabase "
            "dashboard). See backend/README.md for the full setup checklist."
        )
    return create_client(settings.supabase_url, settings.supabase_service_role_key)
