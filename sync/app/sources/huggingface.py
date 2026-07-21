"""
Hugging Face source - public, no key: https://huggingface.co/api/models/{repo_id}

Keyed by the `hugging_face_id` that OpenRouter hands us, this fills the facts that make
Impulse's open-weight story real and self-hostable:

  - license         - the actual repo license (cardData.license), normalized to our names
  - popularity      - log-scaled monthly downloads (0-100), a real signal, not a guess
  - min_vram_gb     - from safetensors parameter count, fp16 baseline (params × 2 bytes × 1.2)
  - release_date    - repo createdAt (fallback when OpenRouter had none)
  - tags            - a few descriptive HF tags (e.g. pipeline task, language)

One call per *unique* repo (many LiteLLM ids share a repo), best-effort: any failure just
leaves that repo un-enriched. Only repos we actually reference are fetched - no crawling.
"""
import logging
import math
import re

import httpx

from app.settings import settings

log = logging.getLogger("impulse_sync")

# HF license slug → Impulse license display name (open licenses we recognize).
_LICENSE = {
    "apache-2.0": "Apache-2.0", "mit": "MIT", "bsd-3-clause": "BSD-3-Clause",
    "cc-by-4.0": "CC-BY-4.0", "cc-by-sa-4.0": "CC-BY-SA-4.0", "cc-by-nc-4.0": "CC-BY-NC-4.0",
    "gemma": "Gemma License", "llama2": "Llama 2 Community License",
    "llama3": "Llama 3 Community License", "llama3.1": "Llama 3.1 Community License",
    "llama3.2": "Llama 3.2 Community License", "llama3.3": "Llama 3.3 Community License",
    "llama4": "Llama 4 Community License", "openrail": "OpenRAIL",
    "bigscience-openrail-m": "BigScience OpenRAIL-M", "deepseek": "DeepSeek License",
    "tongyi-qianwen": "Tongyi Qianwen License", "qwen": "Qwen License",
    "gpl-3.0": "GPL-3.0", "agpl-3.0": "AGPL-3.0",
}
# Tags that are noise, not signal.
_TAG_SKIP = re.compile(r"^(license:|arxiv:|dataset:|base_model|region:|doi:|autotrain|endpoints_compatible)")


def _norm_license(raw: str | None) -> str | None:
    if not raw:
        return None
    return _LICENSE.get(raw.lower().strip(), raw.strip())


def _vram_gb(params: int | None) -> float | None:
    """fp16 baseline: params × 2 bytes × 1.2 runtime overhead, rounded to 1 decimal."""
    if not params or params <= 0:
        return None
    return round(params * 2 * 1.2 / 1e9, 1)


def _popularity(downloads: int | None) -> int | None:
    """Log-scaled 0-100 from monthly downloads (10 → ~12, 1M → ~72, 100M → ~96)."""
    if not downloads or downloads <= 0:
        return None
    return min(100, round(12 * math.log10(downloads + 1)))


def _tags(tags: list, pipeline: str | None) -> list[str]:
    out = []
    if pipeline:
        out.append(pipeline.replace("-", " "))
    for t in tags or []:
        if isinstance(t, str) and not _TAG_SKIP.match(t) and ":" not in t and len(t) <= 24:
            out.append(t)
    seen, uniq = set(), []
    for t in out:
        if t not in seen:
            seen.add(t)
            uniq.append(t)
    return uniq[:6]


def _one(client: httpx.Client, repo: str) -> dict | None:
    try:
        r = client.get(f"{settings.URL_HF_MODEL}/{repo}", timeout=settings.HTTP_TIMEOUT)
        if r.status_code != 200:
            return None
        d = r.json()
    except Exception:
        return None
    card = d.get("cardData") or {}
    safet = d.get("safetensors") or {}
    created = d.get("createdAt") or ""
    return {
        "license": _norm_license(card.get("license")),
        "popularity": _popularity(d.get("downloads")),
        "min_vram_gb": _vram_gb(safet.get("total")),
        "release_date": created[:10] if len(created) >= 10 else "",
        "tags": _tags(d.get("tags"), d.get("pipeline_tag")),
    }


def fetch(repo_ids: set[str]) -> dict[str, dict]:
    """Return {hf_id: {license, popularity, min_vram_gb, release_date, tags}} for reachable repos."""
    repos = sorted(r for r in repo_ids if r)
    if not repos:
        return {}
    out: dict[str, dict] = {}
    with httpx.Client(follow_redirects=True) as client:
        for repo in repos:
            got = _one(client, repo)
            if got:
                out[repo] = got
    log.info("Hugging Face: enriched %d/%d repos", len(out), len(repos))
    return out
