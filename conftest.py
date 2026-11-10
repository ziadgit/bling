import pytest

from bling.config import Settings


@pytest.fixture(autouse=True)
def _isolate(monkeypatch, tmp_path):
    for name in Settings.model_fields:
        monkeypatch.delenv(name.upper(), raising=False)
        monkeypatch.delenv(name, raising=False)
    monkeypatch.chdir(tmp_path)
