"""
Configuration loader for the DRISHTI FastAPI backend.

Loads environment variables from the repo-root `.env` file (never commit the
real file — see `.env.example` and docs/ARCHITECTURE.md "Explicitly Rejected
Complexity" / security notes).

CRITICAL: SUPABASE_SERVICE_ROLE_KEY is read here and used only inside
`backend/app/database.py`. It must never be sent to, imported by, or
referenced from the React frontend.
"""
import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

# backend/app/config.py -> backend/app -> backend -> repo root
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(REPO_ROOT / ".env")


class Settings:
    """Simple settings holder — kept intentionally minimal (no unnecessary
    abstraction layers or dependency-injection frameworks, per Phase 2 scope)."""

    supabase_url: str | None = os.environ.get("SUPABASE_URL")
    supabase_anon_key: str | None = os.environ.get("SUPABASE_ANON_KEY")
    supabase_service_role_key: str | None = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    database_url: str | None = os.environ.get("DATABASE_URL")

    # Comma-separated list of allowed frontend origins for CORS. Defaults
    # cover local dev; override via env var for a deployed frontend.
    frontend_origins: list[str] = [
        origin.strip()
        for origin in os.environ.get(
            "FRONTEND_ORIGINS", "http://localhost:3000,http://localhost:5173"
        ).split(",")
        if origin.strip()
    ]

    def is_supabase_configured(self) -> bool:
        return bool(self.supabase_url and self.supabase_service_role_key)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
