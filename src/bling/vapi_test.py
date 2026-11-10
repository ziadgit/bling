import json

import httpx
import pytest
import respx
from pydantic import SecretStr

from bling.config import Settings
from bling.decision_test import FakeJev
from bling.vapi import (
    KEYTERMS,
    PLAN_TRIP_TOOL,
    SITUATION_DESCRIPTION,
    SYSTEM_PROMPT,
    Deps,
    VapiApi,
    assistant_body,
    check_secret,
    handle_message,
    mask_secrets,
)


def deps(**kw):
    jev = FakeJev("drive")
    return Deps(settings=Settings(vapi_server_secret=SecretStr("sek"), **kw), jev=jev), jev


def body(*calls, type="tool-calls"):
    return {"message": {"type": type, "toolCallList": list(calls)}}


def call(id, name, args):
    return {"id": id, "function": {"name": name, "arguments": args}}


def test_check_secret():
    s = Settings(vapi_server_secret=SecretStr("sek"))
    assert check_secret("sek", s)
    assert not check_secret("nope", s) and not check_secret(None, s)
    assert not check_secret("sek", Settings())


async def test_plan_trip_and_errors():
    d, jev = deps()
    out = await handle_message(
        body(
            call("a", "plan_trip", {"destination": "SFO"}),
            call("b", "plan_trip", json.dumps(
                {"destination": "SFO", "origin": "Oakland", "situation": "two suitcases"})),
            call("c", "plan_trip", {}),
            call("d", "voice_link", {"mode": "review", "destination": "SFO"}),
            call("e", "plan_trip", "{bad json"),
        ),
        d,
    )
    r = out["results"]
    assert [x["toolCallId"] for x in r] == ["a", "b", "c", "d", "e"]
    assert r[0]["name"] == "plan_trip" and r[0]["result"].startswith("Drive.")
    assert "error" not in r[0] and "result" not in r[2]
    assert r[2]["error"] == "I need a destination."
    assert "error" in r[3] and "result" not in r[3] and "error" in r[4]
    assert all(isinstance(x.get("result", x.get("error")), str) for x in r)
    situations = sorted(str(state["situation"]) for state, _ in jev.calls)
    assert situations == ["none given", "two suitcases"]


async def test_other_types():
    d, _ = deps()
    assert await handle_message(body(type="status-update"), d) == {}
    assert await handle_message({}, d) == {}


def test_plan_trip_tool():
    assert PLAN_TRIP_TOOL["type"] == "function"
    params = PLAN_TRIP_TOOL["function"]["parameters"]
    assert set(params["properties"]) == {"destination", "origin", "arrive_by", "situation"}
    assert params["required"] == ["destination"]
    assert params["properties"]["situation"]["description"] == SITUATION_DESCRIPTION
    assert SITUATION_DESCRIPTION.startswith("Anything the caller said about their circumstances")
    assert PLAN_TRIP_TOOL["messages"] == [
        {"type": "request-start", "content": "Let me check the roads and transit."}]


def test_assistant_body_without_deepgram_key():
    s = Settings(vapi_server_secret=SecretStr("sek"), public_base_url="https://b.example")
    b = assistant_body(s)
    assert b["name"] == "Bling" and b["firstMessage"] == "Hey, it's Bling. Where are you headed?"
    assert b["server"] == {"url": "https://b.example/vapi/webhook",
                           "headers": {"x-bling-secret": "sek"}}
    assert b["model"]["provider"] == "openai" and b["model"]["model"] == "gpt-4.1"
    assert b["model"]["messages"] == [{"role": "system", "content": SYSTEM_PROMPT}]
    assert b["model"]["tools"] == [PLAN_TRIP_TOOL]
    assert b["transcriber"] == {"provider": "deepgram", "model": "nova-3", "language": "en",
                                "keyterm": KEYTERMS, "endpointing": 300}
    assert b["voice"] == {"provider": "deepgram", "voiceId": "asteria"}
    assert b["serverMessages"] == ["tool-calls"]
    assert "credentials" not in b
    assert "voice_link" not in json.dumps(b) and "text conversation" not in SYSTEM_PROMPT


def test_assistant_body_with_deepgram_key_and_voice():
    s = Settings(vapi_server_secret=SecretStr("sek"), public_base_url="https://b.example",
                 deepgram_api_key=SecretStr("dgk"), vapi_voice_id="luna")
    b = assistant_body(s)
    assert b["credentials"] == [{"provider": "deepgram", "apiKey": "dgk"}]
    assert b["voice"]["voiceId"] == "luna"
    masked = mask_secrets(b)
    assert masked["credentials"] == [{"provider": "deepgram", "apiKey": "***"}]
    assert masked["server"]["headers"] == {"x-bling-secret": "***"}
    assert "dgk" not in json.dumps(masked) and "sek" not in json.dumps(masked)
    assert b["credentials"][0]["apiKey"] == "dgk"  # original untouched


def test_keyterms():
    assert len(KEYTERMS) == 24 and KEYTERMS[0] == "BART" and KEYTERMS[-1] == "Highway 1"
    assert "Salesforce Transit Center" in KEYTERMS and "I-880" in KEYTERMS


@respx.mock
def test_vapi_api():
    post = respx.post("https://api.vapi.ai/assistant").mock(
        return_value=httpx.Response(201, json={"id": "as1"}))
    patch = respx.patch("https://api.vapi.ai/assistant/as1").mock(
        side_effect=[httpx.Response(200, json={"id": "as1"}),
                     httpx.Response(400, json={"message": ["bad key dgk", "voice invalid"]})])
    with httpx.Client() as http:
        api = VapiApi("vk", http)
        assert api.create_assistant({"name": "Bling"})["id"] == "as1"
        assert post.calls[0].request.headers["authorization"] == "Bearer vk"
        assert json.loads(post.calls[0].request.content) == {"name": "Bling"}
        api.update_assistant("as1", {"name": "Bling"})
        assert patch.calls[0].request.headers["authorization"] == "Bearer vk"
        secret_body = {"credentials": [{"provider": "deepgram", "apiKey": "dgk"}]}
        with pytest.raises(RuntimeError) as exc:
            api.update_assistant("as1", secret_body)
    msg = str(exc.value)
    assert "HTTP 400" in msg and "voice invalid" in msg and "dgk" not in msg
