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
    "You are Bling, a voice assistant that helps someone in the San Francisco Bay Area decide "
    "whether to drive or take public transit. Get the destination, and the origin and arrival "
    "time if they offer them. If they mention their circumstances (luggage, kids, mobility, "
    "budget, parking, urgency), pass them as situation. Ask at most one short follow-up. Then "
    "call plan_trip and say its answer in your own words, keeping every fact. Never guess "
    "traffic or transit conditions yourself. Speak in short sentences. No lists, no URLs."
)

KEYTERMS: list[str] = [
    "BART", "Muni", "Caltrain", "AC Transit", "VTA", "SamTrans", "Golden Gate Transit",
    "Salesforce Transit Center", "Embarcadero", "SFO", "Oakland Airport", "San Jose Airport",
    "Bay Bridge", "Golden Gate Bridge", "San Mateo Bridge", "Dumbarton Bridge", "Richmond Bridge",
    "US-101", "I-80", "I-280", "I-580", "I-680", "I-880", "Highway 1",
]

SITUATION_DESCRIPTION = (
    "Anything the caller said about their circumstances that could change the choice: luggage, "
    "kids, mobility, budget, parking, being in a hurry, the weather where they are. Omit it if "
    "they said nothing."
)

PLAN_TRIP_TOOL = {
    "type": "function",
    "function": {
        "name": "plan_trip",
        "description": "Check live traffic and transit conditions and decide: drive or take transit.",
        "parameters": {
            "type": "object",
            "properties": {
                "destination": {"type": "string", "description": "Where the caller is going."},
                "origin": {"type": "string", "description": "Where they are starting from, if given."},
                "arrive_by": {"type": "string", "description": "When they need to arrive, as they said it."},
                "situation": {"type": "string", "description": SITUATION_DESCRIPTION},
            },
            "required": ["destination"],
        },
    },
    "messages": [{"type": "request-start", "content": "Let me check the roads and transit."}],
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

    return TripRequest(
        destination=dest.strip(),
        origin=opt("origin"),
        arrive_by=opt("arrive_by"),
        situation=opt("situation"),
    )


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
    body: dict[str, Any] = {
        "name": "Bling",
        "firstMessage": "Hey, it's Bling. Where are you headed?",
        "transcriber": {
            "provider": "deepgram",
            "model": settings.deepgram_stt_model,
            "language": "en",
            "keyterm": list(KEYTERMS),
            "endpointing": 300,
        },
        "voice": {"provider": "deepgram", "voiceId": settings.vapi_voice_id},
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
    if settings.deepgram_api_key is not None:
        body["credentials"] = [
            {"provider": "deepgram", "apiKey": settings.deepgram_api_key.get_secret_value()}
        ]
    return body


SECRET_KEYS = {"apiKey", "x-bling-secret"}


def mask_secrets(value: Any) -> Any:
    """A copy of an assistant body with every secret value replaced by "***"."""
    if isinstance(value, dict):
        return {k: "***" if k in SECRET_KEYS else mask_secrets(v) for k, v in value.items()}
    if isinstance(value, list):
        return [mask_secrets(v) for v in value]
    return value


def _secret_values(value: Any) -> list[str]:
    if isinstance(value, dict):
        out = [v for k, v in value.items() if k in SECRET_KEYS and isinstance(v, str) and v]
        return out + [s for v in value.values() for s in _secret_values(v)]
    if isinstance(value, list):
        return [s for v in value for s in _secret_values(v)]
    return []


def _vapi_error(r: httpx.Response) -> str:
    """Vapi's own error message, never anything from the request (it carries keys)."""
    try:
        data = r.json()
    except ValueError:
        return ""
    msg = data.get("message") or data.get("error") if isinstance(data, dict) else None
    if isinstance(msg, list):
        msg = "; ".join(str(m) for m in msg)
    return str(msg)[:300] if msg else ""


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
            detail = _vapi_error(r)
            for secret in [self._key, *_secret_values(body)]:
                detail = detail.replace(secret, "***")
            raise RuntimeError(
                f"vapi {method} {path} HTTP {r.status_code}" + (f": {detail}" if detail else "")
            )
        return r.json()

    def create_assistant(self, body: dict[str, Any]) -> dict[str, Any]:
        return self._send("POST", "/assistant", body)

    def update_assistant(self, assistant_id: str, body: dict[str, Any]) -> dict[str, Any]:
        return self._send("PATCH", f"/assistant/{assistant_id}", body)
