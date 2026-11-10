# ruff: noqa: E501
import asyncio
import json
from types import SimpleNamespace as NS

from bling.conditions import CONTENTS, TRAFFIC_SCHEMA, TRANSIT_SCHEMA, fetch_conditions
from bling.config import Settings
from bling.domain import TripRequest


def resp(content, urls=(), cost=None):
    return NS(
        output=NS(content=content),
        results=[NS(url=u) for u in urls],
        cost_dollars=NS(total=cost) if cost is not None else None,
    )


class FakeExa:
    def __init__(self, traffic=None, transit=None):
        self.calls = []
        self.answers = {"traffic": traffic, "transit": transit}

    async def search(self, query, **kwargs):
        self.calls.append((query, kwargs))
        key = "traffic" if query.startswith("traffic") else "transit"
        ans = self.answers[key]
        if isinstance(ans, BaseException):
            raise ans
        if ans == "slow":
            await asyncio.sleep(10)
        return ans


TRIP = TripRequest(destination="SFO", origin="Oakland", situation="secret context")


async def test_exact_kwargs_and_parsing():
    exa = FakeExa(
        traffic=resp(
            {"incidents": [{"road": "I-880", "summary": "crash", "severity": "severe"},
                           {"road": "bad", "severity": "nope"}]},
            urls=["https://511.org/a"], cost=0.01,
        ),
        transit=resp(json.dumps({"alerts": [{"line": "BART", "summary": "delay",
                                             "severity": "minor"}]}),
                     urls=["https://bart.gov"], cost=0.02),
    )
    c = await fetch_conditions(TRIP, exa, Settings())
    assert [i.road for i in c.incidents] == ["I-880"]
    assert [a.line for a in c.alerts] == ["BART"]
    assert c.sources == ["https://511.org/a", "https://bart.gov"]
    assert abs(c.exa_cost_usd - 0.03) < 1e-9
    assert c.missing == []
    r = "San Francisco Bay Area, CA"
    (q1, k1), (q2, k2) = exa.calls
    assert q1 == f"traffic crashes, road closures and congestion right now between Oakland and SFO, {r}"
    assert q2 == f"public transit service alerts and delays right now for trips to SFO, {r}"
    assert set(k1) == {"type", "objective", "system_prompt", "output_schema", "contents"}
    assert k1["type"] == "auto" and k1["output_schema"] == TRAFFIC_SCHEMA
    assert k2["output_schema"] == TRANSIT_SCHEMA
    assert k1["contents"] == CONTENTS == {"highlights": True, "max_age_hours": 1,
                                          "livecrawl_timeout": 3000}
    assert k1["objective"].startswith("Find today's traffic incident and closure reports that "
                                      "would slow a drive from Oakland to SFO.")
    assert "transit lines a rider would take from Oakland to SFO" in k2["objective"]
    assert "secret context" not in q1 + q2 + json.dumps([k1, k2])
    assert TRANSIT_SCHEMA["properties"]["alerts"]["items"]["required"] == [
        "line", "summary", "severity"]


async def test_origin_defaults_to_region():
    exa = FakeExa(resp({"incidents": []}), resp({"alerts": []}))
    await fetch_conditions(TripRequest(destination="SFO"), exa, Settings())
    assert "between San Francisco Bay Area, CA and SFO" in exa.calls[0][0]


async def test_failure_and_timeout_mark_missing():
    exa = FakeExa(traffic=RuntimeError("boom"), transit="slow")
    c = await fetch_conditions(TRIP, exa, Settings(exa_timeout_s=0.05))
    assert c.missing == ["traffic", "transit"]
    assert c.incidents == [] and c.alerts == []


async def test_bad_content_yields_empty():
    exa = FakeExa(resp("not json"), NS(output=None, results=None, cost_dollars=None))
    c = await fetch_conditions(TRIP, exa, Settings())
    assert c.incidents == [] and c.alerts == [] and c.missing == []
