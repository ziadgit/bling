# fix_plan (27-minute build, top to bottom, one commit per item)

- [x] P0 — scaffold: pyproject.toml, .python-version, `uv sync`, root conftest.py, `__init__.py`, config.py (+ config_test), domain.py — spec: SPEC.md §0–2
- [x] P0 — conditions.py: the two Exa searches with exact kwargs, parsing, timeouts, `missing` + tests with a fake Exa — spec: SPEC.md §3
- [ ] P0 — decision.py: Jev questions/state, mapping, no-verdict fallback + tests with a fake Jev; pipeline.py plan_trip + reply_text + tests — spec: SPEC.md §4–5
- [ ] P0 — deepgram.py (transcribe, speak) + links.py LinkStore + tests (respx, tmp_path) — spec: SPEC.md §6–7
- [ ] P0 — vapi.py webhook handling (secret, tool-calls, plan_trip, voice_link) + assistant_body + VapiApi + tests — spec: SPEC.md §8
- [ ] P0 — app.py (create_app, lifespan, all routes incl. /v and /e pages from pages.py) + app_test with TestClient and fakes — spec: SPEC.md §7, §9
- [ ] P1 — cli.py (ask, serve, vapi-sync) + cli_test with typer CliRunner; README "Run it" section — spec: SPEC.md §9

## Discovered
