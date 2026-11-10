# AGENT.md

## Project

**Bling**: a phone/SMS assistant. Tell it where you're going, and it says whether to drive or
take public transit. Vapi handles voice. Exa `/search` pulls live traffic and transit conditions.
Jev (TypeSafe) makes the decision. See `IDEA.md` for the locked vision and `specs/` for the
source of truth.

## Stack

- **Language:** Python 3.11+, managed with **uv**. `src/bling/`, hatchling, PEP 735 dev group.
- **HTTP server:** FastAPI + uvicorn (Vapi server-URL webhook, SMS webhook, health).
- **Web retrieval:** `exa-py` (latest). Guidance: `.claude/skills/build-with-exa/` (vendored,
  MIT, upstream commit in `UPSTREAM_COMMIT`).
- **Decision model:** `typesafe-sdk` (`AsyncTypeSafeClient(api_key=..., model=...)`,
  `await client.system_one(state=..., questions=...)`, then `response.choices[k].choice`,
  `response.nouls[k].noul`, `response.scores[k].score`, `response.usage.input_tokens`).
  Working example: `reference/avicv_jev.py`.
- **Voice:** Vapi REST API + server URL webhooks (called with `httpx`).
- **CLI:** `typer`, a single `bling` entry point. **Config:** `pydantic-settings` + `.env`.
- **Storage:** SQLite (stdlib `sqlite3`) under `data/` for caller profiles.
- **Test/lint/types:** `pytest`, `pytest-asyncio`, `respx`, `ruff`, `mypy --strict`.

## Bootstrap (if dependencies are missing)

```sh
uv sync
```

If `pyproject.toml` does not exist yet, the first P0 item scaffolds it (spec 01).

## Environment (`.env`, gitignored; template in `.env.example`)

`EXA_API_KEY`, `TYPESAFE_API_KEY`, `VAPI_API_KEY`, `VAPI_SERVER_SECRET`, plus SMS-provider keys
once spec 08 picks one. Settings fields use `SecretStr`. Missing keys fail at the call site with a
clear message, not at import.

## Commands

| Purpose      | Command                                   |
| ------------ | ----------------------------------------- |
| ask locally  | `.venv/bin/bling ask "to Union Station by 6pm"` |
| serve        | `.venv/bin/bling serve`                   |
| sync Vapi    | `.venv/bin/bling vapi sync`               |
| lint         | `.venv/bin/ruff check .`                  |
| typecheck    | `.venv/bin/mypy src/bling`                |
| test         | `.venv/bin/pytest -x -q`                  |
| build sanity | `.venv/bin/python -c "import bling"`      |

## Gotchas

- Exa `search()` in `exa-py` uses snake_case kwargs (`output_schema`, `system_prompt`,
  `max_age_hours`). camelCase top-level kwargs raise `TypeError`.
- Exa `/search` content options live inside `contents={...}`. `lite` rejects `output_schema`
  and `max_age_hours`, so don't use `lite` for the conditions searches.
- Python `exa.search()` returns 10k-char text by default unless `contents` is passed. Always
  pass `contents={"highlights": True}`.
- Jev answers about ONE state per request. Put trip + conditions + rider in one state. Ask all
  the questions in that one call (extra questions are nearly free).
- Vapi tool-call responses must echo the `toolCallId` exactly (see spec 07).
