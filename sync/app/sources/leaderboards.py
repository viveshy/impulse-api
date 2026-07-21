"""
Open benchmark leaderboards - the free replacement for paid benchmark data.

  Aider polyglot  - real-world code editing pass-rate. Joined on the LiteLLM model name
                    embedded in each record's `command` (`aider --model <name>`), which is
                    far more reliable than matching human-written display names.
  HF Open LLM v2  - IFEval / BBH / MATH / GPQA / MUSR / MMLU-Pro. Joined on the Hugging
                    Face repo id we already resolve via OpenRouter, so the match is exact.

Both are best-effort and additive: a failed fetch or an unmatched model simply leaves
benchmarks empty - an honest gap is always preferred over an invented score.
"""
import logging
import re

import httpx
import yaml

from app.settings import settings
from app.sources.openrouter import keys_for

log = logging.getLogger("impulse_sync")

AIDER_URL = (
    "https://raw.githubusercontent.com/Aider-AI/aider/main/aider/website/_data/polyglot_leaderboard.yml"
)
OPEN_LLM_URL = "https://datasets-server.huggingface.co/rows"
OPEN_LLM_DATASET = "open-llm-leaderboard/contents"

# leaderboard column -> the name we display. All are percentages (max 100).
_OPEN_LLM_COLS = {
    "Average ⬆️": "Open LLM Average",
    "IFEval": "IFEval",
    "BBH": "BBH",
    "MATH Lvl 5": "MATH Lvl 5",
    "GPQA": "GPQA",
    "MUSR": "MUSR",
    "MMLU-PRO": "MMLU-Pro",
}


def fetch_aider() -> dict[str, list[dict]]:
    """{normalized model key: [benchmark]} from the Aider polyglot leaderboard."""
    try:
        r = httpx.get(AIDER_URL, timeout=settings.HTTP_TIMEOUT, follow_redirects=True)
        r.raise_for_status()
        records = yaml.safe_load(r.text) or []
    except Exception as e:  # never fail the sync over enrichment
        log.warning("Aider leaderboard fetch failed (%s); skipping", e)
        return {}

    out: dict[str, list[dict]] = {}
    for rec in records:
        score = rec.get("pass_rate_2")
        if not isinstance(score, (int, float)):
            continue
        command = rec.get("command") or ""
        matched = re.search(r"--model\s+(\S+)", command)
        identifier = matched.group(1) if matched else (rec.get("model") or "")
        bench = {"name": "Aider Polyglot", "score": float(score), "max": 100.0, "source": "Aider"}
        for key in keys_for(identifier):
            out.setdefault(key, [bench])
    log.info("Aider leaderboard: %d records -> %d lookup keys", len(records), len(out))
    return out


def fetch_open_llm(repo_ids: set[str]) -> dict[str, list[dict]]:
    """{hf repo id: [benchmarks]} from the HF Open LLM Leaderboard (archived, still public)."""
    wanted = {r for r in repo_ids if r}
    if not wanted:
        return {}

    out: dict[str, list[dict]] = {}
    try:
        with httpx.Client(timeout=settings.HTTP_TIMEOUT) as client:
            offset, total = 0, None
            while total is None or offset < total:
                resp = client.get(
                    OPEN_LLM_URL,
                    params={
                        "dataset": OPEN_LLM_DATASET, "config": "default", "split": "train",
                        "offset": offset, "length": 100,
                    },
                )
                if resp.status_code != 200:
                    break
                payload = resp.json()
                total = payload.get("num_rows_total") or 0
                for row in payload.get("rows", []):
                    record = row.get("row", {})
                    repo = record.get("fullname")
                    if repo not in wanted:
                        continue
                    scores = [
                        {"name": label, "score": round(float(record[col]), 1),
                         "max": 100.0, "source": "Open LLM Leaderboard"}
                        for col, label in _OPEN_LLM_COLS.items()
                        if isinstance(record.get(col), (int, float))
                    ]
                    if scores:
                        out[repo] = scores
                offset += 100
                if len(out) == len(wanted):  # everything we care about is found
                    break
    except Exception as e:
        log.warning("Open LLM Leaderboard fetch failed (%s); using partial results", e)

    log.info("Open LLM Leaderboard: matched %d/%d linked repos", len(out), len(wanted))
    return out
