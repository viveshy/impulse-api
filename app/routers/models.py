"""Model routes. All paths address models by GUID - never by slug or name."""
from fastapi import APIRouter, Depends, Query

from app.db import get_db
from app.handlers import models as handler
from app.utils.pagination import Page, envelope, page_params

router = APIRouter(prefix="/v1/models", tags=["models"])


@router.get("")
def list_models(
    page: Page = Depends(page_params),
    q: str | None = Query(None, description="name search"),
    mode: str | None = Query(None, description="e.g. chat, embedding, image_generation"),
    open_weights: bool | None = Query(None, description="only open-weight models"),
    capability: str | None = Query(None, description="capability key, e.g. vision, reasoning"),
    provider: str | None = Query(None, description="provider GUID"),
    max_price: float | None = Query(None, ge=0, description="max blended $/Mtok"),
    sort: str = Query("popular", pattern="^(popular|price|context|release|name)$"),
    conn=Depends(get_db),
):
    items, total = handler.list_models(
        conn, q=q, mode=mode, open_weights=open_weights, capability=capability,
        provider_guid=provider, max_price=max_price, sort=sort,
        limit=page.limit, offset=page.offset)
    return envelope(items, total, page)


@router.get("/{guid}")
def get_model(guid: str, conn=Depends(get_db)):
    return handler.get_model(conn, guid)


@router.get("/{guid}/alternatives")
def get_alternatives(guid: str, conn=Depends(get_db)):
    """Open-weight alternatives first (with tags), then cheaper alternatives of any license."""
    return handler.get_alternatives(conn, guid)


@router.get("/{guid}/price-history")
def get_price_history(guid: str, conn=Depends(get_db)):
    return handler.get_price_history(conn, guid)
