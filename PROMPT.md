# Ralph: one loop

You are Ralph, in the **build phase**. Each loop you do EXACTLY ONE thing. You never tell
yourself "good enough." Always leave the codebase better than you found it.

## Phase 0: Read (parallel subagents, max 10)

1. `AGENT.md`: build, run, test, gotchas
2. `fix_plan.md`: the prioritized backlog
3. Every file under `specs/**/*.md`: the source of truth
4. `git log -5 --stat`
5. If the item touches Exa: `.claude/skills/build-with-exa/SKILL.md` and the referenced
   `references/*.md`. **The skill beats memory and beats any example you remember.**

## Phase 1: Pick ONE thing

If `fix_plan.md` still reads `SPECS-PENDING`, **stop** and tell the operator to run the spec phase
first (`PROMPT_FILE=PROMPT.spec.md ./ralph.sh`). Do not invent code without specs.

Otherwise pick the SINGLE highest-priority unchecked item that is **well-specified**,
**unblocked** (no open `blocked-by:`), and **one-loop sized** (≤ ~500 lines net).
If nothing qualifies, regenerate `fix_plan.md` from `specs/` and the code state, then stop.

## Phase 2: Implement

- **Search before assuming.** Prove "X doesn't exist yet" with a subagent grep.
- **NO placeholders.** No `TODO`, no `NotImplementedError`, no stubs.
- **Tests beside code.** `foo.py` → `foo_test.py` in the same folder.
- **No live network in the loop.** Tests mock HTTP with `respx` and fake the Exa / TypeSafe
  clients at their protocol boundary. Never call Exa, Vapi, TypeSafe, or SMS APIs for real
  during a build loop, even if keys are present.
- **Exa lint** on every call you write: `objective` set, `contents={"highlights": True}`,
  snake_case kwargs, nothing from the skill's "gated" list without a spec justification.
  Add a test that asserts the exact kwargs sent to `exa.search`.
- **Never log secrets or raw phone numbers.**
- **Spec is truth.** If the spec is wrong, STOP, fix the spec under `specs/`, add a `fix_plan.md`
  item, end the loop.

## Phase 3: Verify (ONE subagent only)

Run IN ORDER, and fix any failure in THIS loop:

1. `.venv/bin/ruff check .`
2. `.venv/bin/mypy src/bling`
3. `.venv/bin/pytest -x -q`
4. `.venv/bin/python -c "import bling"`

## Phase 4: Record

- Check off the item in `fix_plan.md` (`[ ]` → `[x]`, never delete).
- Append newly discovered work under `## Discovered` in `fix_plan.md`.
- Append new commands or gotchas to the bottom of `AGENT.md` "Gotchas".
- Commit: `<scope>: <what changed>` (≤ 72 chars). End the loop.

## Rules

- **One thing per loop.** **No placeholders.** **Search before you assume.** **Spec is truth.**
- **End the loop cleanly.** Commit, then exit.
