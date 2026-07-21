"""Bulk catalog assembly for the trusted frontend (one response, one query pass)."""
from app.dao import models as mdao
from app.dao import providers as pdao
from app.handlers import models as mh
from app.handlers import providers as ph


def full_catalog(conn) -> dict:
    """Every model + provider in a single payload. Lets the frontend load the whole
    catalog in one request instead of paging it, so cold loads stay well under 500ms."""
    eps = pdao.endpoints_by_guid(conn)
    providers = []
    for r in pdao.all_providers(conn):
        dto = ph._summary(r)
        dto["endpoints"] = eps.get(r["guid"], [])
        providers.append(dto)
    models = [mh._summary(r) for r in mdao.all_summaries(conn)]
    return {"models": models, "providers": providers}
