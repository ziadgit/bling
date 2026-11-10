import time

from bling.domain import Conditions, Recommendation, TripRequest
from bling.links import LinkStore

TRIP = TripRequest(destination="SFO")


def test_roundtrip(tmp_path):
    store = LinkStore(tmp_path / "links", 24)
    rec = Recommendation(mode="drive", conditions=Conditions(), trip=TRIP, text="Drive.")
    tok = store.create("review", TRIP, rec)
    assert (tmp_path / "links" / f"{tok}.json").is_file()
    got = store.get(tok)
    assert got.kind == "review" and got.rec.text == "Drive." and got.used is False
    assert store.audio_path(tok) == tmp_path / "links" / f"{tok}.mp3"


def test_bad_tokens(tmp_path):
    store = LinkStore(tmp_path, 24)
    (tmp_path / "secret.json").write_text("{}")
    for tok in ("../../etc/passwd", "short", "a" * 40, "", "../secret" + "x" * 10):
        assert store.get(tok) is None
        assert store.audio_path(tok) is None
    (tmp_path / ("m" * 20 + ".json")).write_text("not json")
    assert store.get("m" * 20) is None
    assert store.get("u" * 20) is None


def test_expired(tmp_path):
    store = LinkStore(tmp_path, 1)
    tok = store.create("explain", TRIP)
    rec = store.get(tok)
    rec.created = time.time() - 7200
    store.save(tok, rec)
    assert store.get(tok) is None
