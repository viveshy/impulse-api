"""GET /v1/price-changes: list-price moves on active models, for internal clients only."""
from datetime import datetime


def _changes(client, days=30) -> dict:
    r = client.get(f"/v1/price-changes?days={days}")
    assert r.status_code == 200
    return r.json()


def test_price_changes_lists_real_change(client, guids):
    body = _changes(client)
    assert body["days"] == 30
    mine = [c for c in body["changes"] if c["guid"] == guids["gpt"]]
    assert len(mine) == 1
    c = mine[0]
    assert c["from"]["inputPerMtok"] == 2.0 and c["to"]["inputPerMtok"] == 1.5
    assert c["from"]["outputPerMtok"] == 10.0 and c["to"]["outputPerMtok"] == 10.0
    assert set(c) == {"guid", "name", "provider", "route", "from", "to", "at"}
    assert c["name"] == "gpt-6-sol" and c["route"] is None
    assert c["provider"] == client.get(f"/v1/models/{guids['gpt']}").json()["provider"]
    assert datetime.fromisoformat(c["at"]).tzinfo is not None


def test_price_changes_ignores_unchanged_rows(client, guids):
    # opus: only the cached price moved; bedrock: a single (first-sighting) row;
    # retired-model: history of a model that left the catalog
    assert [c["guid"] for c in _changes(client)["changes"]] == [guids["gpt"], guids["gpt_azure_eu"]]  # newest first


def test_price_changes_compare_with_the_price_before_the_window(client, guids):
    # azure moved 20 days ago from a price first seen 45 days ago: still a move inside 30 days
    azure = _changes(client)["changes"][1]
    assert azure["route"] == "eu"
    assert azure["from"] == {"inputPerMtok": 3.0, "outputPerMtok": 12.0}
    assert azure["to"] == {"inputPerMtok": 2.4, "outputPerMtok": 12.0}
    assert [c["guid"] for c in _changes(client, days=15)["changes"]] == [guids["gpt"]]


def test_price_changes_hidden_from_public(client):
    public = {"X-Forwarded-For": "8.8.8.8"}
    assert client.get("/v1/price-changes", headers=public).status_code == 404
    # hidden before validation, so a bad query doesn't reveal the route either
    assert client.get("/v1/price-changes?days=500", headers=public).status_code == 404


def test_price_changes_days_bounds(client):
    # the sync keeps 30 days of history, so a longer window would quietly return less
    assert client.get("/v1/price-changes?days=0").status_code == 422
    assert client.get("/v1/price-changes?days=31").status_code == 422
    assert _changes(client, days=1)["changes"] == []
    assert _changes(client, days=30)["days"] == 30
