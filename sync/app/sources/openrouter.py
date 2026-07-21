"""
OpenRouter source - public, no key: https://openrouter.ai/api/v1/models

LiteLLM gives us the universe + pricing + context + capabilities but almost no prose.
OpenRouter fills three gaps that matter for Impulse's open-weight story:

  - description   - real, human-written model blurbs
  - release_date  - from the unix `created` timestamp
  - hugging_face_id - the exact HF repo, which is the join key into Hugging Face
                      (license, downloads→popularity, params→VRAM) for the next layer.

We index each OpenRouter model under several normalized keys so a LiteLLM id like
`claude-3-5-sonnet-20241022` can find `anthropic/claude-3.5-sonnet`. Matching is
best-effort: popular/featured models match, the long tail stays LiteLLM-only (honest gap).
"""
import logging
import re
from datetime import datetime, timezone

import httpx

from app.settings import settings

log = logging.getLogger("impulse_sync")


# Hosts re-list the same model under decorated names. Strip the decoration so a Bedrock
# entry like 'us.anthropic.claude-3-5-sonnet-20241022-v2:0' resolves to the same key as
# the vendor's own 'claude-3-5-sonnet-20241022' - model-level facts (descriptions, release
# dates, benchmarks) then reach every listing instead of only the bare one.
_REGION_PREFIX = re.compile(r"^(?:us|eu|apac|ap|ca|sa|global)\.")
_VENDOR_PREFIX = re.compile(
    r"^(?:openai|anthropic|meta|mistral|mistralai|google|cohere|amazon|ai21|deepseek|writer|stability|luma|qwen)\."
)


def norm(s: str) -> str:
    """Normalized model key: 'us.anthropic.claude-3.5-sonnet-v2:0' → 'claude35sonnet'."""
    seg = (s or "").split("/")[-1].lower()
    seg = re.sub(r"@.*$", "", seg)          # claude-fable-5@default
    seg = re.sub(r"-v\d+:\d+$", "", seg)    # bedrock  …-v2:0
    seg = _REGION_PREFIX.sub("", seg)
    seg = _VENDOR_PREFIX.sub("", seg)
    return re.sub(r"[^a-z0-9]", "", seg)


def _strip_date(k: str) -> str:
    """Drop a trailing 6-8 digit date/version stamp: 'claude35sonnet20241022' → 'claude35sonnet'."""
    return re.sub(r"\d{6,8}$", "", k)


def keys_for(name: str) -> list[str]:
    """Candidate lookup keys for a LiteLLM model name, most-specific first."""
    k = norm(name)
    out = [k, _strip_date(k)]
    return [x for i, x in enumerate(out) if x and x not in out[:i]]


def fetch() -> dict[str, dict]:
    """Return {normalized_key: {description, release_date, hugging_face_id}}. Empty dict on failure."""
    try:
        r = httpx.get(settings.URL_OPENROUTER, timeout=settings.HTTP_TIMEOUT, follow_redirects=True)
        r.raise_for_status()
        data = r.json().get("data", [])
    except Exception as e:  # enrichment is best-effort - never fail the sync
        log.warning("OpenRouter fetch failed (%s); skipping OpenRouter enrichment", e)
        return {}

    out: dict[str, dict] = {}
    for m in data:
        created = m.get("created")
        release = ""
        if isinstance(created, (int, float)) and created > 0:
            try:
                release = datetime.fromtimestamp(created, tz=timezone.utc).date().isoformat()
            except (ValueError, OSError, OverflowError):
                pass
        enr = {
            "description": (m.get("description") or "").strip(),
            "release_date": release,
            "hugging_face_id": (m.get("hugging_face_id") or "").strip() or None,
            "or_id": m.get("id"),  # 'author/slug' - the key for the per-model endpoints API
        }
        cand = {norm(m.get("id", "")), norm(m.get("canonical_slug", "")),
                _strip_date(norm(m.get("id", "")))}
        for key in cand:
            # first writer wins → exact id keys registered before their date-stripped variants
            if key and key not in out:
                out[key] = enr
    log.info("OpenRouter: %d models, %d lookup keys", len(data), len(out))
    return out


def fetch_uptime(or_ids: set[str]) -> dict[str, float]:
    """
    {openrouter model id: availability %} from the per-model endpoints API.

    A model is served by several hosts with independent uptimes; we report the best
    host's figure - the availability you can actually get - measured over the last day
    (falling back to the 30-minute window). Latency/throughput are deliberately NOT read
    here: OpenRouter returns them as null for most providers, and an empty field beats a
    made-up one. One request per model, so only ids we actually matched are fetched.
    """
    ids = sorted(i for i in or_ids if i)
    if not ids:
        return {}

    out: dict[str, float] = {}
    with httpx.Client(timeout=settings.HTTP_TIMEOUT, follow_redirects=True) as client:
        for or_id in ids:
            try:
                r = client.get(f"{settings.URL_OPENROUTER}/{or_id}/endpoints")
                if r.status_code != 200:
                    continue
                endpoints = (r.json().get("data") or {}).get("endpoints") or []
            except Exception:
                continue
            uptimes = [
                e["uptime_last_1d"] if isinstance(e.get("uptime_last_1d"), (int, float))
                else e.get("uptime_last_30m")
                for e in endpoints
            ]
            values = [float(u) for u in uptimes if isinstance(u, (int, float))]
            if values:
                out[or_id] = round(max(values), 1)
    log.info("OpenRouter uptime: %d/%d models reported availability", len(out), len(ids))
    return out
