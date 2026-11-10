import pytest
from pydantic import SecretStr

from bling.config import Settings, require


def test_defaults():
    s = Settings()
    assert s.exa_api_key is None
    assert s.jev_model == "jev-1.13.0"
    assert s.bling_region == "San Francisco Bay Area, CA"
    assert s.plan_deadline_s == 8.0
    assert s.vapi_voice_id == "asteria"
    assert not hasattr(s, "link_ttl_hours")


def test_env_and_dotenv(monkeypatch, tmp_path):
    (tmp_path / ".env").write_text("EXA_API_KEY=abc\nBLING_REGION=\n")
    monkeypatch.setenv("JEV_TIMEOUT_S", "1.5")
    s = Settings()
    assert require(s.exa_api_key, "EXA_API_KEY") == "abc"
    assert s.bling_region == "San Francisco Bay Area, CA"  # empty ignored
    assert s.jev_timeout_s == 1.5


def test_require():
    assert require(SecretStr("x"), "K") == "x"
    with pytest.raises(RuntimeError, match="K is not set"):
        require(None, "K")
