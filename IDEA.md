# Bling: call or text it where you're going, and it tells you to drive or take transit

## North star
You call a phone number (or text it) and say where you're headed, like *"I need to be at
Union Station by 6."* Bling checks what's happening right now on the live web (traffic
incidents, road closures, transit service alerts and delays, big events, severe weather),
lets **Jev** make the call, and answers in one or two spoken sentences: **drive** or
**take transit**, plus the reason. Example: *"Take the train. There's a crash closing two
lanes on I-90 and the Red Line is running normally."*

## Locked decisions (do not relitigate)
- **Language:** Python 3.11+, uv, `src/` layout (`src/bling/`), hatchling, pydantic-settings.
- **Voice:** **Vapi**. A Vapi assistant answers the phone. Its LLM calls Bling's tools through
  Vapi's **server URL** webhook (`tool-calls` messages). Bling is the webhook server (FastAPI).
- **Text:** inbound SMS runs the same pipeline and replies by text. The spec phase picks the SMS
  transport (Vapi's own SMS/chat support if it handles inbound SMS on the same number,
  otherwise a Twilio Messaging webhook), **after verifying against live docs**.
- **Live conditions:** **Exa** `/search`. This is the only web-retrieval surface. Follow
  `.claude/skills/build-with-exa/` exactly (see "Exa rules" below).
- **Decision:** **Jev** (TypeSafe's decision model, `typesafe-sdk`, `AsyncTypeSafeClient.system_one`).
  Jev answers typed questions (`Choice`, `Noul`, `Score`) about one `state` dict. The final
  drive/transit verdict is a Jev `Choice`, not an LLM's free-text opinion. Reference
  implementation from a sibling app: `reference/avicv_jev.py`.
- **Interfaces:** FastAPI app (`/vapi/webhook`, SMS webhook, `/healthz`) plus a `bling` typer CLI
  (`bling ask "..."` for local runs, `bling serve`, `bling vapi sync` to create/update the
  assistant from code).

## Pipeline
```
caller voice ─▶ Vapi assistant (LLM) ──tool-call: plan_trip(destination, arrive_by?, origin?)──┐
caller SMS  ─▶ SMS webhook ──parse──────────────────────────────────────────────────────────────┤
                                                                                                 ▼
                    TripRequest (origin from caller profile or the request, destination, time)
                                                                                                 │
             ┌──────────── parallel, hard time budget ────────────┐                              │
             ▼                         ▼                          ▼                              │
     Exa: road/traffic        Exa: transit service        (optional) travel-time                 │
     incidents on route       alerts for the lines/city    estimates (spec 04)                   │
             └──────────────── Conditions ─────────────────┘                                     │
                                       ▼                                                         │
                     Jev.system_one(state={trip, conditions, rider}, questions)                  │
                                       ▼                                                         │
                     Recommendation(mode: drive|transit|either, reasons, sources)  ◀────────────┘
                                       ▼
                     spoken / texted reply (≤ 2 sentences, ≤ 320 chars for SMS)
```

## Exa rules (from the vendored build-with-exa skill, non-negotiable)
- Endpoint: `/search` via `exa-py` (`exa.search(...)`, snake_case kwargs).
- Every Bling search is one step of a larger task, so **every call sends `objective`**
  (which documents rank first, which to exclude, what facts to pull).
- `contents={"highlights": True}` on every call. Never stack `text`/`summary`.
- Extracted fields (incident location, severity, affected lines, delay minutes) go in a
  **compact `output_schema`** (one array of flat objects, at most five fields). Keep/drop rules
  go in `system_prompt`. Stay on `type="auto"` because the schema is compact.
- Recency goes **in the query text** ("right now", "today"). The content must be current, so
  `contents.max_age_hours` is justified. The spec phase sets it (default: 1) with a
  `livecrawl_timeout`.
- **Do not** set `category`, `num_results`, `include_domains`/`exclude_domains`, or date filters
  unless a spec explicitly justifies it against the skill's rules.
- If the Vapi LLM also gets a general `web_search` tool for follow-ups, it must take
  **`query` + `objective` (required)**, with the skill's verbatim `objective` description, and
  the tool description must say "search the live web". The spec phase decides whether to
  include it (default: yes).
- `EXA_API_KEY` is read from the environment / `.env` via pydantic-settings.

## Hard constraints
- **Voice latency:** the `plan_trip` tool must return within **8 s** p95. Exa and routing calls
  run concurrently with timeouts. On timeout, decide with what arrived and say so.
- **Never fabricate conditions.** If Exa returns nothing relevant, the state says
  "no reported incidents found", and Jev decides on that.
- **Webhook security:** verify Vapi's server secret and the SMS provider's signature. Reject
  anything unsigned.
- **Privacy:** phone numbers and saved home addresses are stored locally (SQLite under `data/`),
  are never logged in plain text (hash or mask them), and are never sent to Exa. Queries name
  places and roads, never the caller.
- **Tests never hit the network.** All HTTP is mocked with `respx`. The TypeSafe and Exa clients
  are faked at their boundary.

## Non-goals (for now)
- Turn-by-turn directions, ticket purchase, ride-hail, bikes/scooters.
- Multi-leg itineraries beyond "drive vs transit for this trip".
- A web UI.

## Proposed spec map (the spec loop owns `specs/PLAN.md`)
0. architecture: modules, data flow, dirs, CLI/HTTP surface
1. scaffold: pyproject/uv, deps, config (`Settings`), logging, test setup
2. domain-model: TripRequest, Conditions, Recommendation, caller profile store (SQLite)
3. exa-conditions: the exact Exa queries, objectives, schemas, system prompts, timeouts
4. travel-times: optional drive/transit duration estimates (provider chosen and verified; Bling works without it)
5. jev-decision: Jev state shape, questions, response mapping, cost accounting
6. pipeline: orchestration, concurrency, time budget, degraded modes, reply wording
7. vapi-voice: assistant definition (prompt, tools, voice), webhook handling, `bling vapi sync`
8. sms: transport choice, inbound parse, signature check, reply
9. http-and-cli: FastAPI app wiring, `bling ask|serve|vapi sync`
10. evaluation: golden trips with recorded Exa/Jev fixtures, verdict sanity checks
11. ops: deploy target, secrets, structured logs, per-request cost (Exa `costDollars` + Jev tokens)
