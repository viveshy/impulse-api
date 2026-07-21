"""Configuration for impulse-catalog-sync (env-driven, zero-config defaults)."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class Settings:
    def __init__(self) -> None:
        # SQLite file the sync writes and the BE reads (same file in dev & prod).
        self.DB_PATH = os.getenv("IMPULSE_DB_PATH", str(ROOT / "impulse.db"))

        # LiteLLM source (public catalog files, GitHub-raw at this ref).
        self.LITELLM_REF = os.getenv("LITELLM_REF", "main")
        base = f"https://raw.githubusercontent.com/BerriAI/litellm/{self.LITELLM_REF}"
        self.URL_MODELS = f"{base}/model_prices_and_context_window.json"
        self.URL_PROVIDERS = f"{base}/provider_endpoints_support.json"

        # Enrichment sources (public, no key).
        self.URL_OPENROUTER = os.getenv("URL_OPENROUTER", "https://openrouter.ai/api/v1/models")
        self.URL_HF_MODEL = "https://huggingface.co/api/models"

        # Curated enrichment overlay (git-tracked; never overwritten by a sync).
        self.ENRICHMENT_DIR = Path(os.getenv("IMPULSE_ENRICHMENT_DIR", str(ROOT / "data" / "enrichment")))
        self.SCHEMA_PATH = ROOT / "db" / "schema.sql"

        self.HTTP_TIMEOUT = float(os.getenv("HTTP_TIMEOUT", "60"))


settings = Settings()
