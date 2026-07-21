# Impulse - Data Sources

Impulse is built entirely on **open, free data**. Artificial Analysis was evaluated and
**deliberately dropped** - its useful data sits behind an expensive plan, and the whole
point of Impulse is to give people that intelligence *without* paying for it. Everything
below is public and no-auth (or free-tier), so the catalog stays reproducible and honest.

**LiteLLM** is the broad base (the whole model universe + pricing). **OpenRouter** and
**Hugging Face** enrich it (descriptions, release dates, license, popularity, self-host
VRAM). **Open benchmark leaderboards** fill the quality/benchmark gap (planned - see §4).
Base facts are live/factual; nothing is fabricated, and gaps are left honestly empty.

> Impulse's focus is **open-weight models and their alternatives** ("show me the open model
> I can run instead of Fable/Sonnet"). So Hugging Face (license, downloads, params→VRAM) is
> the highest-value enricher, and OpenRouter's `hugging_face_id` is the glue that links a
> model to its HF repo automatically.

**Status legend:** ✅ implemented in the sync · ◻ planned next.

---

## Coverage matrix - who fills what

| Impulse field | LiteLLM ✅ | OpenRouter ✅ | Hugging Face ✅ | Open leaderboards ◻ |
|---|:--:|:--:|:--:|:--:|
| model universe / ids | ● (~2,970) | ● (~340) | - | - |
| input/output/cache pricing | ● | ● | - | - |
| context window / max output | ● | ● | - | - |
| capabilities (`supports_*`) | ● | ● (params) | - | - |
| modalities | ● | ● | - | - |
| mode / deprecation | ● | ● (cutoff) | - | - |
| **description** | - | ● | ● (card) | - |
| **release date** | - | ● (`created`) | ● (`createdAt`) | - |
| **is_open_weights** | - | - | ● (on-Hub ⇒ open) | - |
| **license** | - | overlay | ● | - |
| **popularity** | - | - | ● (downloads) | - |
| **params → VRAM / self-host** | - | - | ● (safetensors) | - |
| tags | - | - | ● | - |
| **benchmarks / quality index** | - | - | - | ● |
| `hugging_face_id` (linkage) | - | ● | - | - |

*Numbers reflect the current sync: 2,966 models · 104 providers · 866 OpenRouter matches ·
361 HF matches (356 with computed VRAM). Benchmarks are the one honest gap remaining.*

---

## 1. LiteLLM - the base universe ✅

Static JSON on GitHub-raw (no API, no auth). Broadest coverage.

| | |
|---|---|
| **Auth** | none |
| **Coverage** | ~2,970 models · ~170 providers (104 referenced after mapping) |
| **Refresh** | re-run anytime (pin `LITELLM_REF`) |

```bash
# models (pricing, context, capabilities, modalities, mode)
curl -s https://raw.githubusercontent.com/BerriAI/litellm/main/model_prices_and_context_window.json
# providers + supported endpoints
curl -s https://raw.githubusercontent.com/BerriAI/litellm/main/provider_endpoints_support.json
```

**Per-model fields:** `litellm_provider`, `mode`, `max_input_tokens`, `max_output_tokens`,
`input_cost_per_token`, `output_cost_per_token`, `cache_read_input_token_cost`,
`input_cost_per_token_batches`, `supported_modalities`, `supported_output_modalities`,
`supported_endpoints`, `deprecation_date`, and every `supports_*` flag
(`supports_vision`, `supports_function_calling`, `supports_tool_choice`,
`supports_response_schema`, `supports_reasoning`, `supports_prompt_caching`,
`supports_audio_input/output`, `supports_native_streaming`, …).

**Fills:** the universe + pricing, context, capabilities, modalities, mode, deprecation.
Mapped in `app/mapping.py`; pricing scaled ×1e6 (per-token → per-Mtok).

---

## 2. OpenRouter - descriptions, release, HF linkage ✅

Public models catalog. Listing needs no key (a key is only for *inference*).

| | |
|---|---|
| **Auth** | none for `/models` |
| **Coverage** | ~340 models (curated); **866 LiteLLM models matched** |
| **Refresh** | every sync |

```bash
curl -s https://openrouter.ai/api/v1/models | jq '.data[0]'
```

**Per-model fields:** `id`, `canonical_slug`, **`hugging_face_id`**, `name`,
`created` (unix → release date), **`description`**, `context_length`,
`architecture{ modality, input_modalities[], output_modalities[], tokenizer }`,
`pricing{ prompt, completion, request, image, input_cache_read, input_cache_write }`,
`top_provider{ context_length, max_completion_tokens, is_moderated }`,
`supported_parameters[]`, `knowledge_cutoff`.

**Fills:** descriptions, release date, **`hugging_face_id`** (the HF join key).
Implemented in `app/sources/openrouter.py`. Matching (`app/sources/openrouter.py:keys_for`)
normalizes names to alphanumeric last-segment keys with a date-stripped variant, so
`claude-3-5-sonnet-20241022` (LiteLLM) resolves to `anthropic/claude-3.5-sonnet`
(OpenRouter). Best-effort: popular/featured models match; the long tail stays LiteLLM-only.

---

## 3. Hugging Face Hub - the open-weight goldmine ✅

Public model metadata; no auth (a token only raises rate limits for bulk pulls).

| | |
|---|---|
| **Auth** | none (token optional for bulk) |
| **Coverage** | every open model on the Hub; fetched by `hugging_face_id` from OpenRouter |
| **Refresh** | every sync (one call per *unique* repo - ~100 calls, deduped) |

```bash
curl -s https://huggingface.co/api/models/meta-llama/Llama-3.3-70B-Instruct
```

**Fields used:** `createdAt` (release), **`downloads`**, `likes`, `gated`, `pipeline_tag`,
`tags[]`, `cardData{ license }`, **`safetensors{ total }`** (parameter count).

**Fills (open models):** license, **popularity** (log-scaled downloads → 0-100), **parameter
count → VRAM**, release date (fallback), tags. A repo published on the Hub *with weights* is
treated as open-weight. Implemented in `app/sources/huggingface.py`.

*VRAM estimate (fp16 baseline):* `params × 2 bytes × 1.2` overhead. INT8 ≈ `× 1`, 4-bit ≈ `× 0.5`.
e.g. Llama-3.2-1B → 3.0 GB, Qwen3-8B → 19.7 GB, Gemma-4-31B → 78.4 GB.

*Popularity:* `min(100, round(12 · log10(downloads+1)))` - a real, monotonic signal, not a guess.

---

## 4. Open benchmark leaderboards - quality/benchmarks ◻ (planned)

Replaces Artificial Analysis's benchmark/Openness data with **free, open** equivalents.
This is the one remaining honest gap: `model_benchmarks` is currently populated only from the
curated overlay. Verified programmatic-access sources (no scraping, stable formats):

| Source | Data | Access |
|---|---|---|
| **HF Open LLM Leaderboard v2** (archived Jun 2025, results public) | MMLU-Pro, GPQA, MATH, IFEval, BBH, MuSR | HF datasets-server API → parquet (`open-llm-leaderboard/contents`) |
| **Aider polyglot leaderboard** | real-world coding edit/refactor pass-rate | plain YAML in the `Aider-AI/aider` GitHub repo |
| **EvalPlus** (HumanEval+, MBPP+) | rigorous code-gen pass@1 | JSON in the `evalplus/evalplus` GitHub repo |
| **LiveBench** | contamination-free monthly benchmark | downloadable result files (CSV/JSON) |
| **LMArena / Chatbot Arena** | human-preference Elo | periodic CSV snapshot published as an HF dataset |

```bash
# HF Open LLM Leaderboard v2 results (parquet via datasets-server)
curl -s "https://datasets-server.huggingface.co/rows?dataset=open-llm-leaderboard%2Fcontents&config=default&split=train&offset=0&length=100"
# Aider leaderboard (YAML in-repo)
curl -s https://raw.githubusercontent.com/Aider-AI/aider/main/aider/website/_data/polyglot_leaderboard.yml
```

**Will fill:** benchmark scores + a self-computed quality/intelligence index into
`model_benchmarks` (name/score/max/source). Matched to models by normalized name + HF id.
Impulse computes its own openness score from HF facts (license open? weights present?
params known?) - no paid Openness Index needed.

---

## Identity matching (how sources are merged)

- **OpenRouter ↔ Hugging Face:** direct via `hugging_face_id`.
- **LiteLLM ↔ OpenRouter:** normalized keys (`openrouter.keys_for`): alphanumeric last-segment
  + a trailing-date-stripped variant.
- **Open leaderboards ↔ others:** normalized name + HF id (planned).
- **Precedence:** base facts (pricing/context/caps) → LiteLLM, filled by OpenRouter;
  openness/license/params/popularity → Hugging Face; descriptions/release → OpenRouter then HF;
  benchmarks → open leaderboards. The **curated overlay wins over all** (manual fixes,
  never clobbered by a sync).

## Refresh cadence

Re-run the sync anytime - it's idempotent and atomic. Pricing/models move on the order of
days. One bulk call each for LiteLLM + OpenRouter; ~100 deduped calls for HF. Price changes
are captured in `model_price_history` (row written only on change, 30-day window).

## Sources

- LiteLLM catalog files - <https://github.com/BerriAI/litellm>
- OpenRouter models API - <https://openrouter.ai/api/v1/models>
- Hugging Face Hub API - <https://huggingface.co/docs/hub/api>
- HF Open LLM Leaderboard - <https://huggingface.co/open-llm-leaderboard>
- Aider leaderboards - <https://aider.chat/docs/leaderboards/>
- EvalPlus - <https://github.com/evalplus/evalplus>
