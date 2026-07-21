"""In-memory fixed-window rate limit per client IP - the anti-scraping guard.

Deliberately simple (no Redis): the catalog is curated and read-mostly, and this plus
mandatory pagination means nobody one-click grabs the whole dataset. For multi-instance
deploys, swap the store for a shared one behind the same interface.
"""
import ipaddress
import time
from collections import defaultdict

from fastapi import Request
from fastapi.responses import JSONResponse

from app.settings import settings


def client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for", "")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "anon"


def is_internal(ip: str) -> bool:
    """Loopback / private-network clients are the trusted frontend, not public scrapers."""
    try:
        addr = ipaddress.ip_address(ip)
        return addr.is_loopback or addr.is_private
    except ValueError:
        return False


class RateLimiter:
    def __init__(self) -> None:
        self._hits: dict[str, list[float]] = defaultdict(list)

    async def __call__(self, request: Request, call_next):
        ip = client_ip(request)

        # The frontend calls this API server-to-server from the same host / private
        # network. Rate limiting is anti-scraping for public clients only; never throttle
        # the frontend, or its full-catalog paging trips the limit and search breaks.
        if is_internal(ip):
            return await call_next(request)

        now = time.time()
        window = settings.RATE_WINDOW
        recent = [t for t in self._hits[ip] if t > now - window]

        if len(recent) >= settings.RATE_LIMIT:
            return JSONResponse(
                status_code=429,
                content={"error": "rate_limited",
                         "detail": f"Max {settings.RATE_LIMIT} requests per {window}s."},
                headers={"Retry-After": str(window)},
            )

        recent.append(now)
        self._hits[ip] = recent
        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(settings.RATE_LIMIT)
        response.headers["X-RateLimit-Remaining"] = str(max(0, settings.RATE_LIMIT - len(recent)))
        return response
