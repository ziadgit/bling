"""plan_trip: conditions then decision, under one deadline. reply_text: the SMS/voice reply."""

import asyncio
from typing import Any

from .conditions import fetch_conditions
from .config import Settings
from .domain import Conditions, Recommendation, TripRequest

MAX_CHARS = 320
VERDICT = {
    "drive": "Drive.",
    "transit": "Take transit.",
    "either": "Either works.",
    None: "I couldn't make the call right now.",
}
RANK = {"severe": 0, "moderate": 1, "minor": 2}


async def plan_trip(trip: TripRequest, *, exa: Any, jev: Any, settings: Settings) -> Recommendation:
    from .decision import decide

    async def run() -> Recommendation:
        if exa is None:
            conditions = Conditions(missing=["traffic", "transit"])
        else:
            conditions = await fetch_conditions(trip, exa, settings)
        return await decide(trip, conditions, jev, settings)

    try:
        async with asyncio.timeout(settings.plan_deadline_s):
            return await run()
    except TimeoutError:
        rec = Recommendation(
            mode=None, conditions=Conditions(missing=["traffic", "transit"]), trip=trip, text=""
        )
        rec.text = reply_text(rec)
        return rec


def _truncate(text: str, limit: int = MAX_CHARS) -> str:
    if len(text) <= limit:
        return text
    cut = text[: limit - 1].rsplit(" ", 1)[0].rstrip(" ,;:")
    return cut + "…"


def _sentence(s: str) -> str:
    s = s.strip()
    return s if s.endswith((".", "!", "?")) else s + "."


def reply_text(rec: Recommendation) -> str:
    c = rec.conditions
    parts = [VERDICT[rec.mode]]
    if "traffic" in c.missing:
        parts.append("I couldn't check traffic.")
    elif c.incidents:
        i = min(c.incidents, key=lambda x: RANK[x.severity])
        parts.append(_sentence(f"On the road: {i.road}: {i.summary}"))
    else:
        parts.append("No reported traffic problems.")
    if "transit" in c.missing:
        parts.append("I couldn't check transit.")
    elif c.alerts:
        a = min(c.alerts, key=lambda x: RANK[x.severity])
        parts.append(_sentence(f"On transit: {a.line}: {a.summary}"))
    else:
        parts.append("Transit is running normally.")
    return _truncate(" ".join(parts))
