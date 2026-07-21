"""Provider data access. GUID is the public identity."""
import sqlite3

Row = sqlite3.Row

_SUMMARY = """
SELECT p.guid, p.name, p.website, p.api_base, p.category,
       pe.description, pe.auth_type, pe.monogram, pe.founded_year,
       (SELECT COUNT(*) FROM models m WHERE m.provider_id = p.id AND m.is_active = 1) AS model_count
FROM providers p
LEFT JOIN provider_enrichment pe ON pe.provider_id = p.id
WHERE p.is_active = 1
"""


def list_providers(conn, *, category=None, q=None, limit=30, offset=0) -> tuple[list[Row], int]:
    where, args = [], []
    if category:
        where.append("p.category = ?")
        args.append(category)
    if q:
        where.append("p.name LIKE ?")
        args.append(f"%{q}%")
    clause = (" AND " + " AND ".join(where)) if where else ""
    total = conn.execute(
        f"SELECT COUNT(*) FROM providers p WHERE p.is_active = 1{clause}", args).fetchone()[0]
    rows = conn.execute(
        f"{_SUMMARY}{clause} ORDER BY model_count DESC, p.name LIMIT ? OFFSET ?",
        [*args, limit, offset]).fetchall()
    return rows, total


def get_by_guid(conn, guid: str) -> Row | None:
    return conn.execute(f"{_SUMMARY} AND p.guid = ?", [guid]).fetchone()


def all_providers(conn) -> list[Row]:
    """Every active provider in one pass (for the internal bulk /v1/catalog endpoint)."""
    return conn.execute(f"{_SUMMARY} ORDER BY p.name").fetchall()


def internal_id(conn, guid: str) -> str | None:
    r = conn.execute("SELECT id FROM providers WHERE guid = ?", [guid]).fetchone()
    return r["id"] if r else None


def regions(conn, pid): return [r["region"] for r in conn.execute(
    "SELECT region FROM provider_regions WHERE provider_id = ? ORDER BY region", [pid])]

def endpoints(conn, pid): return [dict(r) for r in conn.execute(
    "SELECT name, method, path, description, streaming, auth FROM provider_endpoints "
    "WHERE provider_id = ? ORDER BY path", [pid])]

def endpoints_by_guid(conn) -> dict[str, list[dict]]:
    """All provider endpoints keyed by provider GUID (one query, for the list view)."""
    out: dict[str, list[dict]] = {}
    for r in conn.execute(
        "SELECT p.guid AS g, ep.name, ep.method, ep.path, ep.description, ep.streaming, ep.auth "
        "FROM provider_endpoints ep JOIN providers p ON p.id = ep.provider_id ORDER BY ep.path"):
        out.setdefault(r["g"], []).append(
            {k: r[k] for k in ("name", "method", "path", "description", "streaming", "auth")})
    return out

def sdks(conn, pid): return [dict(r) for r in conn.execute(
    # aliased to camelCase so SDK objects match the rest of the API's DTO style
    "SELECT language, package_name AS packageName, install_command AS installCommand, "
    "docs_url AS docsUrl FROM provider_sdks WHERE provider_id = ? ORDER BY language", [pid])]
