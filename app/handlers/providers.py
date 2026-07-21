"""Provider business logic: GUID-addressed DTOs."""
from fastapi import HTTPException

from app.dao import providers as dao


def _summary(row) -> dict:
    return {
        "guid": row["guid"],
        "name": row["name"],
        "website": row["website"],
        "apiBase": row["api_base"] or None,
        "category": row["category"],
        "description": row["description"],
        "monogram": row["monogram"],
        "authType": row["auth_type"],
        "foundedYear": row["founded_year"],
        "modelCount": row["model_count"],
    }


def list_providers(conn, **filters) -> tuple[list[dict], int]:
    rows, total = dao.list_providers(conn, **filters)
    eps = dao.endpoints_by_guid(conn)
    items = []
    for r in rows:
        dto = _summary(r)
        dto["endpoints"] = eps.get(r["guid"], [])
        items.append(dto)
    return items, total


def get_provider(conn, guid: str) -> dict:
    row = dao.get_by_guid(conn, guid)
    if row is None:
        raise HTTPException(404, detail=f"No provider with guid {guid}")
    pid = dao.internal_id(conn, guid)
    dto = _summary(row)
    dto["regions"] = dao.regions(conn, pid)
    dto["endpoints"] = dao.endpoints(conn, pid)
    dto["sdks"] = dao.sdks(conn, pid)
    return dto
