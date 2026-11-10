import json

import httpx
import respx
from typer.testing import CliRunner

from bling import cli

runner = CliRunner()


def test_ask_without_keys():
    r = runner.invoke(cli.app, ["ask", "SFO", "--from", "Oakland", "--by", "6pm"])
    assert r.exit_code == 0
    assert r.output.strip() == (
        "I couldn't make the call right now. I couldn't check traffic. I couldn't check transit."
    )


def test_ask_uses_plan_trip(monkeypatch):
    seen = {}

    async def fake_ask(trip, settings):
        seen["trip"] = trip
        return "Drive."

    monkeypatch.setattr(cli, "_ask", fake_ask)
    r = runner.invoke(cli.app, ["ask", "SFO", "--situation", "bike"])
    assert r.output.strip() == "Drive." and seen["trip"].situation == "bike"


def test_vapi_sync_requires_settings(monkeypatch):
    monkeypatch.setenv("VAPI_API_KEY", "vk")
    r = runner.invoke(cli.app, ["vapi-sync"])
    assert r.exit_code == 1 and "VAPI_SERVER_SECRET is not set" in r.output


@respx.mock
def test_vapi_sync_create_and_update(monkeypatch):
    monkeypatch.setenv("VAPI_API_KEY", "vk")
    monkeypatch.setenv("VAPI_SERVER_SECRET", "sek")
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://b.example")
    post = respx.post("https://api.vapi.ai/assistant").mock(
        return_value=httpx.Response(201, json={"id": "as9"}))
    r = runner.invoke(cli.app, ["vapi-sync"])
    assert r.exit_code == 0 and "Add VAPI_ASSISTANT_ID=as9 to .env" in r.output
    assert json.loads(post.calls[0].request.content)["name"] == "Bling"
    monkeypatch.setenv("VAPI_ASSISTANT_ID", "as9")
    patch = respx.patch("https://api.vapi.ai/assistant/as9").mock(
        return_value=httpx.Response(200, json={"id": "as9"}))
    r = runner.invoke(cli.app, ["vapi-sync"])
    assert r.exit_code == 0 and patch.called
