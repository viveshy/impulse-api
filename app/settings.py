"""Configuration for impulse-api (env-driven, zero-config defaults)."""
import os
from pathlib import Path

# By default read the DB the bundled sync job produces (in ./sync/).
_DEFAULT_DB = Path(__file__).resolve().parents[1] / "sync" / "impulse.db"


class Settings:
    def __init__(self) -> None:
        self.DB_PATH = os.getenv("IMPULSE_DB_PATH", str(_DEFAULT_DB))

        # Pagination (the catalog is only reachable page-by-page - no bulk dump).
        self.PAGE_DEFAULT = int(os.getenv("PAGE_DEFAULT", "30"))
        self.PAGE_MAX = int(os.getenv("PAGE_MAX", "100"))

        # Fixed-window rate limit per client (anti-scraping).
        self.RATE_LIMIT = int(os.getenv("RATE_LIMIT", "120"))
        self.RATE_WINDOW = int(os.getenv("RATE_WINDOW", "60"))

        self.CORS_ORIGINS = [o for o in os.getenv("CORS_ORIGINS", "*").split(",") if o]


settings = Settings()
