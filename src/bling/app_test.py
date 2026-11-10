import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from bling.app import create_app
from bling.config import Settings
from bling.decision_test import FakeJev

BODY = {"message": {"type": "tool-calls", "toolCallList": [
    {"id": "t1", "function": {"name": "plan_trip", "arguments": '{"destination": "SFO"}'}}]}}


@pytest.fixture
def client(tmp_path):
    s = Settings(vapi_server_secret=SecretStr("sek"), bling_data_dir=tmp_path / "data")
    with TestClient(create_app(s, jev=FakeJev("transit"))) as c:
        yield c


def test_healthz_and_nothing_else(client):
    assert client.get("/healthz").json() == {"status": "ok"}
    for path in ("/docs", "/openapi.json", "/redoc", "/v/" + "a" * 20, "/e/" + "a" * 20):
        assert client.get(path).status_code == 404
    paths = {r.path for r in client.app.routes}
    assert paths == {"/", "/healthz", "/vapi/webhook"}
    page = client.get("/")
    assert page.status_code == 200 and "text/html" in page.headers["content-type"]
    assert "Bling" in page.text and "github.com/ziadgit/bling" in page.text
    assert "<script src" not in page.text


def test_webhook_auth_and_tools(client):
    assert client.post("/vapi/webhook", json=BODY).status_code == 401
    bad = client.post("/vapi/webhook", json=BODY, headers={"x-bling-secret": "x"})
    assert bad.status_code == 401
    r = client.post("/vapi/webhook", json=BODY, headers={"x-bling-secret": "sek"})
    assert r.status_code == 200
    res = r.json()["results"][0]
    assert res["toolCallId"] == "t1" and res["result"].startswith("Take transit.")
    other = client.post("/vapi/webhook", json={"message": {"type": "end-of-call-report"}},
                        headers={"x-bling-secret": "sek"})
    assert other.status_code == 200 and other.json() == {}
    junk = client.post("/vapi/webhook", content=b"not json", headers={"x-bling-secret": "sek"})
    assert junk.status_code == 200 and junk.json() == {}


def test_webhook_401_when_secret_unset(tmp_path):
    with TestClient(create_app(Settings(bling_data_dir=tmp_path))) as c:
        assert c.post("/vapi/webhook", json=BODY, headers={"x-bling-secret": ""}).status_code == 401


def test_clients_built_lazily_without_lifespan(monkeypatch, tmp_path):
    import exa_py

    class FakeAsyncExa:
        def __init__(self, api_key):
            self.api_key = api_key

        async def search(self, query, **kw):
            raise RuntimeError("offline")

    monkeypatch.setattr(exa_py, "AsyncExa", FakeAsyncExa)
    s = Settings(vapi_server_secret=SecretStr("sek"), exa_api_key=SecretStr("ek"))
    app = create_app(s)
    c = TestClient(app)  # no `with`: the lifespan never runs, as on Vercel
    r = c.post("/vapi/webhook", json=BODY, headers={"x-bling-secret": "sek"})
    assert r.status_code == 200
    assert isinstance(app.state.deps.exa, FakeAsyncExa) and app.state.deps.exa.api_key == "ek"
    assert "I couldn't check traffic" in r.json()["results"][0]["result"]
