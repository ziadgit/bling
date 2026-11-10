# ruff: noqa: E501 - the Jev questions are literal spec text
"""Drive-or-transit decision with Jev (TypeSafe). Code never picks a verdict."""

import asyncio
import logging
from typing import Any

from typesafe_sdk import AsyncTypeSafeClient, Choice, Noul, NoulCriteria, RetryPolicy

from .config import Settings, require
from .domain import Conditions, Recommendation, TripRequest

log = logging.getLogger(__name__)

QUESTIONS = {
    "mode": Choice(
        instructions="Given `trip`, the current `conditions`, and the rider's `situation` (if any), "
        "should the rider drive or take public transit for this trip?",
        criteria={
            "drive": "Driving is clearly the better choice: transit is disrupted, impractical for this "
            "trip, or the rider's situation needs a car, and roads are reasonably clear.",
            "transit": "Transit is clearly the better choice: roads have significant incidents or "
            "congestion, or parking/cost/the rider's situation favor transit, and service is running.",
            "either": "Neither option is clearly better given what is known.",
        },
    ),
    "traffic_bad": Noul(
        instructions="Do `conditions` report traffic problems likely to delay a drive on this trip?",
        criteria=NoulCriteria(
            true="A reported incident, closure or heavy congestion affects the likely route.",
            false="No reported problem affects the likely driving route.",
        ),
    ),
    "transit_disrupted": Noul(
        instructions="Do `conditions` report transit problems likely to delay this trip?",
        criteria=NoulCriteria(
            true="A reported alert, delay or suspension affects the likely transit lines.",
            false="No reported problem affects the likely transit lines.",
        ),
    ),
}

MODES = {"drive", "transit", "either"}


def make_jev(settings: Settings) -> AsyncTypeSafeClient:
    return AsyncTypeSafeClient(
        api_key=require(settings.typesafe_api_key, "TYPESAFE_API_KEY"),
        model=settings.jev_model,
        retry=RetryPolicy(max_retries=0),
        timeout=settings.jev_timeout_s,
    )


def build_state(trip: TripRequest, conditions: Conditions) -> dict[str, Any]:
    return {
        "trip": {
            "destination": trip.destination,
            "origin": trip.origin,
            "arrive_by": trip.arrive_by,
        },
        "situation": trip.situation or "none given",
        "conditions": {
            "incidents": [i.model_dump() for i in conditions.incidents],
            "alerts": [a.model_dump() for a in conditions.alerts],
            "searches_failed": list(conditions.missing),
            "note": "Empty lists mean nothing was reported.",
        },
    }


async def decide(
    trip: TripRequest, conditions: Conditions, jev: Any, settings: Settings
) -> Recommendation:
    from .pipeline import reply_text

    mode = traffic_bad = transit_disrupted = None
    if jev is not None:
        try:
            async with asyncio.timeout(settings.jev_timeout_s):
                response = await jev.system_one(
                    state=build_state(trip, conditions), questions=QUESTIONS
                )
            choice = response.choices["mode"].choice
            mode = choice if choice in MODES else None
            traffic_bad = float(response.nouls["traffic_bad"].noul)
            transit_disrupted = float(response.nouls["transit_disrupted"].noul)
        except Exception as e:  # noqa: BLE001 - no verdict rather than a crash
            log.warning("jev failed: %s", type(e).__name__)
            mode = traffic_bad = transit_disrupted = None
    log.info("decision mode=%s missing=%s", mode, conditions.missing)
    rec = Recommendation(
        mode=mode,
        traffic_bad=traffic_bad,
        transit_disrupted=transit_disrupted,
        conditions=conditions,
        trip=trip,
        text="",
    )
    rec.text = reply_text(rec)
    return rec
