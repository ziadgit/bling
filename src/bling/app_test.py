import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from bling.app import create_app
from bling.config import Settings
from bling.decision_test import FakeJev
from bling.domain import Conditions, Recommendation, TripRequest


class FakeDeepgram:
    def __init__(self, transcript="I have a bike with me"):
        self.transcript, self.spoken, self.heard = transcript, [], []

    async def transcribe(self, audio, content_type):
        self.heard.append((audio, content_type))
        return self.transcript

    async def speak(self, text):
        self.spoken.append(text)
        return b"MP3DATA"


@pytest.fixture
def env(tmp_path):
    s = Settings(vapi_server_secret=SecretStr("sek"), bling_data_dir=tmp_path / "data",
                 public_base_url="https://b.example")
    dg, jev = FakeDeepgram(), FakeJev("transit")
    app = create_app(s, jev=jev, deepgram=dg)
    with TestClient(app) as client:
        yield client, app.state.deps, dg, jev


TRIP = TripRequest(destination="<SFO>")


def test_healthz_and_no_docs(env):
    c, *_ = env
    assert c.get("/healthz").json() == {"status": "ok"}
    assert c.get("/docs").status_code == 404 and c.get("/openapi.json").status_code == 404


def test_webhook_auth_and_tools(env):
    c, *_ = env
    body = {"message": {"type": "tool-calls", "toolCallList": [
        {"id": "t1", "function": {"name": "plan_trip", "arguments": '{"destination": "SFO"}'}}]}}
    assert c.post("/vapi/webhook", json=body).status_code == 401
    assert c.post("/vapi/webhook", json=body, headers={"x-bling-secret": "x"}).status_code == 401
    r = c.post("/vapi/webhook", json=body, headers={"x-bling-secret": "sek"})
    assert r.status_code == 200
    res = r.json()["results"][0]
    assert res["toolCallId"] == "t1" and res["result"].startswith("Take transit.")
    r = c.post("/vapi/webhook", json={"message": {"type": "end-of-call-report"}},
               headers={"x-bling-secret": "sek"})
    assert r.json() == {}


def test_webhook_401_when_secret_unset(tmp_path):
    with TestClient(create_app(Settings(bling_data_dir=tmp_path))) as c:
        assert c.post("/vapi/webhook", json={}, headers={"x-bling-secret": ""}).status_code == 401


def test_review_page_and_audio_cache(env):
    c, deps, dg, _ = env
    rec = Recommendation(mode="drive", conditions=Conditions(), trip=TRIP, text="Drive <now>.")
    tok = deps.links.create("review", TRIP, rec)
    page = c.get(f"/v/{tok}")
    assert page.status_code == 200 and "Drive &lt;now&gt;." in page.text
    assert f'<audio controls autoplay src="/v/{tok}/audio">' in page.text
    for _ in range(2):
        a = c.get(f"/v/{tok}/audio")
        assert a.status_code == 200 and a.content == b"MP3DATA"
        assert a.headers["content-type"] == "audio/mpeg"
    assert dg.spoken == ["Drive <now>."]
    assert c.get("/v/..%2F..%2Fetc").status_code == 404
    assert c.get("/v/" + "z" * 20).status_code == 404
    assert c.get("/v/" + "z" * 20 + "/audio").status_code == 404


def test_explain_flow(env):
    c, deps, dg, jev = env
    tok = deps.links.create("explain", TRIP)
    page = c.get(f"/e/{tok}")
    assert page.status_code == 200 and "Tell me about your trip to &lt;SFO&gt;" in page.text
    assert "MediaRecorder" in page.text and "<script src" not in page.text
    r = c.post(f"/e/{tok}/audio", files={"audio": ("a.webm", b"AUD", "audio/ogg")})
    assert r.status_code == 200
    j = r.json()
    assert j["transcript"] == "I have a bike with me" and j["text"].startswith("Take transit.")
    assert dg.heard == [(b"AUD", "audio/ogg")]
    assert jev.calls[-1][0]["situation"] == "I have a bike with me"
    assert c.get(j["audio_url"]).content == b"MP3DATA"
    assert deps.links.get(tok).used is True
    again = c.post(f"/e/{tok}/audio", files={"audio": ("a.webm", b"AUD", "audio/webm")})
    assert again.status_code == 409


def test_explain_errors(env):
    c, deps, dg, _ = env
    assert c.post("/e/" + "q" * 20 + "/audio", files={"audio": ("a", b"x")}).status_code == 404
    assert c.get("/e/" + "q" * 20).status_code == 404
    review = deps.links.create("review", TRIP)
    assert c.post(f"/e/{review}/audio", files={"audio": ("a", b"x")}).status_code == 409
    tok = deps.links.create("explain", TRIP)
    big = b"0" * (10 * 1024 * 1024 + 1)
    assert c.post(f"/e/{tok}/audio", files={"audio": ("a", big)}).status_code == 413
    dg.transcript = "  "
    r = c.post(f"/e/{tok}/audio", files={"audio": ("a", b"x")})
    assert r.status_code == 422 and r.json() == {"error": "I didn't catch that, try again."}
    assert deps.links.get(tok).used is False
