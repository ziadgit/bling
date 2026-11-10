# Build Bling in one session (27-minute time box)

You are running with `--dangerously-skip-permissions` in this repo. Build the whole app described
in `SPEC.md` by working through `fix_plan.md` top to bottom, in this one session, in
**27 minutes of wall-clock time**.

## Start

1. Run `date +%s > .build_start` (it's gitignored). That is t=0.
2. Read `SPEC.md` (the source of truth), `fix_plan.md`, `AGENT.md`, and
   `.claude/skills/build-with-exa/SKILL.md`. Read `reference/avicv_jev.py` before the Jev item.

## For each unchecked `- [ ]` item, in order

1. **Check the clock:** `echo $(( $(date +%s) - $(cat .build_start) ))`. If 25 minutes (1500 s)
   or more have passed, go to "Finish" now.
2. **Implement the item fully.** No `TODO`s, no stubs. Tests sit beside the code (`foo.py` →
   `foo_test.py`).
3. **Verify:** `.venv/bin/ruff check . --fix && .venv/bin/ruff check . && .venv/bin/pytest -x -q`.
   Fix any failure before moving on.
4. **Record:** check the item off (`[ ]` → `[x]`), add any gotcha to the bottom of `AGENT.md`,
   then `git add -A && git commit -m "<scope>: <what>"`.

## Rules

- Be fast and decisive. Don't explore beyond what the item needs. SPEC.md decisions are final.
  If something is impossible as written, make the smallest change and note it in `AGENT.md`.
- To learn an SDK's real attribute names, inspect the installed package in `.venv` instead of guessing.
- **No live network calls to Exa, TypeSafe, Deepgram or Vapi**, even though keys may be in
  `.env`. Tests use respx and fakes. (Installing packages with `uv sync` is fine.)
- Never print, log or commit secrets. Never read `.env` values into your output.
- Stay inside this repo.

## Finish

Make sure the last commit has passing tests. Then print: the minutes elapsed, the items done
and still pending, and any `## Discovered` follow-ups. Stop.
