import pytest
from pydantic import ValidationError

from bling.domain import Conditions, Incident, Recommendation, TripRequest


def test_models():
    trip = TripRequest(destination="X")
    rec = Recommendation(mode=None, conditions=Conditions(), trip=trip, text="t")
    assert rec.conditions.missing == []
    with pytest.raises(ValidationError):
        Incident(road="r", summary="s", severity="awful")
