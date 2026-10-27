"""Internal price-change feed: recent list-price moves across the active catalog.
Frontend-only, like /v1/catalog (404 for public clients)."""
from fastapi import APIRouter, Depends, Query

from app.db import get_db
from app.handlers import models as handler
from app.utils.ratelimit import internal_only

router = APIRouter(tags=["changes"], dependencies=[Depends(internal_only)])


@router.get("/v1/price-changes")
def price_changes(days: int = Query(30, ge=1, le=30, description="look-back window in days; the sync keeps 30"),
                  conn=Depends(get_db)):
    """Newest first, at most 200."""
    return handler.price_changes(conn, days)
