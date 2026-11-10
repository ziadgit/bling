import json

import httpx
import pytest
import respx
from pydantic import SecretStr

from bling.config import Settings
from bling.decision_test import FakeJev
from bling.links import LinkStore
from bling.vapi import SYSTEM_PROMPT, Deps, VapiApi, assistant_body, check_secret, handle_message


def deps(tmp_path, **kw):
    s = Settings(vapi_server_secret=SecretStr("sek"), **kw)
    return Deps(settings=s, links=LinkStore(tmp_path / "links", 24), jev=FakeJev("drive"))


def body(*calls, type="tool-calls"):
    return {"message": {"type": type, "toolCallList": list(calls)}}


def call(id, name, args):
    return {"id": id, "function": {"name": name, "arguments": args}}


def test_check_secret():
    s = Settings(vapi_server_secret=SecretStr("sek"))
    assert check_secret("sek", s)
    assert not check_secret("nope", s) and not check_secret(None, s)
    assert not check_secret("sek", Settings())


async def test_plan_trip_and_errors(tmp_path):
    d = deps(tmp_path)
    out = await handle_message(
        body(
            call("a", "plan_trip", {"destination": "SFO"}),
            call("b", "plan_trip", json.dumps({"destination": "SFO", "origin": "Oakland"})),
            call("c", "plan_trip", {}),
            call("d", "nope", {}),
            call("e", "plan_trip", "{bad json"),
        ),
        d,
    )
    r = out["results"]
    assert [x["toolCallId"] for x in r] == ["a", "b", "c", "d", "e"]
    assert r[0]["name"] == "plan_trip" and r[0]["result"].startswith("Drive.")
    assert "error" not in r[0] and "result" not in r[2]
    assert r[2]["error"] == "I need a destination."
    assert "error" in r[3] and "error" in r[4]
    assert all(isinstance(x.get("result", x.get("error")), str) for x in r)


async def test_other_types(tmp_path):
    assert await handle_message(body(type="status-update"), deps(tmp_path)) == {}
    assert await handle_message({}, deps(tmp_path)) == {}


async def test_voice_link(tmp_path):
    d = deps(tmp_path, public_base_url="https://b.example")
    out = await handle_message(
        body(
            call("r", "voice_link", {"mode": "review", "destination": "SFO"}),
            call("e", "voice_link", {"mode": "explain", "destination": "SFO"}),
        ),
        d,
    )
    review, explain = (x["result"] for x in out["results"])
    assert review.startswith("Drive.") and " Listen here: https://b.example/v/" in review
    tok = review.rsplit("/", 1)[1]
    assert d.links.get(tok).kind == "review" and d.links.get(tok).rec.mode == "drive"
    assert explain.startswith(
        "Record your situation here and I'll decide with it: https://b.example/e/"
    )
    etok = explain.rsplit("/", 1)[1]
    assert d.links.get(etok).kind == "explain" and d.links.get(etok).rec is None


async def test_voice_link_unconfigured(tmp_path):
    out = await handle_message(
        body(call("x", "voice_link", {"mode": "review", "destination": "SFO"})), deps(tmp_path)
    )
    assert out["results"][0] == {
        "name": "voice_link", "toolCallId": "x", "error": "Voice links aren't set up yet."}


def test_assistant_body():
    s = Settings(vapi_server_secret=SecretStr("sek"), public_base_url="https://b.example")
    b = assistant_body(s)
    assert b["server"] == {"url": "https://b.example/vapi/webhook",
                           "headers": {"x-bling-secret": "sek"}}
    assert b["model"]["provider"] == "openai" and b["model"]["model"] == "gpt-4.1"
    assert b["model"]["messages"] == [{"role": "system", "content": SYSTEM_PROMPT}]
    names = [t["function"]["name"] for t in b["model"]["tools"]]
    assert names == ["plan_trip", "voice_link"]
    assert b["transcriber"] == {"provider": "deepgram", "model": "nova-3"}
    assert b["voice"] == {"provider": "deepgram", "voiceId": "asteria"}
    assert b["serverMessages"] == ["tool-calls"]


@respx.mock
def test_vapi_api():
    post = respx.post("https://api.vapi.ai/assistant").mock(
        return_value=httpx.Response(201, json={"id": "as1"}))
    patch = respx.patch("https://api.vapi.ai/assistant/as1").mock(
        side_effect=[httpx.Response(200, json={"id": "as1"}), httpx.Response(400)])
    with httpx.Client() as http:
        api = VapiApi("vk", http)
        assert api.create_assistant({"name": "Bling"})["id"] == "as1"
        assert post.calls[0].request.headers["authorization"] == "Bearer vk"
        assert json.loads(post.calls[0].request.content) == {"name": "Bling"}
        api.update_assistant("as1", {"name": "Bling"})
        assert patch.calls[0].request.headers["authorization"] == "Bearer vk"
        with pytest.raises(RuntimeError, match="400"):
            api.update_assistant("as1", {})
