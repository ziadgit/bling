# AGENT.md

## Project

**Bling**: text or call where you're going, and it says drive or take transit. Exa `/search`
provides live conditions, Jev (TypeSafe) decides, Vapi runs the phone call, and Deepgram does
the call's transcription and voice inside Vapi (plus CLI testing with --audio/--say). `SPEC.md` is the source
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
| ask | `.venv/bin/bling ask "Salesforce Transit Center" --from "Oakland" --by 6pm` |
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
- Exa/Jev prompt literals exceed 100 chars; those modules carry a file-level `# ruff: noqa: E501`.
- `decision.decide` imports `pipeline.reply_text` lazily (and vice versa) to avoid an import cycle.
- `plan_deadline_s` timeout yields `mode=None` with both searches marked `missing`.
- Revision 2 removed the link flow: `Deps` is just settings + exa + jev, and the app has only
  `/vapi/webhook` and `/healthz` (app_test asserts the route set).
- `vapi.mask_secrets` masks the `apiKey` and `x-bling-secret` keys (used by `vapi-sync --dry-run`).
  `VapiApi` errors include Vapi's `message`, with the API key and any body secrets scrubbed out,
  because Vapi validation messages can quote the values they reject.
- Deepgram keyterms go as repeated `keyterm=` query params (httpx `params` as a list of tuples).
- typer `Path` options trip ruff B008; `typer.Option`/`typer.Argument` are listed under
  `[tool.ruff.lint.flake8-bugbear] extend-immutable-calls`.
- `bling ask --audio` checks for `DEEPGRAM_API_KEY` before running anything, and transcribes
  before it builds the Exa/Jev clients, so the `heard:` line prints first.
- Vercel: `api/index.py` is the entrypoint (it puts `src/` on `sys.path`). Vercel detects FastAPI
  and routes every path to the app itself, so don't add a catch-all rewrite (it would turn every
  path into `/api/index`). Vercel has no Python 3.11, so `.python-version` is listed in
  `.vercelignore` and Vercel uses 3.12. Clients are also built lazily on the first webhook call,
  because the serverless runtime may skip the lifespan.
