"""
Map a LiteLLM cost-map entry (+ curated overlay) → Impulse domain rows.

The 15 capability keys mirror the FE's CAPABILITY_KEYS exactly. The DB's promoted
columns are the domain facets; the verbatim LiteLLM entry is kept in model_spec.
"""
import re
import uuid
from datetime import date
from typing import Any

# Fixed namespace so a model/provider's public GUID is DETERMINISTIC and STABLE across
# every wipe-and-rebuild sync. Derived from the natural key - never random, never re-minted.
_GUID_NS = uuid.uuid5(uuid.NAMESPACE_DNS, "impulse.catalog")


def guid(*parts: str) -> str:
    return str(uuid.uuid5(_GUID_NS, ":".join(p or "" for p in parts)))

# LiteLLM endpoint-key -> client-facing /v1 path (inference subset we expose)
EP_MAP = {
    "chat_completions": "/v1/chat/completions", "text_completion": "/v1/completions",
    "messages": "/v1/messages", "responses": "/v1/responses", "embeddings": "/v1/embeddings",
    "image_generations": "/v1/images/generations", "audio_transcriptions": "/v1/audio/transcriptions",
    "audio_speech": "/v1/audio/speech", "moderations": "/v1/moderations", "rerank": "/v1/rerank",
    "batches": "/v1/batches", "realtime": "/v1/realtime",
}
MODE_EP = {
    "chat": ["/v1/chat/completions"], "completion": ["/v1/completions"], "embedding": ["/v1/embeddings"],
    "image_generation": ["/v1/images/generations"], "audio_transcription": ["/v1/audio/transcriptions"],
    "audio_speech": ["/v1/audio/speech"], "rerank": ["/v1/rerank"], "realtime": ["/v1/realtime"],
    "moderation": ["/v1/moderations"],
}

# Starter provider categories (LiteLLM has none; providers.json overlay overrides any).
CATEGORY = {
    "openai": "frontier", "anthropic": "frontier", "gemini": "frontier", "vertex_ai": "cloud",
    "xai": "frontier", "mistral": "open", "deepseek": "open", "groq": "inference",
    "together_ai": "inference", "fireworks_ai": "inference", "perplexity": "frontier",
    "cohere": "frontier", "cohere_chat": "frontier", "bedrock": "cloud", "azure": "cloud",
    "azure_ai": "cloud", "ollama": "open", "cerebras": "inference", "databricks": "cloud",
    "huggingface": "open", "nvidia_nim": "inference", "replicate": "inference",
}

_MODALITIES = {"text", "image", "audio", "video", "embedding"}

# What a mode actually emits, used when LiteLLM declares no output modalities.
_MODE_OUT = {
    "embedding": ["embedding"],
    "image_generation": ["image"], "image_edit": ["image"],
    "audio_speech": ["audio"],
    "video_generation": ["video"],
}

# LiteLLM's `mode` is unreliable - some entries omit it (→ default "chat") and some are
# outright mislabeled (Titan embeddings, Flux image models carry mode="chat"). Recover the
# true mode from the strongest available signal: declared endpoints, then name patterns.
_EP_MODE = {
    "/v1/embeddings": "embedding", "/v1/images/generations": "image_generation",
    "/v1/rerank": "rerank", "/v1/audio/transcriptions": "audio_transcription",
    "/v1/audio/speech": "audio_speech", "/v1/moderations": "moderation",
}
_NAME_MODE = [
    (re.compile(r"embed|embedding|bge-|gte-|e5-|nomic", re.I), "embedding"),
    (re.compile(r"rerank|reranker", re.I), "rerank"),
    (re.compile(r"flux|stable-diffusion|sdxl|dall-?e|imagen|image-gen|-image$|kolors|playground-v", re.I), "image_generation"),
    (re.compile(r"whisper|transcrib|-stt|speech-to-text", re.I), "audio_transcription"),
    (re.compile(r"\btts\b|text-to-speech|-tts|xtts|voice", re.I), "audio_speech"),
    (re.compile(r"moderation|guard", re.I), "moderation"),
]


def infer_mode(litellm_name: str, entry: dict) -> str:
    """Best-effort true mode. Endpoints win; then name patterns correct chat mislabels."""
    for ep in (entry.get("supported_endpoints") or []):
        if ep in _EP_MODE:
            return _EP_MODE[ep]
    declared = entry.get("mode")
    name = litellm_name.split("/")[-1]
    # trust a specific declared mode; only second-guess the vague/default "chat"
    if declared and declared != "chat":
        return declared
    for pat, mode in _NAME_MODE:
        if pat.search(name):
            return mode
    return declared or "chat"


def vendor(litellm_provider: str) -> str:
    if litellm_provider.startswith("bedrock"):
        return "bedrock"
    if litellm_provider.startswith("vertex_ai"):
        return "vertex_ai"
    if litellm_provider == "text-completion-openai":
        return "openai"
    return litellm_provider


def slugify(s: str) -> str:
    return re.sub(r"^-+|-+$", "", re.sub(r"[^a-z0-9]+", "-", s.lower()))


def titleize(slug: str) -> str:
    return " ".join(w.capitalize() for w in re.split(r"[-_]", slug) if w)


def strip_name(display: str | None) -> str:
    return (display or "").split(" (`")[0].strip()


def _modalities(values: Any, fallback: list[str]) -> list[str]:
    if not isinstance(values, list):
        return fallback
    out = [m for m in values if m in _MODALITIES]
    return out or fallback


def capabilities(entry: dict, mode: str, in_mods: list[str], out_mods: list[str],
                 paths: list[str], overlay: dict) -> dict[str, bool]:
    """The 15 domain capability flags (True/False)."""
    return {
        "streaming": bool(entry.get("supports_native_streaming", mode == "chat")),
        "functionCalling": bool(entry.get("supports_function_calling")),
        "toolCalling": bool(entry.get("supports_tool_choice") or entry.get("supports_function_calling")),
        "jsonMode": bool(entry.get("supports_response_schema")),
        "structuredOutputs": bool(entry.get("supports_response_schema")),
        "reasoning": bool(entry.get("supports_reasoning")),
        "vision": bool(entry.get("supports_vision")),
        "audio": bool(entry.get("supports_audio_input") or entry.get("supports_audio_output")),
        "imageInput": bool(entry.get("supports_vision") or "image" in in_mods),
        "imageGeneration": mode == "image_generation" or "image" in out_mods,
        "video": "video" in in_mods,
        "embeddings": mode == "embedding",
        "batchApi": "/v1/batches" in paths or entry.get("input_cost_per_token_batches") is not None,
        "promptCaching": bool(entry.get("supports_prompt_caching")),
        "mcp": bool(overlay.get("supportsMcp", False)),
    }


def _deprecation(entry: dict, overlay: dict) -> str:
    if overlay.get("status") in ("active", "deprecating", "deprecated", "preview"):
        return overlay["status"]
    dep = entry.get("deprecation_date")
    if isinstance(dep, str) and len(dep) >= 7:
        try:
            return "deprecated" if date.fromisoformat(dep[:10]) <= date.today() else "deprecating"
        except ValueError:
            pass
    return "active"


def _f(v: Any) -> float | None:
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def map_model(litellm_name: str, entry: dict, provider_slug: str,
              provider_paths: set[str], overlay: dict, model_id: str) -> dict:
    """Return a `models` row dict (+ 'capabilities' list attached for the junction)."""
    mode = infer_mode(litellm_name, entry)
    paths = entry.get("supported_endpoints") or MODE_EP.get(mode, ["/v1/chat/completions"])
    paths = [p for p in paths if isinstance(p, str)]
    in_mods = _modalities(entry.get("supported_modalities"), ["text"])
    # LiteLLM rarely declares output modalities; default from the (inferred) mode rather
    # than assuming "text", which mislabels image/audio/video generators as text models.
    out_mods = _modalities(entry.get("supported_output_modalities"), _MODE_OUT.get(mode, ["text"]))

    caps = capabilities(entry, mode, in_mods, out_mods, paths, overlay)
    endpoint_ids = [f"{provider_slug}:{p.split('/')[-1]}" for p in paths if p in provider_paths]

    in_tok = _f(entry.get("input_cost_per_token")) or 0.0
    out_tok = _f(entry.get("output_cost_per_token"))
    cached = _f(entry.get("cache_read_input_token_cost"))

    display = litellm_name.split("/")[-1]

    row = {
        "id": model_id,
        # stable public id = uuid5(litellm route + exact LiteLLM model name)
        "guid": guid("model", entry.get("litellm_provider", provider_slug), litellm_name),
        "provider_id": provider_slug,
        "litellm_provider": entry.get("litellm_provider", provider_slug),
        # transient (not columns): enrichment join keys used by the sync, dropped before insert
        "_litellm_name": litellm_name,
        "hf_id": None,
        "or_id": None,
        "name": display,
        "family": overlay.get("family"),
        # Left empty when the overlay has none → sync fills from OpenRouter, then a generic fallback.
        "description": overlay.get("description", ""),
        "mode": mode,
        "status": _deprecation(entry, overlay),
        "release_date": overlay.get("releaseDate", ""),
        "input_per_mtok": in_tok * 1e6,
        "output_per_mtok": out_tok * 1e6 if out_tok is not None else None,
        "cached_input_per_mtok": cached * 1e6 if cached is not None else None,
        "batch_discount": overlay.get("batchDiscount"),
        "context_window": entry.get("max_input_tokens") or entry.get("max_tokens") or 0,
        "max_output_tokens": entry.get("max_output_tokens") or 0,
        "is_open_weights": 1 if overlay.get("isOpenWeights") else 0,
        "license": overlay.get("license"),
        "open_source_score": overlay.get("openSourceScore"),
        "min_vram_gb": overlay.get("minVramGb"),
        "runtimes": overlay.get("runtimes", []),
        "ttft_ms": overlay.get("ttftMs"),
        "tokens_per_sec": overlay.get("tokensPerSec"),
        "availability_pct": overlay.get("availabilityPct"),
        "popularity": overlay.get("popularity"),
        "input_modalities": in_mods,
        "output_modalities": out_mods,
        "endpoint_ids": endpoint_ids,
        "tags": overlay.get("tags", []),
        "benchmarks": overlay.get("benchmarks", []),
        "model_spec": entry,
        "enriched": 1 if overlay else 0,
        "capabilities": [k for k, on in caps.items() if on],
    }
    return row


def endpoints_for(slug: str, paths: list[str]) -> list[dict]:
    out = []
    for p in sorted(paths):
        key = p.split("/")[-1]
        out.append({
            "id": f"{slug}:{key}", "name": titleize(key), "method": "POST", "path": p,
            "description": f"{titleize(key)} endpoint.",
            "streaming": bool(re.search(r"chat|responses|messages|speech|realtime", p)),
            "auth": "API key",
        })
    return out


def map_provider(slug: str, display: str | None, url: str | None,
                 paths: list[str], overlay: dict) -> dict:
    name = overlay.get("name") or strip_name(display) or titleize(slug)
    return {
        "id": slug,
        "guid": guid("provider", slug),
        "name": name,
        "monogram": overlay.get("monogram", name[:1].upper()),
        "description": overlay.get("description", f"{name} models via API."),
        "website": overlay.get("website") or url or "",
        # LiteLLM's provider `url` is a docs link, so an API base can never be derived
        # from it - it is curated or left empty (callers must not fabricate one).
        "api_base": overlay.get("apiBase", ""),
        "category": overlay.get("category") or CATEGORY.get(slug, "cloud"),
        "auth_type": overlay.get("authType", "api-key"),
        "regions": overlay.get("regions", []),
        "endpoints": overlay.get("endpoints") or endpoints_for(slug, paths),
        "sdks": overlay.get("sdks", []),
        "founded_year": overlay.get("foundedYear"),
        "enriched": 1 if overlay else 0,
    }
