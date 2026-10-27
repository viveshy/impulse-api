"""Impulse API - read-only, paginated, rate-limited catalog over the sync's SQLite DB.

Structure: router → handler → dao → utils. Models and providers are addressed only by
their opaque GUID; internal slug ids never cross the API boundary. The only writes go to
the separate visitor-analytics DB.
"""
import json

from fastapi import FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response

from app.routers import analytics, catalog, changes, meta, models, providers
from app.settings import settings
from app.utils.ratelimit import RateLimiter

app = FastAPI(
    title="Impulse API",
    version="0.1.0",
    description="The single reference for every AI model - frontier first.",
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


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    try:
        return await request_validation_exception_handler(request, exc)
    except UnicodeEncodeError:
        # The 422 echoes the rejected input, and a JSON body can carry lone surrogates that
        # UTF-8 can't encode - escape them rather than turn junk into a 500.
        return Response(json.dumps({"detail": jsonable_encoder(exc.errors())}),
                        status_code=422, media_type="application/json")


app.include_router(meta.router)
app.include_router(catalog.router)
app.include_router(changes.router)
app.include_router(models.router)
app.include_router(providers.router)
app.include_router(analytics.router)
