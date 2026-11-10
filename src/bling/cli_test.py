import json

import httpx
import respx
from typer.testing import CliRunner

from bling import cli
from bling.vapi import KEYTERMS

runner = CliRunner()
NO_VERDICT = (
    "I couldn't make the call right now. I couldn't check traffic. I couldn't check transit."
)
LISTEN = "https://api.deepgram.com/v1/listen"
SPEAK = "https://api.deepgram.com/v1/speak"


def test_ask_without_keys():
    r = runner.invoke(cli.app, ["ask", "SFO", "--from", "Oakland", "--by", "6pm"])
    assert r.exit_code == 0 and r.output.strip() == NO_VERDICT


def test_ask_passes_situation(monkeypatch):
    seen = {}

    async def fake_plan(trip, **kw):
        seen["trip"] = trip
        return await orig(trip, **kw)

    orig = cli.plan_trip
    monkeypatch.setattr(cli, "plan_trip", fake_plan)
    r = runner.invoke(cli.app, ["ask", "SFO", "--situation", "bike"])
    assert r.exit_code == 0 and seen["trip"].situation == "bike"


def test_audio_and_say_need_deepgram(tmp_path):
    (tmp_path / "me.wav").write_bytes(b"RIFF")
    for args in (["--audio", "me.wav"], ["--say", "out.mp3"]):
        r = runner.invoke(cli.app, ["ask", "SFO", *args])
        assert r.exit_code == 1 and "DEEPGRAM_API_KEY is not set" in r.output


@respx.mock
def test_ask_audio_and_say(monkeypatch, tmp_path):
    monkeypatch.setenv("DEEPGRAM_API_KEY", "dgk")
    (tmp_path / "me.m4a").write_bytes(b"AUDIO")
    listen = respx.post(LISTEN).mock(return_value=httpx.Response(200, json={
        "results": {"channels": [{"alternatives": [{"transcript": "I have two suitcases"}]}]}}))
    speak = respx.post(SPEAK).mock(return_value=httpx.Response(200, content=b"MP3"))
    seen = {}
    orig = cli.plan_trip

    async def fake_plan(trip, **kw):
        seen["trip"] = trip
        return await orig(trip, **kw)

    monkeypatch.setattr(cli, "plan_trip", fake_plan)
    r = runner.invoke(cli.app, ["ask", "SFO", "--situation", "in a hurry", "--audio", "me.m4a",
                                "--say", "out.mp3"])
    assert r.exit_code == 0, r.output
    lines = r.output.strip().splitlines()
    assert lines[0] == "heard: I have two suitcases"
    assert lines[1] == NO_VERDICT and lines[2] == "wrote out.mp3"
    assert seen["trip"].situation == "in a hurry I have two suitcases"
    req = listen.calls[0].request
    assert req.headers["content-type"] == "audio/mp4" and req.content == b"AUDIO"
    assert req.url.params.get_list("keyterm") == KEYTERMS
    assert json.loads(speak.calls[0].request.content) == {"text": NO_VERDICT}
    assert (tmp_path / "out.mp3").read_bytes() == b"MP3"


def test_content_types(tmp_path):
    from pathlib import Path
    assert cli.content_type_for(Path("a.WAV")) == "audio/wav"
    assert cli.content_type_for(Path("a.flac")) == "audio/flac"
    assert cli.content_type_for(Path("a.ogg")) == "audio/ogg"
    assert cli.content_type_for(Path("a.webm")) == "audio/webm"
    assert cli.content_type_for(Path("a.mp3")) == "audio/mpeg"
    assert cli.content_type_for(Path("a.aiff")) == "application/octet-stream"


def test_vapi_sync_requires_settings(monkeypatch):
    monkeypatch.setenv("VAPI_API_KEY", "vk")
    r = runner.invoke(cli.app, ["vapi-sync"])
    assert r.exit_code == 1 and "VAPI_SERVER_SECRET is not set" in r.output


def _sync_env(monkeypatch):
    monkeypatch.setenv("VAPI_API_KEY", "vk")
    monkeypatch.setenv("VAPI_SERVER_SECRET", "sek-123")
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://b.example")
    monkeypatch.setenv("DEEPGRAM_API_KEY", "dgk-456")


@respx.mock
def test_vapi_sync_dry_run(monkeypatch):
    _sync_env(monkeypatch)
    r = runner.invoke(cli.app, ["vapi-sync", "--dry-run"])
    assert r.exit_code == 0
    body = json.loads(r.output)
    assert body["credentials"] == [{"provider": "deepgram", "apiKey": "***"}]
    assert body["server"]["headers"] == {"x-bling-secret": "***"}
    assert "sek-123" not in r.output and "dgk-456" not in r.output and "vk" not in r.output
    assert not respx.calls


@respx.mock
def test_vapi_sync_create_and_update(monkeypatch):
    _sync_env(monkeypatch)
    post = respx.post("https://api.vapi.ai/assistant").mock(
        return_value=httpx.Response(201, json={"id": "as9"}))
    r = runner.invoke(cli.app, ["vapi-sync"])
    assert r.exit_code == 0 and "Add VAPI_ASSISTANT_ID=as9 to .env" in r.output
    sent = json.loads(post.calls[0].request.content)
    assert sent["name"] == "Bling" and sent["credentials"][0]["apiKey"] == "dgk-456"
    monkeypatch.setenv("VAPI_ASSISTANT_ID", "as9")
    patch = respx.patch("https://api.vapi.ai/assistant/as9").mock(
        side_effect=[httpx.Response(200, json={"id": "as9"}),
                     httpx.Response(400, json={"message": "bad"})])
    r = runner.invoke(cli.app, ["vapi-sync"])
    assert r.exit_code == 0 and patch.called and "Updated assistant as9" in r.output
    r = runner.invoke(cli.app, ["vapi-sync"])
    assert r.exit_code == 1 and "HTTP 400: bad" in r.output and "dgk-456" not in r.output
