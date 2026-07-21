"""Impulse API - read-only, paginated, rate-limited catalog over the sync's SQLite DB.

Structure: router → handler → dao → utils. Models and providers are addressed only by
their opaque GUID; internal slug ids never cross the API boundary.
"""
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.routers import catalog, meta, models, providers
from app.settings import settings
from app.utils.ratelimit import RateLimiter

app = FastAPI(
    title="Impulse API",
    version="0.1.0",
    description="The single reference for every AI model - open-weight first.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_methods=["GET"],
    allow_headers=["*"],
)

_limiter = RateLimiter()


@app.middleware("http")
async def rate_limit(request: Request, call_next):
    return await _limiter(request, call_next)


@app.exception_handler(HTTPException)
async def http_error(_: Request, exc: HTTPException):
    return JSONResponse(status_code=exc.status_code,
                        content={"error": "not_found" if exc.status_code == 404 else "error",
                                 "detail": exc.detail})


app.include_router(meta.router)
app.include_router(catalog.router)
app.include_router(models.router)
app.include_router(providers.router)
