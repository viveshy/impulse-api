"""Every list endpoint is page-by-page - there is no bulk-dump route, by design."""
from dataclasses import dataclass

from fastapi import Query

from app.settings import settings

# Far past any real catalog, and keeps (page - 1) * limit inside SQLite's 64-bit OFFSET.
PAGE_LAST = 1_000_000


@dataclass
class Page:
    page: int
    limit: int

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.limit


def page_params(
    page: int = Query(1, ge=1, le=PAGE_LAST, description="1-based page number"),
    limit: int = Query(settings.PAGE_DEFAULT, ge=1, le=settings.PAGE_MAX,
                       description=f"items per page (max {settings.PAGE_MAX})"),
) -> Page:
    return Page(page=page, limit=limit)


def envelope(items: list, total: int, page: Page) -> dict:
    return {
        "data": items,
        "pagination": {
            "page": page.page,
            "limit": page.limit,
            "total": total,
            "pages": (total + page.limit - 1) // page.limit if page.limit else 0,
        },
    }
