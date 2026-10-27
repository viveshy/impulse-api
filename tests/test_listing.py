"""route_of / spec_extras: listing facts derived from internal ids and the verbatim spec."""
from app.utils.listing import route_of, spec_extras


def test_route_of_azure_region():
    assert route_of("azure-eu-gpt-6-sol", "gpt-6-sol", "azure", "azure") == "eu"


def test_route_of_bedrock_govcloud():
    assert route_of("bedrock-us-gov-east-1-anthropic-claude-opus-5-5",
                    "anthropic.claude-opus-5-5", "bedrock", "bedrock_converse") == "us-gov-east-1"


def test_route_of_first_party_is_none():
    assert route_of("claude-opus-5-5", "claude-opus-5-5", "anthropic", "anthropic") is None


def test_route_of_vertex_default_is_none():
    assert route_of("vertex-ai-claude-opus-5-5-default", "claude-opus-5-5@default",
                    "vertex_ai", "vertex_ai-anthropic_models") is None


def test_route_of_strips_repeated_provider_prefixes():
    # id de-duplicated by the sync as "<provider>-<slug(key)>"; the vendor org is what's left
    assert route_of("vercel_ai_gateway-vercel-ai-gateway-anthropic-claude-3-5-sonnet",
                    "claude-3-5-sonnet", "vercel_ai_gateway", "vercel_ai_gateway") == "anthropic"


def test_route_of_bare_provider_prefix_is_none():
    assert route_of("azure-gpt-6-sol", "gpt-6-sol", "azure", "azure") is None


def test_route_of_dedup_suffix_and_mismatch():
    assert route_of("azure-eu-gpt-6-sol-x", "gpt-6-sol", "azure", "azure") == "eu"
    assert route_of("something-else", "gpt-6-sol", "azure", "azure") is None


def test_spec_extras_prices_and_flags():
    x = spec_extras({"input_cost_per_token_batches": 2e-06, "cache_creation_input_token_cost": 5e-06,
                     "cache_creation_input_token_cost_above_1hr": 8e-06,
                     "input_cost_per_token_above_272k_tokens": 4e-06,
                     "output_cost_per_token_above_272k_tokens": 1.5e-05,
                     "search_context_cost_per_query": {"search_context_size_low": 0.01, "search_context_size_medium": 0.02},
                     "supports_web_search": True, "supports_pdf_input": True, "supports_computer_use": False,
                     "supports_xhigh_reasoning_effort": True, "supports_none_reasoning_effort": True,
                     "deprecation_date": "2027-01-08", "source": "https://x", "rpm": 50})
    assert x["pricing"]["batchInputPerMtok"] == 2.0
    assert x["pricing"]["cacheWrite1hPerMtok"] == 8.0
    assert x["pricing"]["longContext"] == {"thresholdTokens": 272000, "inputPerMtok": 4.0, "outputPerMtok": 15.0,
                                           "cachedInputPerMtok": None, "batchInputPerMtok": None,
                                           "batchOutputPerMtok": None}
    assert x["pricing"]["webSearchPerQuery"] == 0.02
    assert x["features"] == ["pdfInput", "webSearch"]
    assert x["reasoningEfforts"] == ["none", "xhigh"]
    assert x["deprecationDate"] == "2027-01-08" and x["sourceUrl"] == "https://x"
    assert x["rateLimits"] == {"rpm": 50, "tpm": None}


def test_spec_extras_empty():
    x = spec_extras({})
    assert x["features"] == [] and x["pricing"]["longContext"] is None and x["rateLimits"] is None


def test_spec_extras_empty_shape():
    x = spec_extras({})
    assert x["deprecationDate"] is None and x["sourceUrl"] is None and x["reasoningEfforts"] == []
    assert set(x["pricing"]) == {
        "cacheWritePerMtok", "cacheWrite1hPerMtok", "batchInputPerMtok", "batchOutputPerMtok",
        "flexInputPerMtok", "flexOutputPerMtok", "priorityInputPerMtok", "priorityOutputPerMtok",
        "longContext", "webSearchPerQuery", "regionalUplift"}
    assert all(v is None for v in x["pricing"].values())


def test_spec_extras_real_gpt_6_sol(specs):
    x = spec_extras(specs["gpt"])
    p = x["pricing"]
    assert (p["flexInputPerMtok"], p["flexOutputPerMtok"]) == (1.0, 5.0)
    assert (p["priorityInputPerMtok"], p["priorityOutputPerMtok"]) == (4.0, 20.0)
    assert (p["batchInputPerMtok"], p["batchOutputPerMtok"]) == (1.0, 5.0)
    # the _batches/_flex/_priority long-context variants must not be read as thresholds
    assert p["longContext"] == {"thresholdTokens": 272000, "inputPerMtok": 4.0, "outputPerMtok": 15.0,
                                "cachedInputPerMtok": 0.4, "batchInputPerMtok": 2.0, "batchOutputPerMtok": 7.5}
    assert p["regionalUplift"] == 1.1  # regional_processing_uplift_multiplier_us
    assert p["cacheWritePerMtok"] == 2.5 and p["cacheWrite1hPerMtok"] is None
    assert x["reasoningEfforts"] == ["none", "xhigh", "max"]
    assert "minimal" not in x["reasoningEfforts"]


def test_spec_extras_real_opus(specs):
    x = spec_extras(specs["opus"])
    assert x["pricing"]["regionalUplift"] == 1.1  # provider_specific_entry.us
    assert x["pricing"]["webSearchPerQuery"] == 0.01
    assert x["pricing"]["cacheWritePerMtok"] == 5.0 and x["pricing"]["cacheWrite1hPerMtok"] == 8.0
    assert x["features"] == ["adaptiveThinking", "computerUse", "fastMode", "nativeStructuredOutput",
                             "pdfInput", "promptCaching", "thinkingAlwaysOn", "webSearch"]
    assert x["sourceUrl"] == "https://platform.claude.com/docs/en/about-claude/pricing"


def test_spec_extras_long_context_takes_smallest_threshold():
    x = spec_extras({"input_cost_per_token_above_512k_tokens": 6e-06,
                     "input_cost_per_token_above_200k_tokens": 5e-06,
                     "input_cost_per_token_above_128k_tokens_priority": 9e-06,
                     "output_cost_per_token_above_512k_tokens": 3e-05})
    assert x["pricing"]["longContext"] == {"thresholdTokens": 200000, "inputPerMtok": 5.0,
                                           "outputPerMtok": None, "cachedInputPerMtok": None,
                                           "batchInputPerMtok": None, "batchOutputPerMtok": None}


def test_spec_extras_long_context_carries_its_cache_and_batch_prices():
    # Past the threshold every price steps up: cache reads and the batch price too.
    x = spec_extras({"input_cost_per_token_above_100k_tokens": 5e-07,
                     "output_cost_per_token_above_100k_tokens": 2.5e-06,
                     "cache_read_input_token_cost_above_100k_tokens": 5e-08,
                     "input_cost_per_token_above_100k_tokens_batches": 2.5e-07,
                     "output_cost_per_token_above_100k_tokens_batches": 1.25e-06,
                     "input_cost_per_token_batches": 5e-08})
    assert x["pricing"]["longContext"] == {"thresholdTokens": 100000, "inputPerMtok": 0.5, "outputPerMtok": 2.5,
                                           "cachedInputPerMtok": 0.05, "batchInputPerMtok": 0.25,
                                           "batchOutputPerMtok": 1.25}


def test_spec_extras_web_search_fallbacks():
    def ws(v):
        return spec_extras({"search_context_cost_per_query": v})["pricing"]["webSearchPerQuery"]
    assert ws({"search_context_size_low": 0.01, "search_context_size_high": 0.03}) == 0.01
    assert ws({"search_context_size_high": 0.03}) == 0.03
    assert ws(0.025) == 0.025
    assert ws("n/a") is None


def test_spec_extras_reasoning_levels_merge_in_order():
    x = spec_extras({"reasoning_effort_levels": ["max", "low", "bogus"],
                     "supports_minimal_reasoning_effort": True,
                     "supports_none_reasoning_effort": False})
    assert x["reasoningEfforts"] == ["minimal", "low", "max"]


def test_spec_extras_regional_uplift_absent_without_us():
    x = spec_extras({"provider_specific_entry": {"dashscope_video_reference_input": 1}})
    assert x["pricing"]["regionalUplift"] is None


def test_spec_extras_ignores_non_numeric_prices():
    x = spec_extras({"input_cost_per_token_batches": "2e-06", "cache_creation_input_token_cost": True,
                     "rpm": "50", "tpm": 4000000.0})
    assert x["pricing"]["batchInputPerMtok"] is None
    assert x["pricing"]["cacheWritePerMtok"] is None
    assert x["rateLimits"] == {"rpm": None, "tpm": 4000000.0}
