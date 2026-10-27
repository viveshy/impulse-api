"""Who the client is: the socket peer, or, behind a local proxy, the address the proxy names
last in X-Forwarded-For (nginx appends the one it saw after whatever the client sent)."""
from fastapi.testclient import TestClient

from app.main import app
from app.settings import settings


def _peer(host: str) -> TestClient:
    return TestClient(app, client=(host, 50000))


def test_behind_a_local_proxy_the_last_forwarded_address_is_the_client(client):
    assert client.get("/v1/price-changes", headers={"X-Forwarded-For": "127.0.0.1, 8.8.8.8"}).status_code == 404
    assert client.get("/v1/price-changes", headers={"X-Forwarded-For": "8.8.8.8, 127.0.0.1"}).status_code == 200
    assert client.get("/v1/catalog", headers={"X-Forwarded-For": "10.0.0.5, 8.8.8.8"}).status_code == 404


def test_a_public_peer_cannot_claim_to_be_local():
    public = _peer("8.8.8.8")
    for fwd in ("127.0.0.1", "10.0.0.1", "8.8.4.4, 127.0.0.1"):
        assert public.get("/v1/price-changes", headers={"X-Forwarded-For": fwd}).status_code == 404, fwd
        assert public.get("/v1/catalog", headers={"X-Forwarded-For": fwd}).status_code == 404, fwd


def test_a_public_peer_cannot_skip_the_rate_limit(monkeypatch):
    monkeypatch.setattr(settings, "RATE_LIMIT", 2)
    public = _peer("9.9.9.9")
    codes = [public.get("/v1/meta", headers={"X-Forwarded-For": "10.0.0.1"}).status_code for _ in range(3)]
    assert codes == [200, 200, 429]
