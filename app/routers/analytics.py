"""Visitor analytics for the trusted frontend: it forwards page views and reads the summary.
Frontend-only, like /v1/catalog (404 for public clients)."""
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from app import analytics
from app.utils.ratelimit import internal_only

router = APIRouter(prefix="/v1/analytics", tags=["analytics"],
                   dependencies=[Depends(internal_only)])


class Hit(BaseModel):
    path: str = Field(max_length=2048)
    ip: str = Field(max_length=2048)
    ua: str = Field(max_length=2048)
    ref: str | None = Field(default=None, max_length=2048)


@router.post("/hit")
def hit(body: Hit):
    """`counted` is false for bots, non-page paths and storage errors - never an error."""
    return {"counted": analytics.record_hit(body.path, body.ip, body.ua, body.ref)}


@router.get("/summary")
def summary(days: int = Query(30, ge=1, le=365, description="window in days, today included")):
    return analytics.summary(days)
