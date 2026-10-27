"""Visitor counter in its own SQLite file (the catalog stays read-only).

No cookies and no stored IPs: a visitor is the first 16 hex chars of
sha256(daily salt + ip + user agent), and only today's salt is kept, so ids can't be linked
across days. Every call fails soft - analytics must never break a page view.
"""
import hashlib
import logging
import re
import secrets
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from urllib.parse import urlsplit

from app.settings import settings

log = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS hits (
  id       INTEGER PRIMARY KEY,
  day      TEXT NOT NULL,               -- UTC date, YYYY-MM-DD
  ts       TEXT NOT NULL,               -- UTC ISO timestamp
  path     TEXT NOT NULL,
  visitor  TEXT NOT NULL,               -- sha256(salt + ip + ua)[:16]
  ref_host TEXT
);
CREATE INDEX IF NOT EXISTS idx_hits_day ON hits(day);
CREATE INDEX IF NOT EXISTS idx_hits_day_visitor ON hits(day, visitor);
CREATE TABLE IF NOT EXISTS salts (day TEXT PRIMARY KEY, salt TEXT NOT NULL);
"""

_KEEP_DAYS = 400
_PATH_MAX = 200
_TOP = 10
_SKIP_PATHS = ("/api/", "/_next/")
_LOCAL_HOSTS = {"localhost", "127.0.0.1"}
_QUERY_OR_FRAGMENT = re.compile(r"[?#]")

# Crawlers, link unfurlers, monitors, HTTP clients and automated/headless browsers (the
# owner's own screenshot runs included) are not visitors.
_BOT_UA = re.compile(
    r"bot|crawl|spider|slurp|scrap|fetch|preview|archive|httrack|validator|"
    r"monitor|uptime|pingdom|synthetics|lighthouse|page ?speed|gtmetrix|"
    r"headless|phantomjs|selenium|puppeteer|playwright|webdriver|"
    r"curl|wget|httpie|python|aiohttp|httpx|axios|undici|okhttp|go-http|java/|libwww|ruby|"
    r"php|postman|facebookexternalhit|meta-external|embedly|iframely|whatsapp|"
    r"google(?:other|-)|apis-google|mediapartners|gpt|claude|anthropic|perplexity|cohere-ai|"
    r"feed|rss",
    re.I)


@contextmanager
def _db() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(settings.ANALYTICS_DB, timeout=5)
    try:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")  # WAL-safe; a lost last hit is fine
        conn.executescript(_SCHEMA)
        yield conn
    finally:
        conn.close()


def _utc(now: datetime | None) -> datetime:
    if now is None:
        return datetime.now(timezone.utc)
    return now.astimezone(timezone.utc) if now.tzinfo else now.replace(tzinfo=timezone.utc)


def _ref_host(ref: str | None) -> str | None:
    try:
        host = urlsplit(ref).hostname if ref else None
    except ValueError:  # e.g. a malformed IPv6 literal
        return None
    if not host or host in _LOCAL_HOSTS or host == settings.SITE_HOST.lower():
        return None
    return host


def _salt(conn: sqlite3.Connection, today: date) -> str:
    day = today.isoformat()
    row = conn.execute("SELECT salt FROM salts WHERE day = ?", (day,)).fetchone()
    if row:
        return row[0]
    # First hit of a new day: rotate the salt and prune. Dropping yesterday's salt is what
    # makes yesterday's visitor ids unlinkable to today's.
    with conn:
        conn.execute("INSERT OR IGNORE INTO salts (day, salt) VALUES (?, ?)",
                     (day, secrets.token_hex(16)))
        conn.execute("DELETE FROM salts WHERE day < ?", (day,))
        conn.execute("DELETE FROM hits WHERE day < ?",
                     ((today - timedelta(days=_KEEP_DAYS)).isoformat(),))
    # re-read: a concurrent first hit may have stored its salt first
    return conn.execute("SELECT salt FROM salts WHERE day = ?", (day,)).fetchone()[0]


def record_hit(path: str, ip: str, ua: str, ref: str | None, now: datetime | None = None) -> bool:
    """Store one page view. False (nothing stored) for bots, non-page paths and DB errors."""
    if not ua or not ua.strip() or _BOT_UA.search(ua):
        return False
    path = _QUERY_OR_FRAGMENT.split(path or "", maxsplit=1)[0][:_PATH_MAX]
    if not path.startswith("/") or path.startswith(_SKIP_PATHS):
        return False
    now = _utc(now)
    try:
        with _db() as conn:
            salt = _salt(conn, now.date())
            visitor = hashlib.sha256(f"{salt}{ip}{ua}".encode()).hexdigest()[:16]
            with conn:
                conn.execute(
                    "INSERT INTO hits (day, ts, path, visitor, ref_host) VALUES (?, ?, ?, ?, ?)",
                    (now.date().isoformat(), now.isoformat(timespec="seconds"), path, visitor,
                     _ref_host(ref)))
    except (sqlite3.Error, UnicodeError) as e:
        log.warning("analytics hit not recorded: %s", e)
        return False
    return True


def summary(days: int, now: datetime | None = None) -> dict:
    """Views and visitors over the last `days` UTC days, today included. Visitors are per-day
    distinct ids summed - by design an id can't be followed across days."""
    now = _utc(now)
    span = [(now.date() - timedelta(days=i)).isoformat() for i in range(days - 1, -1, -1)]
    out = {
        "days": days,
        "generatedAt": now.isoformat(timespec="seconds"),
        "totals": {"views": 0, "visitors": 0},
        "today": {"views": 0, "visitors": 0},
        "allTime": {"views": 0, "since": None},
        "daily": [{"day": d, "views": 0, "visitors": 0} for d in span],
        "topPages": [],
        "topReferrers": [],
    }
    if not span:
        return out
    window = (span[0], span[-1])
    try:
        with _db() as conn:
            per_day = {d: (views, visitors) for d, views, visitors in conn.execute(
                "SELECT day, COUNT(*), COUNT(DISTINCT visitor) FROM hits "
                "WHERE day BETWEEN ? AND ? GROUP BY day", window)}
            all_views, since = conn.execute("SELECT COUNT(*), MIN(day) FROM hits").fetchone()
            pages = conn.execute(
                "SELECT path, COUNT(*) AS n FROM hits WHERE day BETWEEN ? AND ? "
                "GROUP BY path ORDER BY n DESC, path LIMIT ?", (*window, _TOP)).fetchall()
            # By visitors (per day, like the totals), so reloading with a made-up referrer
            # doesn't climb the list.
            refs = conn.execute(
                "SELECT ref_host, COUNT(DISTINCT day || visitor) AS n FROM hits WHERE day BETWEEN ? AND ? "
                "AND ref_host IS NOT NULL GROUP BY ref_host ORDER BY n DESC, ref_host LIMIT ?",
                (*window, _TOP)).fetchall()
    except sqlite3.Error as e:
        log.warning("analytics summary unavailable: %s", e)
        return out

    daily = [{"day": d, "views": per_day.get(d, (0, 0))[0], "visitors": per_day.get(d, (0, 0))[1]}
             for d in span]
    out.update({
        "totals": {"views": sum(d["views"] for d in daily),
                   "visitors": sum(d["visitors"] for d in daily)},
        "today": {"views": daily[-1]["views"], "visitors": daily[-1]["visitors"]},
        "allTime": {"views": all_views, "since": since},
        "daily": daily,
        "topPages": [{"path": p, "views": n} for p, n in pages],
        "topReferrers": [{"host": h, "visitors": n} for h, n in refs],
    })
    return out
