"""Listing facts the sync stores but doesn't promote to columns: the route segment of the
internal id (region, deployment, vendor org...) and the extras in the verbatim LiteLLM spec."""
import re
from functools import lru_cache

REASONING_EFFORTS = ["none", "minimal", "low", "medium", "high", "xhigh", "max"]
_EFFORT_FLAGS = [(e, f"supports_{e}_reasoning_effort") for e in REASONING_EFFORTS]

_FEATURES = {
    "supports_web_search": "webSearch",
    "supports_computer_use": "computerUse",
    "supports_pdf_input": "pdfInput",
    "supports_url_context": "urlContext",
    "supports_parallel_function_calling": "parallelToolCalls",
    "supports_audio_input": "audioInput",
    "supports_audio_output": "audioOutput",
    "supports_video_input": "videoInput",
    "supports_adaptive_thinking": "adaptiveThinking",
    "thinking_always_on": "thinkingAlwaysOn",
    "supports_assistant_prefill": "assistantPrefill",
    "supports_native_structured_output": "nativeStructuredOutput",
    "supports_tool_search": "toolSearch",
    "supports_fast_mode": "fastMode",
    "supports_prompt_caching": "promptCaching",
}

# pricing DTO key -> LiteLLM per-token key
_TIER_PRICES = {
    "cacheWritePerMtok": "cache_creation_input_token_cost",
    "cacheWrite1hPerMtok": "cache_creation_input_token_cost_above_1hr",
    "batchInputPerMtok": "input_cost_per_token_batches",
    "batchOutputPerMtok": "output_cost_per_token_batches",
    "flexInputPerMtok": "input_cost_per_token_flex",
    "flexOutputPerMtok": "output_cost_per_token_flex",
    "priorityInputPerMtok": "input_cost_per_token_priority",
    "priorityOutputPerMtok": "output_cost_per_token_priority",
}

# Whole-key match: `..._above_272k_tokens_batches` / `_flex` / `_priority` are tier prices
# past the threshold, not the threshold's standard price.
_LONG_CONTEXT = re.compile(r"input_cost_per_token_above_(\d+)k_tokens")
_LONG_CONTEXT_PREFIX = "input_cost_per_token_above_"

_SEARCH_SIZES = ("search_context_size_medium", "search_context_size_low", "search_context_size_high")

_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def slugify(s: str) -> str:
    """Same as the sync's `mapping.slugify` (internal ids are slugify(LiteLLM key))."""
    return _NON_ALNUM.sub("-", s.lower()).strip("-")


@lru_cache(maxsize=1024)
def _prefixes(provider_slug: str, litellm_provider: str) -> tuple[str, ...]:
    """Provider spellings that can open an internal id, longest first."""
    return tuple(sorted({p for p in (provider_slug, slugify(provider_slug),
                                     litellm_provider, slugify(litellm_provider)) if p},
                        key=len, reverse=True))


def route_of(internal_id: str, name: str, provider_slug: str, litellm_provider: str) -> str | None:
    """What sits between the provider and the model name in the LiteLLM key: a region
    (`eu`, `us-gov-east-1`), deployment, commitment or vendor org. None for `<provider>/<name>`."""
    tail = slugify(name)
    rest = internal_id
    while tail and not rest.endswith(tail) and rest.endswith("-x"):
        rest = rest[:-2]  # the sync de-duplicates colliding ids with "-x" suffixes
    if not tail or not rest.endswith(tail):
        return None
    rest = rest[: len(rest) - len(tail)]
    if rest and not rest.endswith(("-", "_")):
        return None  # the name only matched part of a segment
    rest = rest.rstrip("-_")

    stripped = True
    while rest and stripped:
        stripped = False
        for p in _prefixes(provider_slug, litellm_provider):
            if rest == p or rest.startswith((p + "-", p + "_")):
                rest, stripped = rest[len(p) + 1:], True
                break
    return rest or None


def _num(v) -> int | float | None:
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _per_mtok(v) -> float | None:
    v = _num(v)
    return round(v * 1e6, 6) if v is not None else None


def _long_context(spec: dict) -> dict | None:
    """The first price step: the smallest `input_cost_per_token_above_{N}k_tokens`, with the
    cache-read and batch prices past the same threshold."""
    found = {}
    for k, v in spec.items():
        if k.startswith(_LONG_CONTEXT_PREFIX) and _num(v) is not None:
            m = _LONG_CONTEXT.fullmatch(k)
            if m:
                found.setdefault(int(m.group(1)), k)
    if not found:
        return None
    n = min(found)
    key = found[n]
    out_key = "output" + key[len("input"):]
    return {"thresholdTokens": n * 1000,
            "inputPerMtok": _per_mtok(spec[key]),
            "outputPerMtok": _per_mtok(spec.get(out_key)),
            "cachedInputPerMtok": _per_mtok(spec.get("cache_read_input_token_cost" + key[len("input_cost_per_token"):])),
            "batchInputPerMtok": _per_mtok(spec.get(key + "_batches")),
            "batchOutputPerMtok": _per_mtok(spec.get(out_key + "_batches"))}


def _web_search(v) -> int | float | None:
    if isinstance(v, dict):
        return next((v[s] for s in _SEARCH_SIZES if _num(v.get(s)) is not None), None)
    return _num(v)


def _regional_uplift(spec: dict) -> int | float | None:
    us = _num(spec.get("regional_processing_uplift_multiplier_us"))
    if us is None and isinstance(spec.get("provider_specific_entry"), dict):
        us = _num(spec["provider_specific_entry"].get("us"))
    return us


def _reasoning_efforts(spec: dict) -> list[str]:
    levels = spec.get("reasoning_effort_levels")
    listed = {e for e in levels if isinstance(e, str)} if isinstance(levels, list) else set()
    return [e for e, flag in _EFFORT_FLAGS if e in listed or spec.get(flag) is True]


def _text(v) -> str | None:
    return v if isinstance(v, str) and v else None


def spec_extras(spec: dict) -> dict:
    """DTO fields parsed from a verbatim LiteLLM entry; prices per 1M tokens (search per query)."""
    if not isinstance(spec, dict):
        spec = {}
    rpm, tpm = _num(spec.get("rpm")), _num(spec.get("tpm"))
    return {
        "deprecationDate": _text(spec.get("deprecation_date")),
        "sourceUrl": _text(spec.get("source")),
        "features": sorted(f for k, f in _FEATURES.items() if spec.get(k) is True),
        "reasoningEfforts": _reasoning_efforts(spec),
        "rateLimits": {"rpm": rpm, "tpm": tpm} if rpm is not None or tpm is not None else None,
        "pricing": {
            **{dto: _per_mtok(spec.get(key)) for dto, key in _TIER_PRICES.items()},
            "longContext": _long_context(spec),
            "webSearchPerQuery": _web_search(spec.get("search_context_cost_per_query")),
            "regionalUplift": _regional_uplift(spec),
        },
    }
