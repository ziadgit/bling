# ruff: noqa: E501 - SYSTEM_PROMPT is literal spec text
"""Vapi: the webhook tools, the assistant definition, and a small REST client."""

import asyncio
import hmac
import json
import logging
import time
from dataclasses import dataclass
from typing import Any

import httpx

from .config import Settings, require
from .domain import TripRequest
from .pipeline import plan_trip, reply_text

log = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are Bling. You help someone decide whether to drive or take public transit. Get the "
    "destination (and the origin and arrival time if they offer them), then call plan_trip and "
    "relay its answer briefly, word for word on facts. Never guess traffic or transit conditions "
    "yourself. In a text conversation: if the person wants to hear the recommendation, call "
    'voice_link with mode "review"; if they want to explain their situation by voice, call '
    'voice_link with mode "explain". Send the link exactly as returned. Keep replies under two '
    "sentences."
)

_TRIP_PROPS = {
    "destination": {"type": "string", "description": "Where the person is going."},
    "origin": {"type": "string", "description": "Where they are starting from, if given."},
    "arrive_by": {"type": "string", "description": "When they need to arrive, as they said it."},
}

PLAN_TRIP_TOOL = {
    "type": "function",
    "function": {
        "name": "plan_trip",
        "description": "Check live traffic and transit conditions and decide: drive or take transit.",
        "parameters": {"type": "object", "properties": _TRIP_PROPS, "required": ["destination"]},
    },
}

class ToolError(Exception):
    """A user-facing tool failure; its message goes back to Vapi as `error`."""


@dataclass
class Deps:
    settings: Settings
    exa: Any = None
    jev: Any = None


def check_secret(header: str | None, settings: Settings) -> bool:
    if settings.vapi_server_secret is None or not header:
        return False
    expected = settings.vapi_server_secret.get_secret_value()
    return hmac.compare_digest(header.encode(), expected.encode())


def _trip(args: dict[str, Any]) -> TripRequest:
    dest = args.get("destination")
    if not isinstance(dest, str) or not dest.strip():
        raise ToolError("I need a destination.")

    def opt(k: str) -> str | None:
        v = args.get(k)
        return v.strip() or None if isinstance(v, str) else None

    return TripRequest(destination=dest.strip(), origin=opt("origin"), arrive_by=opt("arrive_by"))


async def tool_plan_trip(args: dict[str, Any], deps: Deps) -> str:
    rec = await plan_trip(_trip(args), exa=deps.exa, jev=deps.jev, settings=deps.settings)
    return reply_text(rec)


TOOLS = {"plan_trip": tool_plan_trip}


async def _run_call(call: Any, deps: Deps) -> dict[str, Any]:
    call = call if isinstance(call, dict) else {}
    call_id = call.get("id")
    fn = call.get("function") if isinstance(call.get("function"), dict) else {}
    name = fn.get("name")
    out: dict[str, Any] = {"name": name, "toolCallId": call_id}
    start = time.monotonic()
    try:
        raw = fn.get("arguments") or {}
        args = json.loads(raw) if isinstance(raw, str) else raw
        if not isinstance(args, dict):
            raise ToolError("Bad arguments.")
        tool = TOOLS.get(name)
        if tool is None:
            raise ToolError(f"Unknown tool {name}.")
        out["result"] = str(await tool(args, deps))
    except ToolError as e:
        out["error"] = str(e)
    except ValueError:
        out["error"] = "Bad arguments."
    except Exception as e:  # noqa: BLE001 - one bad tool call must not fail the rest
        log.warning("tool %s failed: %s", name, type(e).__name__)
        out["error"] = "Something went wrong, try again."
    log.info("tool %s took %.2fs", name, time.monotonic() - start)
    return out


async def handle_message(body: Any, deps: Deps) -> dict[str, Any]:
    message = body.get("message") if isinstance(body, dict) else None
    if not isinstance(message, dict) or message.get("type") != "tool-calls":
        return {}
    calls = message.get("toolCallList") or []
    results = await asyncio.gather(*(_run_call(c, deps) for c in calls))
    return {"results": list(results)}


def assistant_body(settings: Settings) -> dict[str, Any]:
    base = (settings.public_base_url or "").rstrip("/")
    return {
        "name": "Bling",
        "firstMessage": "Hey, it's Bling. Where are you headed?",
        "transcriber": {"provider": "deepgram", "model": settings.deepgram_stt_model},
        "voice": {"provider": "deepgram", "voiceId": "asteria"},
        "model": {
            "provider": settings.vapi_llm_provider,
            "model": settings.vapi_llm_model,
            "messages": [{"role": "system", "content": SYSTEM_PROMPT}],
            "tools": [PLAN_TRIP_TOOL],
        },
        "server": {
            "url": f"{base}/vapi/webhook",
            "headers": {
                "x-bling-secret": require(settings.vapi_server_secret, "VAPI_SERVER_SECRET")
            },
        },
        "serverMessages": ["tool-calls"],
    }


class VapiApi:
    BASE = "https://api.vapi.ai"

    def __init__(self, api_key: str, http: httpx.Client):
        self._key, self._http = api_key, http

    def _send(self, method: str, path: str, body: dict[str, Any]) -> dict[str, Any]:
        r = self._http.request(
            method,
            f"{self.BASE}{path}",
            json=body,
            headers={"Authorization": f"Bearer {self._key}"},
            timeout=30.0,
        )
        if not r.is_success:
            raise RuntimeError(f"vapi {method} {path} HTTP {r.status_code}")
        return r.json()

    def create_assistant(self, body: dict[str, Any]) -> dict[str, Any]:
        return self._send("POST", "/assistant", body)

    def update_assistant(self, assistant_id: str, body: dict[str, Any]) -> dict[str, Any]:
        return self._send("PATCH", f"/assistant/{assistant_id}", body)
