import asyncio
from types import SimpleNamespace as NS

from bling.config import Settings
from bling.decision import QUESTIONS, decide
from bling.domain import Conditions, Incident, TripRequest


class FakeJev:
    def __init__(self, mode="transit", fail=None, delay=0.0):
        self.mode, self.fail, self.delay, self.calls = mode, fail, delay, []

    async def system_one(self, *, state, questions):
        self.calls.append((state, questions))
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.fail:
            raise self.fail
        return NS(
            choices={"mode": NS(choice=self.mode)},
            nouls={"traffic_bad": NS(noul=0.9), "transit_disrupted": NS(noul=0.1)},
        )


TRIP = TripRequest(destination="SFO", origin="Oakland", arrive_by="6pm")
COND = Conditions(
    incidents=[Incident(road="I-880", summary="crash", severity="severe")], missing=["transit"]
)


async def test_maps_response_and_state():
    jev = FakeJev()
    rec = await decide(TRIP, COND, jev, Settings())
    assert rec.mode == "transit" and rec.traffic_bad == 0.9 and rec.transit_disrupted == 0.1
    assert rec.text.startswith("Take transit.")
    state, questions = jev.calls[0]
    assert questions is QUESTIONS and set(questions) == {"mode", "traffic_bad", "transit_disrupted"}
    assert state["trip"] == {"destination": "SFO", "origin": "Oakland", "arrive_by": "6pm"}
    assert state["situation"] == "none given"
    assert state["conditions"]["searches_failed"] == ["transit"]
    assert state["conditions"]["incidents"][0]["road"] == "I-880"
    assert state["conditions"]["note"] == "Empty lists mean nothing was reported."


async def test_no_verdict_fallbacks():
    for jev, s in (
        (None, Settings()),
        (FakeJev(fail=RuntimeError("x")), Settings()),
        (FakeJev(delay=1), Settings(jev_timeout_s=0.05)),
        (FakeJev(mode="bike"), Settings()),
    ):
        rec = await decide(TRIP, COND, jev, s)
        assert rec.mode is None
        assert rec.text.startswith("I couldn't make the call right now.")
