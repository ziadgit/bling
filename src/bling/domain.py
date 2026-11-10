"""Domain models."""

from typing import Literal

from pydantic import BaseModel

Severity = Literal["minor", "moderate", "severe"]


class TripRequest(BaseModel):
    destination: str
    origin: str | None = None
    arrive_by: str | None = None
    situation: str | None = None


class Incident(BaseModel):
    road: str
    summary: str
    severity: Severity


class TransitAlert(BaseModel):
    line: str
    summary: str
    severity: Severity


class Conditions(BaseModel):
    incidents: list[Incident] = []
    alerts: list[TransitAlert] = []
    sources: list[str] = []
    missing: list[str] = []
    exa_cost_usd: float = 0.0


class Recommendation(BaseModel):
    mode: Literal["drive", "transit", "either"] | None
    traffic_bad: float | None = None
    transit_disrupted: float | None = None
    conditions: Conditions
    trip: TripRequest
    text: str
