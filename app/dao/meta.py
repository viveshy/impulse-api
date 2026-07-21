"""Catalog metadata (freshness, counts) from the sync's `meta` table."""


def all_meta(conn) -> dict:
    return {k: v for k, v in conn.execute("SELECT key, value FROM meta")}


def counts(conn) -> dict:
    return {
        "providers": conn.execute("SELECT COUNT(*) FROM providers WHERE is_active = 1").fetchone()[0],
        "models": conn.execute("SELECT COUNT(*) FROM models WHERE is_active = 1").fetchone()[0],
        "open_weight_models": conn.execute(
            "SELECT COUNT(*) FROM model_enrichment WHERE is_open_weights = 1").fetchone()[0],
    }
