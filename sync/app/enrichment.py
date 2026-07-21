"""
Curated enrichment overlay - the featured-subset data LiteLLM can't provide.

Source of truth is git-tracked JSON in data/enrichment/; a LiteLLM re-sync never
touches it. Three files, all optional (missing/empty = LiteLLM-only, honest gaps):

  providers.json      { "<provider_slug>": { description, category, website,
                                             regions[], sdks[], foundedYear, monogram } }
  models.json         { "<litellm_model_name>": { description, family, releaseDate,
                                             popularity, tags[], benchmarks[], supportsMcp,
                                             ttftMs, tokensPerSec, availabilityPct,
                                             isOpenWeights, license, openSourceScore,
                                             minVramGb, runtimes[] } }   # per-model overrides
  openness_rules.json [ { "match": "<substring>", "isOpenWeights": true,
                          "license": "...", "runtimes": [...],
                          "openSourceScore": N } ]   # family-level, factual licenses
"""
import json
import logging
from typing import Any

from app.settings import settings

log = logging.getLogger("impulse_sync")


def _load(name: str, default: Any) -> Any:
    path = settings.ENRICHMENT_DIR / name
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError as e:
        log.warning("overlay %s is invalid JSON (%s); ignoring", name, e)
        return default


class Enrichment:
    def __init__(self) -> None:
        self.providers: dict[str, dict] = _load("providers.json", {})
        self.models: dict[str, dict] = _load("models.json", {})
        self.openness_rules: list[dict] = _load("openness_rules.json", [])

    def for_provider(self, slug: str) -> dict:
        return self.providers.get(slug, {})

    def for_model(self, litellm_name: str) -> dict:
        """Per-model overlay merged over the first matching family openness rule."""
        base: dict = {}
        lname = litellm_name.lower()
        for rule in self.openness_rules:
            if rule.get("match", "").lower() in lname:
                base = {k: v for k, v in rule.items() if k != "match"}
                break
        base.update(self.models.get(litellm_name, {}))
        return base
