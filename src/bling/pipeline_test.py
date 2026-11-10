import asyncio

from bling.config import Settings
from bling.decision_test import FakeJev
from bling.domain import Conditions, Incident, Recommendation, TransitAlert, TripRequest
from bling.pipeline import plan_trip, reply_text

TRIP = TripRequest(destination="SFO")


def rec(mode="drive", **kw):
    return Recommendation(mode=mode, conditions=Conditions(**kw), trip=TRIP, text="")


def test_reply_text_variants():
    assert reply_text(rec()) == "Drive. No reported traffic problems. Transit is running normally."
    r = rec(
        "transit",
        incidents=[Incident(road="A", summary="slow", severity="minor"),
                   Incident(road="US-101", summary="crash blocking two lanes", severity="severe")],
        alerts=[TransitAlert(line="BART", summary="delays", severity="moderate")],
    )
    assert reply_text(r) == (
        "Take transit. On the road: US-101: crash blocking two lanes. On transit: BART: delays."
    )
    r = rec(None, missing=["traffic", "transit"])
    assert reply_text(r) == (
        "I couldn't make the call right now. I couldn't check traffic. I couldn't check transit."
    )
    assert reply_text(rec("either")).startswith("Either works.")


def test_reply_text_truncates_at_word():
    r = rec(incidents=[Incident(road="I-80", summary="word " * 100, severity="severe")])
    t = reply_text(r)
    assert len(t) <= 320 and t.endswith("…") and "http" not in t
    assert t[:-1].endswith("word")


async def test_plan_trip_without_exa():
    r = await plan_trip(TRIP, exa=None, jev=FakeJev("drive"), settings=Settings())
    assert r.mode == "drive" and r.conditions.missing == ["traffic", "transit"]
    assert "I couldn't check traffic" in r.text


async def test_plan_trip_deadline():
    class SlowExa:
        async def search(self, query, **kw):
            await asyncio.sleep(10)

    s = Settings(plan_deadline_s=0.05)
    r = await plan_trip(TRIP, exa=SlowExa(), jev=FakeJev(), settings=s)
    assert r.mode is None
