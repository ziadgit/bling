import json

import httpx
import pytest
import respx

from bling.deepgram import DeepgramClient


@pytest.fixture
async def dg():
    async with httpx.AsyncClient() as http:
        yield DeepgramClient("k123", http, "nova-3", "aura-2-thalia-en")


@respx.mock
async def test_transcribe(dg):
    route = respx.post("https://api.deepgram.com/v1/listen").mock(
        return_value=httpx.Response(
            200, json={"results": {"channels": [{"alternatives": [{"transcript": "hi there"}]}]}}
        )
    )
    assert await dg.transcribe(b"AUDIO", "audio/webm", ["BART", "Bay Bridge"]) == "hi there"
    req = route.calls[0].request
    assert req.url.params.multi_items() == [
        ("model", "nova-3"), ("smart_format", "true"), ("keyterm", "BART"),
        ("keyterm", "Bay Bridge")]
    assert "keyterm=Bay+Bridge" in str(req.url) or "keyterm=Bay%20Bridge" in str(req.url)
    assert req.headers["authorization"] == "Token k123"
    assert req.headers["content-type"] == "audio/webm"
    assert req.content == b"AUDIO"


@respx.mock
async def test_transcribe_missing_and_error(dg):
    respx.post("https://api.deepgram.com/v1/listen").mock(
        side_effect=[httpx.Response(200, json={}), httpx.Response(500)]
    )
    assert await dg.transcribe(b"x", "audio/webm") == ""
    assert "keyterm" not in str(respx.calls.last.request.url)
    with pytest.raises(RuntimeError, match="deepgram listen HTTP 500"):
        await dg.transcribe(b"x", "audio/webm")


@respx.mock
async def test_speak(dg):
    route = respx.post("https://api.deepgram.com/v1/speak").mock(
        side_effect=[httpx.Response(200, content=b"MP3"), httpx.Response(401)]
    )
    assert await dg.speak("Drive.") == b"MP3"
    req = route.calls[0].request
    assert dict(req.url.params) == {"model": "aura-2-thalia-en"}
    assert req.headers["authorization"] == "Token k123"
    assert json.loads(req.content) == {"text": "Drive."}
    with pytest.raises(RuntimeError, match="deepgram speak HTTP 401"):
        await dg.speak("x")
