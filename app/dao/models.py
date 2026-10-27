"""Model data access. Public identity is the GUID; the internal slug id never leaves here."""
import sqlite3

Row = sqlite3.Row

# One canonical projection: base facts + 1:1 enrichment + license + the verbatim LiteLLM
# spec, with a blended price. `m.id`/`p.id` (internal slugs) are selected only to derive
# the listing's route, never serialized.
_SUMMARY = """
SELECT m.guid, m.name, m.family, m.mode, m.status, m.litellm_provider,
       m.id AS internal_id, p.id AS provider_slug, rw.model_spec,
       p.guid AS provider_guid, p.name AS provider_name,
       m.input_per_mtok, m.output_per_mtok, m.cached_input_per_mtok,
       m.context_window, m.max_output_tokens,
       e.description, e.release_date, e.popularity, e.is_open_weights,
       e.open_source_score, e.min_vram_gb, e.ttft_ms, e.tokens_per_sec, e.availability_pct,
       l.name AS license, l.is_open AS license_is_open,
       (SELECT GROUP_CONCAT(capability_key) FROM model_capabilities WHERE model_id = m.id) AS cap_keys,
       (SELECT GROUP_CONCAT(modality) FROM model_modalities WHERE model_id = m.id AND direction = 'input') AS in_mods,
       (SELECT GROUP_CONCAT(modality) FROM model_modalities WHERE model_id = m.id AND direction = 'output') AS out_mods,
       (SELECT GROUP_CONCAT(tag) FROM model_tags WHERE model_id = m.id) AS tag_names,
       (SELECT GROUP_CONCAT(runtime) FROM model_runtimes WHERE model_id = m.id) AS runtime_names,
       (COALESCE(m.input_per_mtok,0) + COALESCE(m.output_per_mtok,0)) AS blended
FROM models m
JOIN providers p ON p.id = m.provider_id
LEFT JOIN model_enrichment e ON e.model_id = m.id
LEFT JOIN licenses l ON l.id = e.license_id
LEFT JOIN model_raw rw ON rw.model_id = m.id
WHERE m.is_active = 1
"""

_SORTS = {
    "popular": "e.popularity DESC NULLS LAST, m.name",
    "price": "blended ASC, m.name",
    "context": "m.context_window DESC, m.name",
    "release": "e.release_date DESC NULLS LAST, m.name",
    "name": "m.name",
}


def list_models(conn, *, q=None, mode=None, open_weights=None, capability=None,
                provider_guid=None, max_price=None, sort="popular",
                limit=30, offset=0) -> tuple[list[Row], int]:
    where, args = [], []
    if q:
        where.append("m.name LIKE ?")
        args.append(f"%{q}%")
    if mode:
        where.append("m.mode = ?")
        args.append(mode)
    if open_weights is not None:
        where.append("COALESCE(e.is_open_weights,0) = ?")
        args.append(1 if open_weights else 0)
    if provider_guid:
        where.append("p.guid = ?")
        args.append(provider_guid)
    if max_price is not None:
        where.append("(COALESCE(m.input_per_mtok,0) + COALESCE(m.output_per_mtok,0)) <= ?")
        args.append(max_price)
    if capability:
        where.append("EXISTS (SELECT 1 FROM model_capabilities mc "
                     "WHERE mc.model_id = m.id AND mc.capability_key = ?)")
        args.append(capability)

    clause = (" AND " + " AND ".join(where)) if where else ""
    order = _SORTS.get(sort, _SORTS["popular"])

    total = conn.execute(
        "SELECT COUNT(*) FROM models m JOIN providers p ON p.id = m.provider_id "
        "LEFT JOIN model_enrichment e ON e.model_id = m.id "
        f"WHERE m.is_active = 1{clause}", args).fetchone()[0]
    rows = conn.execute(
        f"{_SUMMARY}{clause} ORDER BY {order} LIMIT ? OFFSET ?",
        [*args, limit, offset]).fetchall()
    return rows, total


def get_by_guid(conn, guid: str) -> Row | None:
    return conn.execute(f"{_SUMMARY} AND m.guid = ?", [guid]).fetchone()


def all_summaries(conn) -> list[Row]:
    """Every active model in one pass (for the internal bulk /v1/catalog endpoint)."""
    return conn.execute(f"{_SUMMARY} ORDER BY m.name").fetchall()


def internal_id(conn, guid: str) -> str | None:
    r = conn.execute("SELECT id FROM models WHERE guid = ?", [guid]).fetchone()
    return r["id"] if r else None


# ---- child collections (by internal id, resolved from a guid at the handler edge) ----
def capabilities(conn, mid): return [r["capability_key"] for r in conn.execute(
    "SELECT capability_key FROM model_capabilities WHERE model_id = ? ORDER BY capability_key", [mid])]

def tags(conn, mid): return [r["tag"] for r in conn.execute(
    "SELECT tag FROM model_tags WHERE model_id = ? ORDER BY tag", [mid])]

def runtimes(conn, mid): return [r["runtime"] for r in conn.execute(
    "SELECT runtime FROM model_runtimes WHERE model_id = ? ORDER BY runtime", [mid])]

def modalities(conn, mid): return [dict(r) for r in conn.execute(
    "SELECT modality, direction FROM model_modalities WHERE model_id = ?", [mid])]

def benchmarks(conn, mid): return [dict(r) for r in conn.execute(
    "SELECT name, score, max, source FROM model_benchmarks WHERE model_id = ? ORDER BY name", [mid])]

def endpoints(conn, mid): return [dict(r) for r in conn.execute(
    "SELECT ep.name, ep.method, ep.path FROM model_endpoints me "
    "JOIN provider_endpoints ep ON ep.id = me.endpoint_id WHERE me.model_id = ? ORDER BY ep.path", [mid])]

def price_history(conn, mid): return [dict(r) for r in conn.execute(
    "SELECT input_per_mtok, output_per_mtok, cached_input_per_mtok, recorded_at "
    "FROM model_price_history WHERE model_id = ? ORDER BY recorded_at", [mid])]


def price_changes(conn, *, since: str, limit: int = 200) -> list[Row]:
    """List-price moves recorded at or after `since`, newest first: a history row whose
    previous row for the same model, however old, has a different input or output price. A
    model's first row is just its first sighting, and cached-only moves don't count. The log
    outlives models that leave the catalog, so only active models are joined in."""
    return conn.execute("""
        WITH h AS (
          SELECT model_id, input_per_mtok, output_per_mtok, recorded_at,
                 LAG(input_per_mtok)  OVER w AS prev_input,
                 LAG(output_per_mtok) OVER w AS prev_output,
                 LAG(recorded_at)     OVER w AS prev_at
          FROM model_price_history
          WINDOW w AS (PARTITION BY model_id ORDER BY recorded_at)
        )
        SELECT m.guid, m.name, m.id AS internal_id, m.litellm_provider,
               p.guid AS provider_guid, p.name AS provider_name, p.id AS provider_slug,
               h.prev_input, h.prev_output, h.input_per_mtok, h.output_per_mtok, h.recorded_at
        FROM h
        JOIN models m ON m.id = h.model_id AND m.is_active = 1
        JOIN providers p ON p.id = m.provider_id
        WHERE h.recorded_at >= ? AND h.prev_at IS NOT NULL
          AND (h.input_per_mtok IS NOT h.prev_input OR h.output_per_mtok IS NOT h.prev_output)
        ORDER BY h.recorded_at DESC, m.name
        LIMIT ?""", [since, limit]).fetchall()


def alternatives(conn, target: Row, *, limit=8) -> tuple[list[Row], list[Row]]:
    """Two tiers, ranked: (1) open-weight alternatives, (2) cheaper alternatives (any license)."""
    guid, mode = target["guid"], target["mode"]
    tcaps = [r["capability_key"] for r in conn.execute(
        "SELECT mc.capability_key FROM model_capabilities mc JOIN models m ON m.id = mc.model_id "
        "WHERE m.guid = ?", [guid])]
    tmods = [r["modality"] for r in conn.execute(
        "SELECT mm.modality FROM model_modalities mm JOIN models m ON m.id = mm.model_id "
        "WHERE m.guid = ? AND mm.direction = 'output'", [guid])]
    tblended = (target["input_per_mtok"] or 0) + (target["output_per_mtok"] or 0)

    capph = ",".join("?" * len(tcaps)) if tcaps else "NULL"
    shared = (f"(SELECT COUNT(*) FROM model_capabilities mc "
              f"WHERE mc.model_id = m.id AND mc.capability_key IN ({capph})) AS shared_caps")
    base = _SUMMARY.replace(") AS blended", ") AS blended, " + shared)

    # An alternative must be the same *kind* of model - same mode AND overlapping output
    # modality (guards against upstream mode mislabels leaking embeddings/image models in).
    kind, kind_args = "AND m.mode = ? AND m.guid != ?", [mode, guid]
    if tmods:
        modph = ",".join("?" * len(tmods))
        kind += (f" AND EXISTS (SELECT 1 FROM model_modalities mm WHERE mm.model_id = m.id "
                 f"AND mm.direction = 'output' AND mm.modality IN ({modph}))")
        kind_args += tmods

    # Tier 1 - open-weight: most capability overlap, then most popular, then cheapest.
    open_rows = conn.execute(
        f"{base} {kind} AND COALESCE(e.is_open_weights,0) = 1 "
        "ORDER BY shared_caps DESC, e.popularity DESC NULLS LAST, blended ASC LIMIT ?",
        [*tcaps, *kind_args, limit]).fetchall()

    # Tier 2 - genuinely cheaper than the target (any license), excluding tier-1 picks.
    # Require a real listed price (> 0): a $0 entry means "price unlisted", not "free".
    open_guids = [r["guid"] for r in open_rows]
    excl = ",".join("?" * len(open_guids)) if open_guids else "NULL"
    cheaper_rows = conn.execute(
        f"{base} {kind} "
        "AND (COALESCE(m.input_per_mtok,0) + COALESCE(m.output_per_mtok,0)) > 0 "
        "AND (COALESCE(m.input_per_mtok,0) + COALESCE(m.output_per_mtok,0)) < ? "
        f"AND m.guid NOT IN ({excl}) "
        "ORDER BY blended ASC, shared_caps DESC LIMIT ?",
        [*tcaps, *kind_args, tblended, *open_guids, limit]).fetchall()

    return open_rows, cheaper_rows
