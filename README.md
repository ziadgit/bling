# Bling

Call or text Bling where you're going. It checks live traffic and transit conditions with
**Exa**, lets **Jev** decide, and tells you whether to **drive** or **take transit**, and why.
Voice runs on **Vapi**.

This repo is a **Ralph seed**: the app is written by an autonomous loop from `IDEA.md`.

## Setup

```sh
cp .env.example .env      # then fill in EXA_API_KEY, TYPESAFE_API_KEY, VAPI_* keys
```

## Build it

```sh
# 1. Spec phase: writes specs/NN-*.md one per loop, then generates fix_plan.md
PROMPT_FILE=PROMPT.spec.md MAX_ITERATIONS=14 ./ralph.sh

# 2. Build phase: drains fix_plan.md one item per loop
MAX_ITERATIONS=10 ./ralph.sh
```

`ralph.sh` runs `claude --print --dangerously-skip-permissions`, so the agent acts with no
confirmation. Ctrl-C stops it. `MAX_ITERATIONS=0` means unlimited.

## Layout

- `IDEA.md`: locked vision, decisions, Exa rules, constraints
- `specs/`: source of truth (`PLAN.md` is the index)
- `PROMPT.spec.md` / `PROMPT.md`: spec-phase and build-phase loop prompts
- `fix_plan.md`: build backlog
- `AGENT.md`: stack, commands, gotchas
- `.claude/skills/build-with-exa/`: Exa's official skill (MIT), auto-loaded by Claude Code
- `reference/avicv_jev.py`: working Jev / `typesafe-sdk` usage from avicv
