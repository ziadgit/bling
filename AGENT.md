# AGENT.md

## Project

**Bling**: text or call where you're going, and it says drive or take transit. Exa `/search`
provides live conditions, Jev (TypeSafe) decides, Vapi runs voice and SMS chat, and Deepgram does
the voice links (TTS review page, record-and-transcribe explain page). `SPEC.md` is the source
of truth. `fix_plan.md` is the backlog.

## Bootstrap

```sh
uv sync     # creates .venv with the runtime deps + the dev group
```

## Commands

| Purpose | Command |
|---|---|
| lint | `.venv/bin/ruff check .` |
| test | `.venv/bin/pytest -x -q` |
| ask | `.venv/bin/bling ask "Union Station" --by 6pm` |
| serve | `.venv/bin/bling serve` |
| sync Vapi | `.venv/bin/bling vapi-sync` |

## Gotchas

- exa-py uses snake_case kwargs (`output_schema`, `system_prompt`); nested `contents` keys are
  snake_case too (`max_age_hours`, `livecrawl_timeout`). Always pass `contents`, or Python
  `search()` returns 10k-char text by default.
- The Exa skill lives at `.claude/skills/build-with-exa/`. It beats memory.
- `typesafe-sdk` 0.7.x uses `httpx2`, not httpx, so respx can't intercept it. Fake Jev at the
  object boundary (any object with `async system_one(*, state, questions)`).
- `typesafe-sdk` default retries (2, up to 5 s backoff) blow the voice budget. Construct it with
  `retry=RetryPolicy(max_retries=0)` and `timeout=settings.jev_timeout_s`.
- Vapi tool results must echo `toolCallId` exactly and be flat strings.
