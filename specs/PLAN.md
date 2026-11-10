# Spec plan

The spec phase (`PROMPT_FILE=PROMPT.spec.md ./ralph.sh`) writes one spec per loop, top to bottom.
Check a spec off only once it is written and self-checked.

- [ ] 00-architecture: modules, data flow, directory layout, CLI and HTTP surface
- [ ] 01-scaffold: pyproject (uv, hatchling, src layout, PEP 735 dev group), Settings, logging, test layout
- [ ] 02-domain-model: TripRequest, Conditions, Incident, TransitAlert, Recommendation, caller profile store (SQLite)
- [ ] 03-exa-conditions: Exa `/search` calls (queries, objectives, output schemas, system prompts, freshness, timeouts, fakes)
- [ ] 04-travel-times: optional duration estimates (verify provider docs live; graceful absence)
- [ ] 05-jev-decision: Jev state, questions (Choice/Noul/Score), response mapping, validation, cost
- [ ] 06-pipeline: orchestration, 8 s budget, degraded modes, reply wording (voice and SMS)
- [ ] 07-vapi-voice: assistant config as code, tool definitions, webhook message handling, secret check, `bling vapi sync`
- [ ] 08-sms: transport decision (verify live docs), inbound parsing, signature verification, replies
- [ ] 09-http-and-cli: FastAPI app factory, routes, typer CLI
- [ ] 10-evaluation: golden trips, recorded fixtures, verdict sanity checks
- [ ] 11-ops: deploy, secrets, structured logs, cost tracking

## Discovered
