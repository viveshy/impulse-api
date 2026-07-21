# impulse-api

The **Impulse backend** - a read-only HTTP API plus the catalog **sync** that builds its
database. It powers the [Impulse web app](https://github.com/viveshy/impulse-llm); the app never touches the database
directly.

```
impulse-api/
  app/     the read API (FastAPI)
  sync/    the catalog sync - builds/refreshes the SQLite database from open sources
```

Impulse's focus is **open-weight models and their alternatives**, built entirely on open,
free data (no paid providers). Gaps are left honest, never fabricated.

## Quick start

```bash
# 1) Build the catalog (writes sync/impulse.db)
cd sync && uv run sync && cd ..

# 2) Serve the API (reads sync/impulse.db by default)
uv run serve          # http://localhost:8080  ·  interactive docs at /docs
```

The API is read-only, paginated, and rate-limited, so the curated catalog can't be
one-click scraped. Every model and provider is addressed by an **opaque, stable GUID** -
internal slug ids and model names never appear in a URL.

---

## The sync (`sync/`)

One-shot, idempotent job that builds the read-optimized SQLite catalog and can be re-run
anytime (manually or from a cron/timer) to refresh it.

```bash
cd sync
uv run sync           # fetch all sources + curated overlay → rebuild ./impulse.db
```

Sources (all public, no key):

| Source | Fills |
|---|---|
| **LiteLLM** | the model universe: pricing, context, capabilities, modalities, mode |
| **OpenRouter** | descriptions, release dates, `hugging_face_id` link, host uptime → availability |
| **Hugging Face** | license, downloads→popularity, params→VRAM, tags |
| **Aider + HF Open-LLM leaderboards** | benchmark scores |
| **Curated overlay** (`sync/data/enrichment/`) | open-family licenses/runtimes, provider regions/SDKs/apiBase/authType |

Deterministic UUIDv5 GUIDs, a 30-day price-history log, open-weight/self-host data
(license, runtimes, VRAM) as first-class fields. Field-by-field source reference:
[`sync/docs/DATA_SOURCES.md`](sync/docs/DATA_SOURCES.md). Config (env): `IMPULSE_DB_PATH`,
`LITELLM_REF`, `URL_OPENROUTER`, `IMPULSE_ENRICHMENT_DIR`, `HTTP_TIMEOUT`.

---

## The API (`app/`)

Structure: `router → handler → dao → utils`. Read-only connection (`mode=ro`), camelCase
DTOs, fixed-window rate limit. Config (env): `IMPULSE_DB_PATH` (defaults to
`sync/impulse.db`), `PORT`, `HOST`, `RELOAD`, `PAGE_DEFAULT`/`PAGE_MAX`,
`RATE_LIMIT`/`RATE_WINDOW`, `CORS_ORIGINS`.

| Method · Path | Purpose |
|---|---|
| `GET /health` | liveness |
| `GET /v1/meta` | catalog freshness + counts |
| `GET /v1/models` | paginated list - `q, mode, open_weights, capability, provider, max_price, sort` |
| `GET /v1/models/{guid}` | full model detail (caps, modalities, tags, runtimes, benchmarks, endpoints) |
| `GET /v1/models/{guid}/alternatives` | **two-tier** - open-weight first (tagged), then cheaper (any license) |
| `GET /v1/models/{guid}/price-history` | 30-day price log |
| `GET /v1/providers` | paginated list - `category, q` |
| `GET /v1/providers/{guid}` | provider detail (regions, endpoints, SDKs) |

### Alternatives - the flagship

`GET /v1/models/{guid}/alternatives` returns two ranked tiers: **`openAlternatives`**
(open-weight, each tagged `Open Source` or `Open Weight`) then **`cheaperAlternatives`**
(any license, genuinely cheaper). Both constrained to the same kind of model.

## Deploy

Run the sync on a timer to refresh `sync/impulse.db`; serve `app` with uvicorn behind a
reverse proxy. The API opens the DB read-only, so serving while re-syncing is safe (the
sync rebuilds in a single transaction).

## Contributing

Issues and PRs welcome. The catalog is built entirely from open, free data - see
[`sync/docs/DATA_SOURCES.md`](sync/docs/DATA_SOURCES.md).

## License

Released under the MIT License - see [`LICENSE`](./LICENSE).
