"""Configuration for impulse-api (env-driven, zero-config defaults)."""
import os
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]

# By default read the DB the bundled sync job produces (in ./sync/).
_DEFAULT_DB = _ROOT / "sync" / "impulse.db"


class Settings:
    def __init__(self) -> None:
        self.DB_PATH = os.getenv("IMPULSE_DB_PATH", str(_DEFAULT_DB))

        # Visitor analytics get their own writable file; the catalog stays read-only.
        self.ANALYTICS_DB = os.getenv("IMPULSE_ANALYTICS_DB", str(_ROOT / "analytics.db"))
        # Referrers from the site itself aren't traffic sources.
        self.SITE_HOST = os.getenv("IMPULSE_SITE_HOST", "impulse.viveshy.com")

        # Pagination (the catalog is only reachable page-by-page - no bulk dump).
        self.PAGE_DEFAULT = int(os.getenv("PAGE_DEFAULT", "30"))
        self.PAGE_MAX = int(os.getenv("PAGE_MAX", "100"))

        # Fixed-window rate limit per client (anti-scraping).
        self.RATE_LIMIT = int(os.getenv("RATE_LIMIT", "120"))
        self.RATE_WINDOW = int(os.getenv("RATE_WINDOW", "60"))

        self.CORS_ORIGINS = [o for o in os.getenv("CORS_ORIGINS", "*").split(",") if o]


settings = Settings()
