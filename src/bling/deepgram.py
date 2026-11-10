"""Deepgram speech-to-text and text-to-speech over raw HTTP."""

import httpx

BASE = "https://api.deepgram.com/v1"
TIMEOUT = 30.0


class DeepgramClient:
    def __init__(self, api_key: str, http: httpx.AsyncClient, stt_model: str, tts_model: str):
        self._key, self._http = api_key, http
        self.stt_model, self.tts_model = stt_model, tts_model

    def _auth(self) -> dict[str, str]:
        return {"Authorization": f"Token {self._key}"}

    async def transcribe(self, audio: bytes, content_type: str) -> str:
        r = await self._http.post(
            f"{BASE}/listen",
            params={"model": self.stt_model, "smart_format": "true"},
            headers={**self._auth(), "Content-Type": content_type},
            content=audio,
            timeout=TIMEOUT,
        )
        if not r.is_success:
            raise RuntimeError(f"deepgram listen HTTP {r.status_code}")
        try:
            return r.json()["results"]["channels"][0]["alternatives"][0]["transcript"] or ""
        except (KeyError, IndexError, TypeError, ValueError):
            return ""

    async def speak(self, text: str) -> bytes:
        r = await self._http.post(
            f"{BASE}/speak",
            params={"model": self.tts_model},
            headers=self._auth(),
            json={"text": text},
            timeout=TIMEOUT,
        )
        if not r.is_success:
            raise RuntimeError(f"deepgram speak HTTP {r.status_code}")
        return r.content
