"""Health + catalog metadata."""
from fastapi import APIRouter, Depends

from app.dao import meta as dao
from app.db import get_db

router = APIRouter(tags=["meta"])


@router.get("/health")
def health():
    return {"status": "ok"}


@router.get("/v1/meta")
def meta(conn=Depends(get_db)):
    """Catalog freshness + counts (from the sync's meta table)."""
    return {"catalog": dao.all_meta(conn), "counts": dao.counts(conn)}
