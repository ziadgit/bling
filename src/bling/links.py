"""Voice-link tokens stored as one JSON file each."""

import json
import re
import secrets
import time
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ValidationError

from .domain import Recommendation, TripRequest

TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{16,32}$")


class LinkRecord(BaseModel):
    kind: Literal["review", "explain"]
    created: float
    trip: TripRequest
    rec: Recommendation | None = None
    used: bool = False


class LinkStore:
    def __init__(self, dir: Path, ttl_hours: int):
        self.dir = Path(dir)
        self.ttl_s = ttl_hours * 3600

    def _path(self, token: str, suffix: str = ".json") -> Path | None:
        if not isinstance(token, str) or not TOKEN_RE.match(token):
            return None
        return self.dir / f"{token}{suffix}"

    def create(
        self, kind: str, trip: TripRequest, rec: Recommendation | None = None
    ) -> str:
        token = secrets.token_urlsafe(16)
        record = LinkRecord(kind=kind, created=time.time(), trip=trip, rec=rec)
        self.save(token, record)
        return token

    def save(self, token: str, record: LinkRecord) -> None:
        path = self._path(token)
        if path is None:
            raise ValueError("bad token")
        self.dir.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(record.model_dump_json())
        tmp.replace(path)

    def get(self, token: str) -> LinkRecord | None:
        path = self._path(token)
        if path is None or not path.is_file():
            return None
        try:
            data: Any = json.loads(path.read_text())
            record = LinkRecord.model_validate(data)
        except (ValueError, ValidationError, OSError):
            return None
        if time.time() - record.created > self.ttl_s:
            return None
        return record

    def audio_path(self, token: str) -> Path | None:
        return self._path(token, ".mp3")
