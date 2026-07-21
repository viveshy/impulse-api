"""Internal bulk endpoint. The frontend loads the whole catalog in one request; public
clients still use the paginated /v1/models and /v1/providers (this 404s for them)."""
from fastapi import APIRouter, Depends, HTTPException, Request

from app.dao import meta as meta_dao
from app.db import get_db
from app.handlers import catalog as handler
from app.utils.ratelimit import client_ip, is_internal

router = APIRouter(tags=["catalog"])


@router.get("/v1/catalog")
def catalog(request: Request, conn=Depends(get_db)):
    if not is_internal(client_ip(request)):
        raise HTTPException(status_code=404, detail="not_found")
    return {**handler.full_catalog(conn), "meta": meta_dao.all_meta(conn)}
