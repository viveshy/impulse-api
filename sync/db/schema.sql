-- =============================================================================
-- Impulse · normalized SQLite catalog (the serving store)
--
-- WRITE-ONCE-PER-SYNC, READ-ON-EVERY-REQUEST. Rebuilt by the sync script from
-- LiteLLM (factual/live) + data/enrichment/*.json (curated, git-tracked, never
-- clobbered). The BE only READS this DB. Fully normalized (3NF).
--
-- RULE: `providers` + `models` hold ONLY the LiteLLM base fields. EVERYTHING
-- extra gets its own table - enrichment (curated), arrays, reference vocab, and
-- the price-history log.
--
--   REFERENCE   capabilities · licenses
--   PROVIDER    providers ─┬─ provider_endpoints         (base)
--                          └─ provider_enrichment · provider_regions · provider_sdks   (extra)
--   MODEL       models  ─┬─ model_raw · model_modalities · model_endpoints · model_capabilities   (base)
--                        └─ model_enrichment · model_tags · model_runtimes · model_benchmarks      (extra)
--   HISTORY     model_price_history   (append-only, persists across rebuilds, 30-day window)
-- =============================================================================

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT) STRICT;

-- ========================= REFERENCE =========================================
CREATE TABLE IF NOT EXISTS capabilities (
  key TEXT PRIMARY KEY, label TEXT NOT NULL, category TEXT NOT NULL, sort_order INTEGER NOT NULL
) STRICT;

CREATE TABLE IF NOT EXISTS licenses (
  id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, url TEXT, is_open INTEGER NOT NULL DEFAULT 0
) STRICT;

-- ========================= PROVIDER (base) ===================================
CREATE TABLE IF NOT EXISTS providers (
  id        TEXT PRIMARY KEY,                 -- internal slug (joins only; never exposed)
  guid      TEXT NOT NULL,                    -- public, opaque, stable (UUIDv5) - the API's id
  name      TEXT NOT NULL,
  website   TEXT NOT NULL DEFAULT '',
  api_base  TEXT NOT NULL DEFAULT '',         -- real inference base URL (curated; '' = unknown)
  category  TEXT NOT NULL CHECK (category IN ('frontier','open','cloud','inference')),
  is_active INTEGER NOT NULL DEFAULT 1
) STRICT;
CREATE UNIQUE INDEX IF NOT EXISTS idx_providers_guid ON providers(guid);
CREATE INDEX IF NOT EXISTS idx_providers_category ON providers(category) WHERE is_active = 1;

CREATE TABLE IF NOT EXISTS provider_endpoints (
  id          TEXT PRIMARY KEY,               -- '<provider>:<key>'
  provider_id TEXT NOT NULL REFERENCES providers(id) ON DELETE CASCADE,
  name        TEXT NOT NULL,
  method      TEXT NOT NULL CHECK (method IN ('GET','POST','PUT','DELETE')),
  path        TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  streaming   INTEGER NOT NULL DEFAULT 0,
  auth        TEXT NOT NULL DEFAULT 'API key'
) STRICT;
CREATE INDEX IF NOT EXISTS idx_provider_endpoints_provider ON provider_endpoints(provider_id);

-- ------------------------- PROVIDER (extra / curated) ------------------------
CREATE TABLE IF NOT EXISTS provider_enrichment (
  provider_id  TEXT PRIMARY KEY REFERENCES providers(id) ON DELETE CASCADE,
  description  TEXT NOT NULL DEFAULT '',
  auth_type    TEXT NOT NULL DEFAULT 'api-key' CHECK (auth_type IN ('api-key','bearer','oauth','aws-sigv4')),
  monogram     TEXT,
  founded_year INTEGER
) STRICT;

CREATE TABLE IF NOT EXISTS provider_regions (
  provider_id TEXT NOT NULL REFERENCES providers(id) ON DELETE CASCADE,
  region      TEXT NOT NULL,
  PRIMARY KEY (provider_id, region)
) STRICT, WITHOUT ROWID;

CREATE TABLE IF NOT EXISTS provider_sdks (
  id INTEGER PRIMARY KEY,
  provider_id TEXT NOT NULL REFERENCES providers(id) ON DELETE CASCADE,
  language TEXT NOT NULL, package_name TEXT NOT NULL DEFAULT '',
  install_command TEXT NOT NULL DEFAULT '', docs_url TEXT NOT NULL DEFAULT ''
) STRICT;
CREATE INDEX IF NOT EXISTS idx_provider_sdks_provider ON provider_sdks(provider_id);

-- ========================= MODEL (base) ======================================
CREATE TABLE IF NOT EXISTS models (
  id                    TEXT PRIMARY KEY,              -- internal slug (joins only; never exposed)
  guid                  TEXT NOT NULL,                 -- public, opaque, stable (UUIDv5) - the API's id
  provider_id           TEXT NOT NULL REFERENCES providers(id) ON DELETE RESTRICT,
  name                  TEXT NOT NULL,                 -- display name
  family                TEXT,
  mode                  TEXT NOT NULL,
  litellm_provider      TEXT NOT NULL,                 -- exact LiteLLM route slug
  status                TEXT NOT NULL DEFAULT 'active'
                          CHECK (status IN ('active','deprecating','deprecated','preview')),
  input_per_mtok        REAL NOT NULL DEFAULT 0,
  output_per_mtok       REAL,
  cached_input_per_mtok REAL,
  context_window        INTEGER NOT NULL DEFAULT 0,
  max_output_tokens     INTEGER NOT NULL DEFAULT 0,
  is_active             INTEGER NOT NULL DEFAULT 1
) STRICT;
CREATE UNIQUE INDEX IF NOT EXISTS idx_models_guid ON models(guid);
CREATE INDEX IF NOT EXISTS idx_models_provider   ON models(provider_id)    WHERE is_active = 1;
CREATE INDEX IF NOT EXISTS idx_models_mode        ON models(mode)           WHERE is_active = 1;
CREATE INDEX IF NOT EXISTS idx_models_input_price ON models(input_per_mtok) WHERE is_active = 1;
CREATE INDEX IF NOT EXISTS idx_models_context     ON models(context_window) WHERE is_active = 1;

CREATE TABLE IF NOT EXISTS model_raw (
  model_id   TEXT PRIMARY KEY REFERENCES models(id) ON DELETE CASCADE,
  model_spec TEXT NOT NULL DEFAULT '{}'       -- verbatim LiteLLM cost-map entry
) STRICT;

CREATE TABLE IF NOT EXISTS model_modalities (
  model_id  TEXT NOT NULL REFERENCES models(id) ON DELETE CASCADE,
  modality  TEXT NOT NULL CHECK (modality IN ('text','image','audio','video','embedding')),
  direction TEXT NOT NULL CHECK (direction IN ('input','output')),
  PRIMARY KEY (model_id, direction, modality)
) STRICT, WITHOUT ROWID;

CREATE TABLE IF NOT EXISTS model_endpoints (
  model_id    TEXT NOT NULL REFERENCES models(id) ON DELETE CASCADE,
  endpoint_id TEXT NOT NULL REFERENCES provider_endpoints(id) ON DELETE CASCADE,
  PRIMARY KEY (model_id, endpoint_id)
) STRICT, WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS idx_model_endpoints_endpoint ON model_endpoints(endpoint_id);

CREATE TABLE IF NOT EXISTS model_capabilities (
  model_id       TEXT NOT NULL REFERENCES models(id) ON DELETE CASCADE,
  capability_key TEXT NOT NULL REFERENCES capabilities(key) ON DELETE RESTRICT,
  PRIMARY KEY (model_id, capability_key)
) STRICT, WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS idx_model_capabilities_cap ON model_capabilities(capability_key);

-- ------------------------- MODEL (extra / curated) ---------------------------
CREATE TABLE IF NOT EXISTS model_enrichment (
  model_id          TEXT PRIMARY KEY REFERENCES models(id) ON DELETE CASCADE,
  description       TEXT NOT NULL DEFAULT '',
  release_date      TEXT NOT NULL DEFAULT '',
  popularity        INTEGER,
  is_open_weights   INTEGER NOT NULL DEFAULT 0,
  license_id        INTEGER REFERENCES licenses(id) ON DELETE SET NULL,
  open_source_score INTEGER,
  min_vram_gb       REAL,
  ttft_ms           INTEGER,
  tokens_per_sec    REAL,
  availability_pct  REAL
) STRICT;
CREATE INDEX IF NOT EXISTS idx_model_enrichment_open ON model_enrichment(is_open_weights);
CREATE INDEX IF NOT EXISTS idx_model_enrichment_pop  ON model_enrichment(popularity DESC);

CREATE TABLE IF NOT EXISTS model_tags (
  model_id TEXT NOT NULL REFERENCES models(id) ON DELETE CASCADE,
  tag      TEXT NOT NULL,
  PRIMARY KEY (model_id, tag)
) STRICT, WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS idx_model_tags_tag ON model_tags(tag);

CREATE TABLE IF NOT EXISTS model_runtimes (
  model_id TEXT NOT NULL REFERENCES models(id) ON DELETE CASCADE,
  runtime  TEXT NOT NULL,
  PRIMARY KEY (model_id, runtime)
) STRICT, WITHOUT ROWID;

CREATE TABLE IF NOT EXISTS model_benchmarks (
  id INTEGER PRIMARY KEY,
  model_id TEXT NOT NULL REFERENCES models(id) ON DELETE CASCADE,
  name TEXT NOT NULL, score REAL NOT NULL, max REAL NOT NULL, source TEXT
) STRICT;
CREATE INDEX IF NOT EXISTS idx_model_benchmarks_model ON model_benchmarks(model_id);

-- ========================= HISTORY ===========================================
-- Append-only price log. NOT wiped on rebuild (persists) and intentionally NOT
-- FK'd to models, so it survives a model vanishing upstream. A row is written
-- only when a model's price CHANGES; rows older than 30 days are pruned.
CREATE TABLE IF NOT EXISTS model_price_history (
  id                    INTEGER PRIMARY KEY,
  model_id              TEXT NOT NULL,
  input_per_mtok        REAL NOT NULL,
  output_per_mtok       REAL,
  cached_input_per_mtok REAL,
  recorded_at           TEXT NOT NULL          -- ISO timestamp
) STRICT;
CREATE INDEX IF NOT EXISTS idx_price_history_model ON model_price_history(model_id, recorded_at DESC);

-- ------------------------- seed the 15 capabilities --------------------------
INSERT OR IGNORE INTO capabilities (key,label,category,sort_order) VALUES
  ('streaming','Streaming','Core',1),
  ('functionCalling','Function calling','Core',2),
  ('jsonMode','JSON mode','Core',3),
  ('structuredOutputs','Structured outputs','Core',4),
  ('vision','Vision','Multimodal',5),
  ('imageInput','Image input','Multimodal',6),
  ('audio','Audio','Multimodal',7),
  ('imageGeneration','Image generation','Multimodal',8),
  ('video','Video','Multimodal',9),
  ('reasoning','Reasoning','Advanced',10),
  ('toolCalling','Tool calling','Advanced',11),
  ('mcp','MCP','Advanced',12),
  ('promptCaching','Prompt caching','Advanced',13),
  ('batchApi','Batch API','Advanced',14),
  ('embeddings','Embeddings','Advanced',15);
