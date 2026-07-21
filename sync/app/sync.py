"""
The one script: populate & refresh the Impulse SQLite catalog.

  LiteLLM public files + curated overlay  →  map/merge  →  rebuild the normalized DB.

(Multi-source: OpenRouter + Hugging Face enrichment layer on top of this base - added
next.) Idempotent & atomic. Reference data (capabilities/licenses) and the price-history
log persist across rebuilds; a price row is written only when a model's price changes.
"""
import json
import logging
from datetime import datetime, timedelta, timezone

import httpx

from app import mapping
from app.db import connect, init_schema, wipe_catalog
from app.enrichment import Enrichment
from app.settings import settings
from app.sources import huggingface, leaderboards, openrouter

log = logging.getLogger("impulse_sync")


def _fetch(url: str) -> dict:
    r = httpx.get(url, timeout=settings.HTTP_TIMEOUT, follow_redirects=True)
    r.raise_for_status()
    return r.json()


def _dumps(v) -> str:
    return json.dumps(v, separators=(",", ":"), ensure_ascii=False)


def _build() -> tuple[list[dict], list[dict]]:
    """Fetch LiteLLM + overlay → (provider_rows, model_rows) as flat dicts."""
    log.info("──── Fetching LiteLLM catalog (ref=%s) ────", settings.LITELLM_REF)
    prov_ep = _fetch(settings.URL_PROVIDERS).get("providers", {})
    models = _fetch(settings.URL_MODELS)
    log.info("Fetched: %d providers, %d model entries", len(prov_ep), len(models))

    enrich = Enrichment()
    log.info("Overlay: %d providers, %d models, %d openness rules",
             len(enrich.providers), len(enrich.models), len(enrich.openness_rules))

    display_by_slug, url_by_slug = {}, {}
    paths_by_slug: dict[str, set[str]] = {}

    def add_paths(slug, paths):
        s = paths_by_slug.setdefault(slug, set())
        s.update(p for p in paths if isinstance(p, str))

    for slug, p in prov_ep.items():
        display_by_slug[slug] = p.get("display_name")
        if p.get("url"):
            url_by_slug[slug] = p["url"]
        eps = p.get("endpoints", {}) or {}
        add_paths(slug, [mapping.EP_MAP[k] for k, v in eps.items() if v and k in mapping.EP_MAP])

    model_rows, seen = [], set()
    for name, entry in models.items():
        if name == "sample_spec" or not isinstance(entry, dict) or not entry.get("litellm_provider"):
            continue
        slug = mapping.vendor(entry["litellm_provider"])
        mode = mapping.infer_mode(name, entry)
        paths = entry.get("supported_endpoints") or mapping.MODE_EP.get(mode, ["/v1/chat/completions"])
        add_paths(slug, paths)

        mid = mapping.slugify(name)
        if mid in seen:
            mid = f"{slug}-{mid}"
        while mid in seen:
            mid += "-x"
        seen.add(mid)

        model_rows.append(
            mapping.map_model(name, entry, slug, paths_by_slug.get(slug, set(paths)),
                              enrich.for_model(name), mid))

    # ---- OpenRouter enrichment (descriptions, release dates, HF join key) ----
    or_data = openrouter.fetch()
    or_hits = 0
    for m in model_rows:
        orv = next((or_data[k] for k in openrouter.keys_for(m["_litellm_name"]) if k in or_data), None)
        if orv:
            or_hits += 1
            if not m["description"] and orv["description"]:
                m["description"] = orv["description"]
            if not m["release_date"] and orv["release_date"]:
                m["release_date"] = orv["release_date"]
            m["hf_id"] = orv["hugging_face_id"]
            m["or_id"] = orv.get("or_id")
            if orv["description"] or orv["release_date"]:
                m["enriched"] = 1
        # generic fallback so no model ships a blank description
        if not m["description"]:
            m["description"] = f"{mapping.titleize(m['provider_id'])} {m['mode']} model."
    log.info("OpenRouter matched %d/%d models", or_hits, len(model_rows))

    # ---- Hugging Face enrichment (license, downloads→popularity, params→VRAM) ----
    hf_data = huggingface.fetch({m["hf_id"] for m in model_rows if m.get("hf_id")})
    hf_hits = 0
    for m in model_rows:
        hf = hf_data.get(m.get("hf_id"))
        if not hf:
            continue
        hf_hits += 1
        # a repo published on HF with weights is, by definition, open-weight
        m["is_open_weights"] = 1
        if not m["license"] and hf["license"]:
            m["license"] = hf["license"]
        if m["popularity"] is None and hf["popularity"] is not None:
            m["popularity"] = hf["popularity"]
        if m["min_vram_gb"] is None and hf["min_vram_gb"] is not None:
            m["min_vram_gb"] = hf["min_vram_gb"]
        if not m["release_date"] and hf["release_date"]:
            m["release_date"] = hf["release_date"]
        if not m["tags"] and hf["tags"]:
            m["tags"] = hf["tags"]
        m["enriched"] = 1
    log.info("Hugging Face matched %d models", hf_hits)

    # ---- open benchmark leaderboards (Aider + HF Open LLM) ----
    aider = leaderboards.fetch_aider()
    open_llm = leaderboards.fetch_open_llm({m["hf_id"] for m in model_rows if m.get("hf_id")})
    bench_hits = 0
    for m in model_rows:
        extra: list[dict] = []
        hit = next((aider[k] for k in openrouter.keys_for(m["_litellm_name"]) if k in aider), None)
        if hit:
            extra += hit
        if m.get("hf_id"):
            extra += open_llm.get(m["hf_id"], [])
        if not extra:
            continue
        # curated overlay benchmarks win; leaderboards only fill names not already present
        seen = {b["name"] for b in m["benchmarks"]}
        added = []
        for b in extra:
            if b["name"] not in seen:
                seen.add(b["name"])
                added.append(b)
        if added:
            m["benchmarks"] = [*m["benchmarks"], *added]
            bench_hits += 1
    log.info("Benchmarks attached to %d models", bench_hits)

    # ---- availability from OpenRouter host uptime (the one perf field that is real) ----
    uptime = openrouter.fetch_uptime({m["or_id"] for m in model_rows if m.get("or_id")})
    up_hits = 0
    for m in model_rows:
        pct = uptime.get(m.get("or_id"))
        if pct is not None and m["availability_pct"] is None:
            m["availability_pct"] = pct
            up_hits += 1
    log.info("Availability set on %d models", up_hits)

    referenced = {m["provider_id"] for m in model_rows}
    provider_rows = [
        mapping.map_provider(slug, display_by_slug.get(slug), url_by_slug.get(slug),
                             sorted(paths_by_slug.get(slug, [])), enrich.for_provider(slug))
        for slug in sorted(referenced)
    ]
    return provider_rows, model_rows


def run_sync() -> dict:
    provider_rows, model_rows = _build()

    log.info("Writing normalized DB: %s", settings.DB_PATH)
    conn = connect()
    try:
        init_schema(conn)

        # latest recorded price per model (for change detection; persists across rebuilds)
        last_price = {
            r[0]: (r[1], r[2], r[3])
            for r in conn.execute(
                "SELECT model_id,input_per_mtok,output_per_mtok,cached_input_per_mtok FROM "
                "(SELECT *, ROW_NUMBER() OVER (PARTITION BY model_id ORDER BY recorded_at DESC) rn "
                " FROM model_price_history) WHERE rn = 1")
        }
        now = datetime.now(timezone.utc).isoformat()

        with conn:  # single transaction
            wipe_catalog(conn)

            # ---- licenses (upsert, build name→id) ----
            lic_open: dict[str, bool] = {}
            for m in model_rows:
                nm = m.get("license")
                if nm:
                    lic_open.setdefault(nm, bool(m.get("is_open_weights")))
            for nm, is_open in lic_open.items():
                conn.execute("INSERT OR IGNORE INTO licenses (name,is_open) VALUES (?,?)", (nm, int(is_open)))
            lic_id = dict(conn.execute("SELECT name,id FROM licenses"))

            # ---- providers (base + extras) ----
            conn.executemany(
                "INSERT INTO providers (id,guid,name,website,api_base,category,is_active) VALUES (?,?,?,?,?,?,1)",
                [(p["id"], p["guid"], p["name"], p["website"], p["api_base"], p["category"])
                 for p in provider_rows])
            valid_ep = set()
            ep_rows = []
            for p in provider_rows:
                for e in p["endpoints"]:
                    valid_ep.add(e["id"])
                    ep_rows.append((e["id"], p["id"], e["name"], e["method"], e["path"],
                                    e["description"], int(bool(e["streaming"])), e["auth"]))
            conn.executemany(
                "INSERT OR IGNORE INTO provider_endpoints (id,provider_id,name,method,path,description,streaming,auth) "
                "VALUES (?,?,?,?,?,?,?,?)", ep_rows)
            conn.executemany(
                "INSERT INTO provider_enrichment (provider_id,description,auth_type,monogram,founded_year) VALUES (?,?,?,?,?)",
                [(p["id"], p["description"], p["auth_type"], p["monogram"], p["founded_year"]) for p in provider_rows])
            conn.executemany("INSERT OR IGNORE INTO provider_regions (provider_id,region) VALUES (?,?)",
                             [(p["id"], r) for p in provider_rows for r in p["regions"]])
            conn.executemany(
                "INSERT INTO provider_sdks (provider_id,language,package_name,install_command,docs_url) VALUES (?,?,?,?,?)",
                [(p["id"], s.get("language", ""), s.get("packageName", ""), s.get("installCommand", ""), s.get("docsUrl", ""))
                 for p in provider_rows for s in p["sdks"]])

            # ---- models (base) ----
            conn.executemany(
                "INSERT INTO models (id,guid,provider_id,name,family,mode,litellm_provider,status,"
                "input_per_mtok,output_per_mtok,cached_input_per_mtok,context_window,max_output_tokens,is_active) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,1)",
                [(m["id"], m["guid"], m["provider_id"], m["name"], m["family"], m["mode"], m["litellm_provider"], m["status"],
                  m["input_per_mtok"], m["output_per_mtok"], m["cached_input_per_mtok"],
                  m["context_window"], m["max_output_tokens"]) for m in model_rows])
            conn.executemany("INSERT INTO model_raw (model_id,model_spec) VALUES (?,?)",
                             [(m["id"], _dumps(m["model_spec"])) for m in model_rows])
            conn.executemany("INSERT OR IGNORE INTO model_modalities (model_id,modality,direction) VALUES (?,?,?)",
                             [(m["id"], mod, "input") for m in model_rows for mod in set(m["input_modalities"])]
                             + [(m["id"], mod, "output") for m in model_rows for mod in set(m["output_modalities"])])
            conn.executemany("INSERT OR IGNORE INTO model_endpoints (model_id,endpoint_id) VALUES (?,?)",
                             [(m["id"], eid) for m in model_rows for eid in m["endpoint_ids"] if eid in valid_ep])
            conn.executemany("INSERT OR IGNORE INTO model_capabilities (model_id,capability_key) VALUES (?,?)",
                             [(m["id"], c) for m in model_rows for c in m["capabilities"]])

            # ---- model extras (1:1 enrichment for every model + child tables) ----
            conn.executemany(
                "INSERT INTO model_enrichment (model_id,description,release_date,popularity,is_open_weights,"
                "license_id,open_source_score,min_vram_gb,ttft_ms,tokens_per_sec,availability_pct) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                [(m["id"], m["description"], m["release_date"], m["popularity"], int(bool(m["is_open_weights"])),
                  lic_id.get(m.get("license")), m["open_source_score"], m["min_vram_gb"],
                  m["ttft_ms"], m["tokens_per_sec"], m["availability_pct"]) for m in model_rows])
            conn.executemany("INSERT OR IGNORE INTO model_tags (model_id,tag) VALUES (?,?)",
                             [(m["id"], t) for m in model_rows for t in m["tags"]])
            conn.executemany("INSERT OR IGNORE INTO model_runtimes (model_id,runtime) VALUES (?,?)",
                             [(m["id"], rt) for m in model_rows for rt in m["runtimes"]])
            conn.executemany("INSERT INTO model_benchmarks (model_id,name,score,max,source) VALUES (?,?,?,?,?)",
                             [(m["id"], b["name"], b["score"], b["max"], b.get("source"))
                              for m in model_rows for b in m["benchmarks"]])

            # ---- price history (write on change) + 30-day prune ----
            hist = []
            for m in model_rows:
                cur = (m["input_per_mtok"], m["output_per_mtok"], m["cached_input_per_mtok"])
                if last_price.get(m["id"]) != cur:
                    hist.append((m["id"], cur[0], cur[1], cur[2], now))
            conn.executemany(
                "INSERT INTO model_price_history (model_id,input_per_mtok,output_per_mtok,cached_input_per_mtok,recorded_at) "
                "VALUES (?,?,?,?,?)", hist)
            cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
            conn.execute("DELETE FROM model_price_history WHERE recorded_at < ?", (cutoff,))

            enriched = sum(1 for m in model_rows if m["enriched"])
            for k, v in {"generated_at": now, "litellm_ref": settings.LITELLM_REF,
                         "providers": str(len(provider_rows)), "models": str(len(model_rows)),
                         "enriched_models": str(enriched), "price_changes": str(len(hist))}.items():
                conn.execute("INSERT INTO meta (key,value) VALUES (?,?)", (k, v))

        conn.execute("ANALYZE")
        result = {"providers": len(provider_rows), "models": len(model_rows),
                  "enriched_models": enriched, "price_changes": len(hist)}
        log.info("──── Catalog refreshed: %s ────", result)
        return result
    finally:
        conn.close()
