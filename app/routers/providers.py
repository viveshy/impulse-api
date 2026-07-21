"""Provider routes - GUID-addressed."""
from fastapi import APIRouter, Depends, Query

from app.db import get_db
from app.handlers import providers as handler
from app.utils.pagination import Page, envelope, page_params

router = APIRouter(prefix="/v1/providers", tags=["providers"])


@router.get("")
def list_providers(
    page: Page = Depends(page_params),
    category: str | None = Query(None, description="frontier|open|cloud|inference"),
    q: str | None = Query(None, description="name search"),
    conn=Depends(get_db),
):
    items, total = handler.list_providers(
        conn, category=category, q=q, limit=page.limit, offset=page.offset)
    return envelope(items, total, page)


@router.get("/{guid}")
def get_provider(guid: str, conn=Depends(get_db)):
    return handler.get_provider(conn, guid)
