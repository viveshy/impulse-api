"""Model business logic: assemble GUID-addressed DTOs and rank alternatives.

The DTOs never expose the internal slug id - the `guid` is the only identifier a client
ever sees or sends.
"""
from fastapi import HTTPException

from app.dao import models as dao

# Truly-open licenses (redistribute + modify + commercial). Restricted community licenses
# (Llama, Gemma, DeepSeek, Qwen custom, CC-BY-NC, RAIL) are open-*weight* but not open-*source*.
_OPEN_SOURCE_LICENSES = {
    "Apache-2.0", "MIT", "BSD-3-Clause", "BSD-2-Clause", "MPL-2.0",
    "GPL-3.0", "AGPL-3.0", "LGPL-3.0", "CC-BY-4.0", "CC-BY-SA-4.0", "CC0-1.0", "Unlicense",
}


def open_tag(row) -> str | None:
    """The badge shown in the two-tier alternatives view - None for closed models."""
    if not row["is_open_weights"]:
        return None
    return "Open Source" if row["license"] in _OPEN_SOURCE_LICENSES else "Open Weight"


def _split(v: str | None) -> list[str]:
    return v.split(",") if v else []


def _summary(row) -> dict:
    return {
        "guid": row["guid"],
        "name": row["name"],
        "family": row["family"],
        "mode": row["mode"],
        "status": row["status"],
        "provider": {"guid": row["provider_guid"], "name": row["provider_name"]},
        "description": row["description"],
        "releaseDate": row["release_date"],
        "popularity": row["popularity"],
        "isOpenWeights": bool(row["is_open_weights"]),
        "openTag": open_tag(row),
        "license": ({"name": row["license"], "isOpen": bool(row["license_is_open"])}
                    if row["license"] else None),
        "openSourceScore": row["open_source_score"],
        "minVramGb": row["min_vram_gb"],
        "runtimes": _split(row["runtime_names"]),
        "contextWindow": row["context_window"],
        "maxOutputTokens": row["max_output_tokens"],
        "capabilities": _split(row["cap_keys"]),
        "modalities": {"input": _split(row["in_mods"]), "output": _split(row["out_mods"])},
        "tags": _split(row["tag_names"]),
        "pricing": {
            "inputPerMtok": row["input_per_mtok"],
            "outputPerMtok": row["output_per_mtok"],
            "cachedInputPerMtok": row["cached_input_per_mtok"],
        },
        "performance": {
            "ttftMs": row["ttft_ms"],
            "tokensPerSec": row["tokens_per_sec"],
            "availabilityPct": row["availability_pct"],
        },
    }


def list_models(conn, **filters) -> tuple[list[dict], int]:
    rows, total = dao.list_models(conn, **filters)
    return [_summary(r) for r in rows], total


def get_model(conn, guid: str) -> dict:
    row = dao.get_by_guid(conn, guid)
    if row is None:
        raise HTTPException(404, detail=f"No model with guid {guid}")
    mid = dao.internal_id(conn, guid)
    dto = _summary(row)  # already carries capabilities, modalities, tags, runtimes
    dto["litellmProvider"] = row["litellm_provider"]
    dto["benchmarks"] = dao.benchmarks(conn, mid)
    dto["endpoints"] = dao.endpoints(conn, mid)
    return dto


def _alt(row) -> dict:
    dto = _summary(row)
    dto["sharedCapabilities"] = row["shared_caps"]
    return dto


def get_alternatives(conn, guid: str) -> dict:
    target = dao.get_by_guid(conn, guid)
    if target is None:
        raise HTTPException(404, detail=f"No model with guid {guid}")
    open_rows, cheaper_rows = dao.alternatives(conn, target)
    return {
        "target": _summary(target),
        "openAlternatives": [_alt(r) for r in open_rows],
        "cheaperAlternatives": [_alt(r) for r in cheaper_rows],
    }


def get_price_history(conn, guid: str) -> dict:
    mid = dao.internal_id(conn, guid)
    if mid is None:
        raise HTTPException(404, detail=f"No model with guid {guid}")
    return {"guid": guid, "history": dao.price_history(conn, mid)}
