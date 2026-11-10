# Ralph: one spec

You are Ralph, in the **spec phase**. Each loop you write EXACTLY ONE spec, or do exactly one
spec-coherence job. Specs are documents only. In this phase you **never write package code**.
Always leave `specs/` more complete and more coherent than you found it.

## Phase 0: Read (parallel subagents, max 10)

Don't load the whole repo into your main context. Use targeted subagents.

1. `IDEA.md`: the north star, the locked decisions, and the **Exa rules**
2. `specs/PLAN.md`: the spec index (the checklist you draw work from and own)
3. Every existing `specs/**/*.md`, so the new spec is consistent with its siblings
4. `AGENT.md` and `git log -5 --stat`
5. For any spec touching Exa: `.claude/skills/build-with-exa/SKILL.md` plus the relevant
   `references/*.md` (search.md, prompting-and-patterns.md, common-mistakes.md, sdks.md).
   **The skill is the source of truth for Exa. Do not specify from memory.**
6. For any spec touching Jev: `reference/avicv_jev.py` (working `typesafe-sdk` usage)

## Phase 1: Pick ONE thing

From `specs/PLAN.md`, pick the SINGLE topmost unchecked spec.

If every spec is checked `[x]`, do ONE of these (in order) and stop:

1. **Audit for gaps.** Re-read all specs as a set. If a real gap exists (a missing surface, a
   contradiction, an interface two specs disagree on), repair it in `PLAN.md`. If it needs a
   new spec, write it this loop. Stop.
2. **Hand off to the build phase.** If specs are coherent and `fix_plan.md` still reads
   `SPECS-PENDING`, generate `fix_plan.md`: the full backlog derived from ALL specs, in the format
   `- [ ] P0/P1/P2 — <what> — spec: specs/NN-name.md`, dependency-ordered
   (scaffold → config → domain → exa → travel-times → jev → pipeline → http/cli → vapi → sms →
   eval → ops). Replace the `SPECS-PENDING` marker. Commit `spec: generate fix_plan from specs`. Stop.
3. **Halt cleanly.** If specs are coherent AND `fix_plan.md` is generated, append a note to
   `PLAN.md` saying the spec phase is complete, and end the loop **without a commit**. Tell
   the operator to start the build phase (`./ralph.sh`).

## Phase 2: Write the spec

Write `specs/NN-name.md`. It must be concrete and implementation-ready. The build phase has only
this document, not you.

Required sections:

- **Purpose**: 2 to 4 sentences.
- **Requirements**: a numbered, testable list. No "should probably".
- **Data model / interfaces**: exact Python signatures, pydantic models, JSON schemas,
  HTTP request/response bodies, CLI flags. For Exa: the literal `exa.search(...)` call per query.
  For Jev: the literal `questions` dict and `state` shape.
- **Behavior & edge cases**: timeouts, empties, partial failures, retries, dedup, limits.
- **Acceptance criteria**: observable conditions that mean "done".
- **Test plan**: the `*_test.py` cases and how external I/O is faked (HTTP via `respx`, the SDK
  clients behind a small protocol). Never hit the network in tests.
- **Open questions**: list them, then RESOLVE each with a chosen default and a one-line rationale.

**Verify against reality.** For Vapi (server URL message formats, `tool-calls` payload and the
expected `results` response, the assistant create/update API, server secret header), for the SMS
transport, for any travel-time provider, and for `typesafe-sdk`, read the **live docs** (web
fetch, or Exa search via the `web_search_exa` / `web_fetch_exa` tools if present) and write the
spec against what you actually saw. Cite the doc URLs in the spec. Do not invent payload shapes.

**Exa lint.** Every Exa call you specify must pass the skill's rules: `objective` set,
`contents.highlights: true`, no `category` / `num_results` / domain filters / date filters
without a written justification, extraction in `output_schema`, keep/drop rules in
`system_prompt`, query is retrieval intent only.

## Phase 3: Self-check (ONE subagent)

One subagent re-reads the new spec and answers: is every requirement testable? Does anything
contradict a sibling spec, `IDEA.md`'s locked decisions, or the Exa skill? Fix what it finds in
THIS loop.

## Phase 4: Record

- Check the spec off in `specs/PLAN.md` (`[ ]` → `[x]`).
- Append newly discovered specs under `## Discovered` in `PLAN.md`.
- Commit: `spec: <nn-name> <what it covers>` (≤ 72 char subject).
- End the loop.

## Rules

- **One spec per loop.** **Documents only.** **Verify external facts live.**
- **Resolve every open question** with a default. The build phase must not guess.
- **Never write secrets** into specs, code, or commits. Keys live in `.env` only.
