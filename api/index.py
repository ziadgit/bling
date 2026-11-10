"""Vercel entrypoint: every route is rewritten here (see vercel.json)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from bling.app import create_app  # noqa: E402

app = create_app()
