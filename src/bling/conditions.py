# ruff: noqa: E501 - the Exa prompts are literal spec text
"""Live traffic and transit conditions from two concurrent Exa searches."""

import asyncio
import json
import logging
from typing import Any

from pydantic import ValidationError

from .config import Settings
from .domain import Conditions, Incident, TransitAlert, TripRequest

log = logging.getLogger(__name__)

_SEVERITY = {"type": "string", "enum": ["minor", "moderate", "severe"]}


def _schema(key: str, name: str) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            key: {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        name: {"type": "string"},
                        "summary": {"type": "string"},
                        "severity": _SEVERITY,
                    },
                    "required": [name, "summary", "severity"],
                },
            }
        },
        "required": [key],
    }


TRAFFIC_SCHEMA = _schema("incidents", "road")
TRANSIT_SCHEMA = _schema("alerts", "line")
CONTENTS = {"highlights": True, "max_age_hours": 1, "livecrawl_timeout": 3000}


def search_calls(trip: TripRequest, settings: Settings) -> dict[str, tuple[str, dict[str, Any]]]:
    """The exact (query, kwargs) for each search, keyed by "traffic"/"transit"."""
    d, r = trip.destination, settings.bling_region
    o = trip.origin or r
    traffic = (
        f"traffic crashes, road closures and congestion right now between {o} and {d}, {r}",
        {
            "type": "auto",
            "objective": (
                f"Find today's traffic incident and closure reports that would slow a drive from {o} "
                f"to {d}. Rank official DOT/511 alerts and local news traffic reports first; exclude "
                "old articles, generic directions pages and forecasts. Pull the road, what happened, "
                "and how severe it is."
            ),
            "system_prompt": (
                "Include only incidents reported today that plausibly affect this drive. Never "
                "invent incidents; return an empty list when none are reported."
            ),
            "output_schema": TRAFFIC_SCHEMA,
            "contents": dict(CONTENTS),
        },
    )
    transit = (
        f"public transit service alerts and delays right now for trips to {d}, {r}",
        {
            "type": "auto",
            "objective": (
                f"Find today's service alerts, delays, suspensions and planned work on the public "
                f"transit lines a rider would take from {o} to {d}. Rank the transit agency's own "
                "alert pages first; exclude old news and schedules without alerts. Pull the line, "
                "what is wrong, and how severe it is."
            ),
            "system_prompt": (
                "Include only alerts in effect today that plausibly affect this trip. Never "
                "invent alerts; return an empty list when service is normal."
            ),
            "output_schema": TRANSIT_SCHEMA,
            "contents": dict(CONTENTS),
        },
    )
    return {"traffic": traffic, "transit": transit}


def _content(response: Any) -> dict[str, Any]:
    output = getattr(response, "output", None)
    content = getattr(output, "content", None) if output is not None else None
    if isinstance(content, str):
        try:
            content = json.loads(content)
        except ValueError:
            return {}
    return content if isinstance(content, dict) else {}


def _items(raw: Any, model: type) -> list:
    out = []
    for item in raw if isinstance(raw, list) else []:
        try:
            out.append(model.model_validate(item))
        except ValidationError:
            continue
    return out


def _cost(response: Any) -> float:
    cost = getattr(response, "cost_dollars", None)
    total = getattr(cost, "total", None) if cost is not None else None
    return float(total) if isinstance(total, int | float) else 0.0


def _urls(response: Any) -> list[str]:
    return [u for r in getattr(response, "results", None) or [] if (u := getattr(r, "url", None))]


async def fetch_conditions(trip: TripRequest, exa: Any, settings: Settings) -> Conditions:
    calls = search_calls(trip, settings)

    async def one(query: str, kwargs: dict[str, Any]) -> Any:
        async with asyncio.timeout(settings.exa_timeout_s):
            return await exa.search(query, **kwargs)

    traffic, transit = await asyncio.gather(
        one(*calls["traffic"]), one(*calls["transit"]), return_exceptions=True
    )
    cond = Conditions()
    for name, resp, key, model in (
        ("traffic", traffic, "incidents", Incident),
        ("transit", transit, "alerts", TransitAlert),
    ):
        if isinstance(resp, BaseException):
            log.warning("exa %s search failed: %s", name, type(resp).__name__)
            cond.missing.append(name)
            continue
        items = _items(_content(resp).get(key), model)
        if key == "incidents":
            cond.incidents = items
        else:
            cond.alerts = items
        cond.sources.extend(_urls(resp))
        cond.exa_cost_usd += _cost(resp)
    return cond
