"""Visitor analytics: its own SQLite file, daily-rotating salted visitor ids, fails soft."""
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from app import analytics
from app.settings import settings

BROWSER = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
           "Chrome/141.0.0.0 Safari/537.36")
PUBLIC = {"X-Forwarded-For": "8.8.8.8"}
SUMMARY_KEYS = {"days", "generatedAt", "totals", "today", "allTime", "daily", "topPages",
                "topReferrers"}


@pytest.fixture(autouse=True)
def analytics_db(tmp_path, monkeypatch):
    """A fresh analytics file per test."""
    path = tmp_path / "analytics.db"
    monkeypatch.setattr(settings, "ANALYTICS_DB", str(path))
    return path


def _hit(client, path="/", ip="203.0.113.7", ua=BROWSER, ref=None, **kw):
    return client.post("/v1/analytics/hit", json={"path": path, "ip": ip, "ua": ua, "ref": ref}, **kw)


def _summary(client, days=30) -> dict:
    r = client.get(f"/v1/analytics/summary?days={days}")
    assert r.status_code == 200
    return r.json()


def test_hit_counts_once_per_visitor_per_day(client):
    for path in ("/", "/models", "/models"):
        assert _hit(client, path=path).json() == {"counted": True}
    s = _summary(client)
    assert s["totals"] == {"views": 3, "visitors": 1}
    assert s["today"] == {"views": 3, "visitors": 1}
    assert s["daily"][-1]["views"] == 3 and s["daily"][-1]["visitors"] == 1
    assert s["allTime"]["views"] == 3
    assert s["topPages"] == [{"path": "/models", "views": 2}, {"path": "/", "views": 1}]
    _hit(client, ip="198.51.100.9")  # someone else
    assert _summary(client)["today"] == {"views": 4, "visitors": 2}


def test_bot_ua_not_counted(client):
    for ua in ("Googlebot", "curl/8", "HeadlessChrome",
               "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
               "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
               "HeadlessChrome/141.0.0.0 Safari/537.36",
               "python-httpx/0.28.1", "facebookexternalhit/1.1", "", "   "):
        assert _hit(client, ua=ua).json() == {"counted": False}, ua
    assert _summary(client)["totals"]["views"] == 0


def test_daily_is_zero_filled(client):
    _hit(client)
    s = _summary(client, days=7)
    assert set(s) == SUMMARY_KEYS and s["days"] == 7
    assert len(s["daily"]) == 7
    days = [d["day"] for d in s["daily"]]
    assert days == sorted(days) and days[-1] == datetime.now(timezone.utc).date().isoformat()
    assert [d["views"] for d in s["daily"]] == [0, 0, 0, 0, 0, 0, 1]
    assert len(_summary(client, days=365)["daily"]) == 365


def test_referrer_excludes_own_host(client):
    for ref in ("https://impulse.viveshy.com/models", "http://localhost:3000/",
                "http://127.0.0.1:3100/x", "", None, "not a url",
                "https://news.ycombinator.com/item?id=1", "https://News.YCombinator.com/",
                "https://www.google.com/"):
        assert _hit(client, ref=ref).json() == {"counted": True}
    s = _summary(client)
    assert s["topReferrers"] == [{"host": "news.ycombinator.com", "visitors": 1},
                                 {"host": "www.google.com", "visitors": 1}]
    assert s["totals"]["views"] == 9


def test_referrers_rank_by_visitors_not_views(client):
    for _ in range(5):  # one visitor reloading with a made-up referrer
        _hit(client, ref="https://spam.example/")
    for ip in ("198.51.100.1", "198.51.100.2"):
        _hit(client, ip=ip, ref="https://news.ycombinator.com/")
    assert _summary(client)["topReferrers"] == [{"host": "news.ycombinator.com", "visitors": 2},
                                                {"host": "spam.example", "visitors": 1}]


def test_referrer_visitors_are_counted_per_day(analytics_db):
    day1 = datetime(2026, 10, 1, 12, tzinfo=timezone.utc)
    for now in (day1, day1, day1 + timedelta(days=1)):
        analytics.record_hit("/", "203.0.113.7", BROWSER, "https://news.ycombinator.com/", now=now)
    s = analytics.summary(7, now=day1 + timedelta(days=1))
    assert s["topReferrers"] == [{"host": "news.ycombinator.com", "visitors": 2}]


def test_query_string_stripped(client):
    _hit(client, path="/models?q=claude&sort=price")
    _hit(client, path="/models#pricing")
    _hit(client, path="/compare?m=anthropic/claude-opus-5-5")
    long = "/models/" + "x" * 1000
    _hit(client, path=long)
    pages = {p["path"]: p["views"] for p in _summary(client)["topPages"]}
    assert pages == {"/models": 2, "/compare": 1, long[:200]: 1}


def test_hit_public_client_404(client):
    assert _hit(client, headers=PUBLIC).status_code == 404
    assert client.get("/v1/analytics/summary", headers=PUBLIC).status_code == 404
    # hidden before validation: garbage from a public client is a plain 404 too
    assert client.post("/v1/analytics/hit", json={}, headers=PUBLIC).status_code == 404
    assert _summary(client)["totals"]["views"] == 0


def test_hit_rejects_long_payload_without_500(client):
    assert _hit(client, path="/" + "a" * 5000).status_code == 422
    assert _hit(client, ua="Mozilla/5.0 " + "a" * 5000).status_code == 422
    assert client.post("/v1/analytics/hit", json={"path": "/"}).status_code == 422
    assert client.post("/v1/analytics/hit", json={"path": 1, "ip": [], "ua": {}}).status_code == 422
    # lone surrogates survive JSON decoding but not UTF-8
    raw = b'{"path": "/\\ud800", "ip": "1.2.3.4", "ua": "Mozilla/5.0", "ref": null}'
    r = client.post("/v1/analytics/hit", content=raw, headers={"content-type": "application/json"})
    assert r.status_code == 422 and r.json()["detail"][0]["loc"] == ["body", "path"]
    # junk that validates is simply not counted
    for path in ("models", "", "?q=1", "/api/v", "/_next/static/chunks/x.js", "javascript:alert(1)"):
        assert _hit(client, path=path).json() == {"counted": False}, path
    # a malformed referrer is dropped, the view still counts
    assert _hit(client, ref="http://[bad").json() == {"counted": True}
    s = _summary(client)
    assert s["totals"]["views"] == 1 and s["topReferrers"] == []


def test_old_salts_deleted_on_new_day(analytics_db):
    day1 = datetime(2026, 10, 1, 23, 59, tzinfo=timezone.utc)
    day2 = datetime(2026, 10, 2, 0, 1, tzinfo=timezone.utc)
    assert analytics.record_hit("/", "203.0.113.7", BROWSER, None, now=day1)
    assert analytics.record_hit("/", "203.0.113.7", BROWSER, None, now=day2)
    conn = sqlite3.connect(analytics_db)
    salts = conn.execute("SELECT day FROM salts").fetchall()
    visitors = [v for (v,) in conn.execute("SELECT visitor FROM hits ORDER BY ts")]
    conn.close()
    assert salts == [("2026-10-02",)]
    # same person, new day, new id: visits can't be linked across days
    assert len(visitors) == 2 and visitors[0] != visitors[1] and len(visitors[0]) == 16


def test_visitors_are_summed_per_day(analytics_db):
    day1 = datetime(2026, 10, 1, 12, tzinfo=timezone.utc)
    for now in (day1, day1, day1 + timedelta(days=1)):
        analytics.record_hit("/", "203.0.113.7", BROWSER, None, now=now)
    s = analytics.summary(7, now=day1 + timedelta(days=1))
    assert s["totals"] == {"views": 3, "visitors": 2}
    assert s["today"] == {"views": 1, "visitors": 1}
    assert s["allTime"] == {"views": 3, "since": "2026-10-01"}
    assert s["daily"][-2:] == [{"day": "2026-10-01", "views": 2, "visitors": 1},
                               {"day": "2026-10-02", "views": 1, "visitors": 1}]


def test_hits_older_than_400_days_are_pruned(analytics_db):
    start = datetime(2025, 1, 1, 12, tzinfo=timezone.utc)
    analytics.record_hit("/old", "203.0.113.7", BROWSER, None, now=start)
    analytics.record_hit("/new", "203.0.113.7", BROWSER, None, now=start + timedelta(days=401))
    s = analytics.summary(30, now=start + timedelta(days=401))
    assert s["allTime"] == {"views": 1, "since": "2026-02-06"}


def test_top_lists_are_capped(client):
    for i in range(12):
        for n in range(i + 1):  # i + 1 different visitors
            _hit(client, path=f"/p{i}", ip=f"198.51.100.{n}", ref=f"https://site{i}.example/")
    s = _summary(client)
    assert len(s["topPages"]) == 10 and s["topPages"][0] == {"path": "/p11", "views": 12}
    assert len(s["topReferrers"]) == 10 and s["topReferrers"][-1] == {"host": "site2.example", "visitors": 3}


def test_summary_days_bounds(client):
    assert client.get("/v1/analytics/summary?days=0").status_code == 422
    assert client.get("/v1/analytics/summary?days=366").status_code == 422


def test_db_error_fails_soft(client, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "ANALYTICS_DB", str(tmp_path))  # a directory: can't be opened
    assert _hit(client).json() == {"counted": False}
    s = _summary(client, days=5)
    assert set(s) == SUMMARY_KEYS and len(s["daily"]) == 5
    assert s["totals"] == {"views": 0, "visitors": 0} and s["today"] == {"views": 0, "visitors": 0}
    assert s["allTime"] == {"views": 0, "since": None}
    assert s["topPages"] == [] and s["topReferrers"] == []


def test_analytics_db_is_separate_and_wal(client, analytics_db):
    _hit(client)
    conn = sqlite3.connect(analytics_db)
    assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    conn.close()
    assert tables == {"hits", "salts"}
    assert str(analytics_db) != settings.DB_PATH
