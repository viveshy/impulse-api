"""Shared fixtures: a throwaway catalog (sync/db/schema.sql + real-shaped rows) and a
throwaway analytics DB.

Settings are read when `app` is imported, so the env vars point at the temp dir before that
import - the tests can never open a real database.
"""
import atexit
import json
import os
import shutil
import sqlite3
import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
_TMP = Path(tempfile.mkdtemp(prefix="impulse-api-tests-"))
atexit.register(shutil.rmtree, _TMP, ignore_errors=True)  # also after collection errors
os.environ["IMPULSE_DB_PATH"] = str(_TMP / "catalog.db")
os.environ["IMPULSE_ANALYTICS_DB"] = str(_TMP / "analytics.db")

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

# Verbatim LiteLLM entries from the live catalog (2026-10-26). The GovCloud Bedrock row is
# filed under `bedrock_converse` here, like the other Bedrock Opus 5.5 rows.
OPUS_SPEC = """{"cache_creation_input_token_cost":5e-06,"cache_creation_input_token_cost_above_1hr":8e-06,"cache_creation_input_token_cost_batches":2.5e-06,"cache_read_input_token_cost":2e-07,"cache_read_input_token_cost_batches":1e-07,"input_cost_per_token":4e-06,"input_cost_per_token_batches":2e-06,"litellm_provider":"anthropic","max_input_tokens":1000000,"max_output_tokens":128000,"max_tokens":128000,"mode":"chat","output_cost_per_token":2e-05,"output_cost_per_token_batches":1e-05,"prompt_cache_min_tokens":512,"provider_specific_entry":{"fast":2,"us":1.1},"search_context_cost_per_query":{"search_context_size_high":0.01,"search_context_size_low":0.01,"search_context_size_medium":0.01},"source":"https://platform.claude.com/docs/en/about-claude/pricing","supports_adaptive_thinking":true,"supports_anthropic_compaction":true,"supports_assistant_prefill":false,"supports_computer_use":true,"supports_fast_mode":true,"supports_forced_tool_use":false,"supports_function_calling":true,"supports_max_reasoning_effort":true,"supports_mid_conversation_system":true,"supports_native_structured_output":true,"supports_output_config":true,"supports_pdf_input":true,"supports_prompt_caching":true,"supports_reasoning":true,"supports_response_schema":true,"supports_sampling_params":false,"supports_speed":true,"supports_tool_choice":true,"supports_vision":true,"supports_web_search":true,"supports_xhigh_reasoning_effort":true,"thinking_always_on":true}"""

OPUS_BEDROCK_GOV_SPEC = """{"bedrock_converse_supports_strict_tools":false,"cache_creation_input_token_cost":6e-06,"cache_creation_input_token_cost_above_1hr":9.6e-06,"cache_read_input_token_cost":2.4e-07,"input_cost_per_token":4.8e-06,"litellm_provider":"bedrock_converse","max_input_tokens":1000000,"max_output_tokens":128000,"max_tokens":128000,"mode":"chat","output_cost_per_token":2.4e-05,"prompt_cache_min_tokens":512,"source":"https://aws.amazon.com/bedrock/pricing/","supports_adaptive_thinking":true,"supports_assistant_prefill":false,"supports_computer_use":true,"supports_forced_tool_use":false,"supports_function_calling":true,"supports_max_reasoning_effort":true,"supports_mid_conversation_system":true,"supports_native_structured_output":false,"supports_output_config":true,"supports_parallel_tool_use_config":true,"supports_pdf_input":true,"supports_prompt_caching":true,"supports_reasoning":true,"supports_response_schema":true,"supports_sampling_params":false,"supports_tool_choice":true,"supports_tool_search":true,"supports_vision":true,"supports_xhigh_reasoning_effort":true,"thinking_always_on":true}"""

GPT_SPEC = """{"cache_creation_input_token_cost":2.5e-06,"cache_creation_input_token_cost_above_12hr":5e-06,"cache_creation_input_token_cost_above_12hr_above_272k_tokens":1e-05,"cache_creation_input_token_cost_above_12hr_above_272k_tokens_flex":5e-06,"cache_creation_input_token_cost_above_12hr_above_272k_tokens_priority":2e-05,"cache_creation_input_token_cost_above_12hr_flex":2.5e-06,"cache_creation_input_token_cost_above_12hr_priority":1e-05,"cache_creation_input_token_cost_above_272k_tokens":5e-06,"cache_creation_input_token_cost_above_272k_tokens_batches":2.5e-06,"cache_creation_input_token_cost_above_272k_tokens_flex":2.5e-06,"cache_creation_input_token_cost_above_272k_tokens_priority":1e-05,"cache_creation_input_token_cost_batches":1.25e-06,"cache_creation_input_token_cost_flex":1.25e-06,"cache_creation_input_token_cost_priority":5e-06,"cache_read_input_token_cost":2e-07,"cache_read_input_token_cost_above_272k_tokens":4e-07,"cache_read_input_token_cost_above_272k_tokens_batches":2e-07,"cache_read_input_token_cost_above_272k_tokens_flex":2e-07,"cache_read_input_token_cost_above_272k_tokens_priority":8e-07,"cache_read_input_token_cost_batches":1e-07,"cache_read_input_token_cost_flex":1e-07,"cache_read_input_token_cost_priority":4e-07,"input_cost_per_token":2e-06,"input_cost_per_token_above_272k_tokens":4e-06,"input_cost_per_token_above_272k_tokens_batches":2e-06,"input_cost_per_token_above_272k_tokens_flex":2e-06,"input_cost_per_token_above_272k_tokens_priority":8e-06,"input_cost_per_token_batches":1e-06,"input_cost_per_token_flex":1e-06,"input_cost_per_token_priority":4e-06,"litellm_provider":"openai","max_input_tokens":922000,"max_output_tokens":128000,"max_tokens":128000,"mode":"chat","output_cost_per_token":1e-05,"output_cost_per_token_above_272k_tokens":1.5e-05,"output_cost_per_token_above_272k_tokens_batches":7.5e-06,"output_cost_per_token_above_272k_tokens_flex":7.5e-06,"output_cost_per_token_above_272k_tokens_priority":3e-05,"output_cost_per_token_batches":5e-06,"output_cost_per_token_flex":5e-06,"output_cost_per_token_priority":2e-05,"regional_processing_uplift_multiplier_eu":1.1,"regional_processing_uplift_multiplier_us":1.1,"search_context_cost_per_query":{"search_context_size_high":0.01,"search_context_size_low":0.01,"search_context_size_medium":0.01},"source":"https://developers.openai.com/api/docs/pricing","supported_endpoints":["/v1/chat/completions","/v1/batch","/v1/responses"],"supported_modalities":["text","image"],"supported_output_modalities":["text"],"supports_computer_use":true,"supports_function_calling":true,"supports_max_reasoning_effort":true,"supports_minimal_reasoning_effort":false,"supports_native_streaming":true,"supports_none_reasoning_effort":true,"supports_parallel_function_calling":true,"supports_pdf_input":true,"supports_prompt_cache_breakpoint":true,"supports_prompt_caching":true,"supports_reasoning":true,"supports_response_schema":true,"supports_system_messages":true,"supports_tool_choice":true,"supports_tool_search":true,"supports_vision":true,"supports_web_search":true,"supports_xhigh_reasoning_effort":true}"""

GPT_AZURE_EU_SPEC = """{"cache_creation_input_token_cost":3e-06,"cache_creation_input_token_cost_above_272k_tokens":6e-06,"cache_read_input_token_cost":2.4e-07,"cache_read_input_token_cost_above_272k_tokens":4.8e-07,"deprecation_date":"2028-03-11","input_cost_per_token":2.4e-06,"input_cost_per_token_above_272k_tokens":4.8e-06,"litellm_provider":"azure","max_input_tokens":922000,"max_output_tokens":128000,"max_tokens":128000,"mode":"chat","output_cost_per_token":1.2e-05,"output_cost_per_token_above_272k_tokens":1.8e-05,"search_context_cost_per_query":{"search_context_size_high":0.01,"search_context_size_low":0.01,"search_context_size_medium":0.01},"source":"https://azure.microsoft.com/en-us/blog/gpt-6-astra-sol-and-luna-for-production-agents-in-microsoft-foundry/","supported_endpoints":["/v1/chat/completions","/v1/responses"],"supported_modalities":["text","image"],"supported_output_modalities":["text"],"supports_computer_use":true,"supports_function_calling":true,"supports_max_reasoning_effort":true,"supports_minimal_reasoning_effort":false,"supports_native_streaming":true,"supports_none_reasoning_effort":true,"supports_parallel_function_calling":true,"supports_pdf_input":true,"supports_prompt_caching":true,"supports_reasoning":true,"supports_response_schema":true,"supports_system_messages":true,"supports_tool_choice":true,"supports_vision":true,"supports_web_search":true,"supports_xhigh_reasoning_effort":true}"""

PROVIDERS = [  # (id, name, category)
    ("anthropic", "Anthropic", "frontier"),
    ("openai", "OpenAI", "frontier"),
    ("bedrock", "AWS - Bedrock", "cloud"),
    ("azure", "Azure", "cloud"),
]

MODELS = [  # (guids key, internal id, LiteLLM key, provider id, name, status, spec)
    ("opus", "claude-opus-5-5", "claude-opus-5-5", "anthropic",
     "claude-opus-5-5", "active", OPUS_SPEC),
    ("opus_bedrock_gov", "bedrock-us-gov-east-1-anthropic-claude-opus-5-5",
     "bedrock/us-gov-east-1/anthropic.claude-opus-5-5", "bedrock",
     "anthropic.claude-opus-5-5", "active", OPUS_BEDROCK_GOV_SPEC),
    ("gpt", "gpt-6-sol", "gpt-6-sol", "openai", "gpt-6-sol", "active", GPT_SPEC),
    ("gpt_azure_eu", "azure-eu-gpt-6-sol", "azure/eu/gpt-6-sol", "azure",
     "gpt-6-sol", "deprecating", GPT_AZURE_EU_SPEC),
]

CAPS = ["functionCalling", "jsonMode", "promptCaching", "reasoning", "streaming",
        "structuredOutputs", "toolCalling", "vision"]

_NS = uuid.uuid5(uuid.NAMESPACE_DNS, "impulse.catalog")


def _guid(*parts: str) -> str:
    """Same deterministic UUIDv5 scheme as the sync."""
    return str(uuid.uuid5(_NS, ":".join(parts)))


def _history(now: datetime) -> list[tuple]:
    """Price-history rows (model id, input, output, cached, days ago)."""
    rows = [
        ("gpt-6-sol", 2.0, 10.0, 0.2, 10),  # a real list-price cut, 2.0 -> 1.5 input
        ("gpt-6-sol", 1.5, 10.0, 0.2, 3),
        ("claude-opus-5-5", 4.0, 20.0, 0.2, 12),  # only the cached price moved
        ("claude-opus-5-5", 4.0, 20.0, 0.1, 4),
        ("bedrock-us-gov-east-1-anthropic-claude-opus-5-5", 4.8, 24.0, 0.24, 20),  # first sighting
        ("azure-eu-gpt-6-sol", 3.0, 12.0, 0.3, 45),  # previous row outside a 30-day window
        ("azure-eu-gpt-6-sol", 2.4, 12.0, 0.24, 20),
        ("retired-model", 1.0, 2.0, None, 9),  # orphan: no longer in `models`
        ("retired-model", 0.5, 1.0, None, 2),
    ]
    return [(mid, i, o, c, (now - timedelta(days=d)).isoformat()) for mid, i, o, c, d in rows]


def _build_catalog(path: str) -> None:
    now = datetime.now(timezone.utc)
    conn = sqlite3.connect(path)
    conn.executescript((_ROOT / "sync" / "db" / "schema.sql").read_text())
    with conn:
        conn.executemany(
            "INSERT INTO providers (id, guid, name, category) VALUES (?,?,?,?)",
            [(pid, _guid("provider", pid), name, cat) for pid, name, cat in PROVIDERS])
        for _, mid, key, pid, name, status, raw in MODELS:
            spec = json.loads(raw)
            cached = spec.get("cache_read_input_token_cost")
            conn.execute(
                "INSERT INTO models (id, guid, provider_id, name, mode, litellm_provider, status, "
                "input_per_mtok, output_per_mtok, cached_input_per_mtok, context_window, "
                "max_output_tokens) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (mid, _guid("model", spec["litellm_provider"], key), pid, name, "chat",
                 spec["litellm_provider"], status, spec["input_cost_per_token"] * 1e6,
                 spec["output_cost_per_token"] * 1e6, cached * 1e6 if cached else None,
                 spec["max_input_tokens"], spec["max_output_tokens"]))
            conn.execute("INSERT INTO model_raw (model_id, model_spec) VALUES (?,?)", (mid, raw))
            conn.execute("INSERT INTO model_enrichment (model_id, description, release_date) "
                         "VALUES (?,?,?)", (mid, f"{name} fixture.", "2026-09-22"))
            conn.executemany("INSERT INTO model_capabilities (model_id, capability_key) VALUES (?,?)",
                             [(mid, c) for c in CAPS])
            conn.executemany("INSERT INTO model_modalities (model_id, modality, direction) "
                             "VALUES (?,?,?)", [(mid, "text", "input"), (mid, "text", "output")])
        conn.executemany(
            "INSERT INTO model_price_history (model_id, input_per_mtok, output_per_mtok, "
            "cached_input_per_mtok, recorded_at) VALUES (?,?,?,?,?)", _history(now))
        conn.executemany("INSERT INTO meta (key, value) VALUES (?,?)",
                         [("generated_at", now.isoformat()), ("models", str(len(MODELS)))])
    conn.close()


@pytest.fixture(scope="session", autouse=True)
def catalog_db() -> str:
    _build_catalog(os.environ["IMPULSE_DB_PATH"])
    return os.environ["IMPULSE_DB_PATH"]


@pytest.fixture(scope="session")
def client(catalog_db):
    # A loopback peer is the trusted frontend; tests that need a public client send
    # X-Forwarded-For.
    return TestClient(app, client=("127.0.0.1", 50000))


@pytest.fixture(scope="session")
def guids() -> dict[str, str]:
    return {k: _guid("model", json.loads(raw)["litellm_provider"], key)
            for k, _, key, _, _, _, raw in MODELS}


@pytest.fixture(scope="session")
def specs() -> dict[str, dict]:
    """The fixture models' parsed specs, keyed like `guids`."""
    return {k: json.loads(raw) for k, *_, raw in MODELS}
