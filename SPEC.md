# Bling: the build spec (single source of truth)

**Call** Bling and say where you're going. It checks live traffic and transit conditions with
**Exa**, lets **Jev** decide, and tells you **drive** or **take transit**, with the reason.
Voice only: no SMS, no links.

- **Vapi** runs the phone call: the number, turn-taking and interruptions, the conversation LLM,
  and calling Bling's `plan_trip` tool through the webhook.
- **Deepgram** is Vapi's ears and mouth: Nova-3 transcription (boosted with Bay Area place and
  transit names) and an Aura voice, billed to the user's own Deepgram key via a Vapi credential.
  Bling also calls Deepgram directly from the CLI, to test hearing and speaking without a phone.

Every decision here is final. Do not re-open it. If something is truly impossible as written,
make the smallest change, record it in `AGENT.md` "Gotchas", and move on.

## 0. Layout and stack

```
pyproject.toml   .python-version (3.11)   conftest.py (repo root)
src/bling/
  __init__.py      __version__ = "0.1.0"
  config.py        Settings
  domain.py        TripRequest, Incident, TransitAlert, Conditions, Recommendation
  conditions.py    Exa searches → Conditions
  decision.py      Jev → Recommendation
  pipeline.py      plan_trip(), reply_text()
  deepgram.py      DeepgramClient: transcribe(), speak() (CLI testing only)
  vapi.py          webhook handling, assistant definition, KEYTERMS, VapiApi (sync)
  app.py           create_app() FastAPI
  cli.py           typer: ask, serve, vapi-sync
  *_test.py        tests beside code
```

Python ≥ 3.11, uv, hatchling, `src/` layout. Runtime deps: `exa-py`, `typesafe-sdk>=0.7.5,<0.8`,
`fastapi`, `uvicorn`, `typer`, `pydantic-settings`, `httpx`. Dev group
(PEP 735 `[dependency-groups].dev`): `pytest`, `pytest-asyncio`, `respx`, `ruff`. Pytest:
`testpaths=["src"]`, `python_files=["*_test.py"]`, `asyncio_mode="auto"`. Ruff: line length 100,
`extend-exclude=["reference"]`. The console script `bling = "bling.cli:app"`.

All network I/O is async. Tests never touch the network: mock HTTP with `respx`, and pass fake
objects for Exa and Jev (they are duck-typed parameters, not imported clients). The root
`conftest.py` has an autouse fixture that deletes every Settings env var and `chdir`s to
`tmp_path`, so tests never read the real `.env`.

## 1. Settings (`config.py`)

`Settings(BaseSettings)` with `env_file=".env"`, `env_ignore_empty=True`, `extra="ignore"`, no prefix.

| field | type | default |
|---|---|---|
| exa_api_key, typesafe_api_key, deepgram_api_key, vapi_api_key, vapi_server_secret | `SecretStr \| None` | None |
| vapi_assistant_id | `str \| None` | None |
| vapi_llm_provider / vapi_llm_model | str | `"openai"` / `"gpt-4.1"` |
| vapi_voice_id | str | `"asteria"` (a Deepgram Aura voice in Vapi) |
| jev_model | str | `"jev-1.13.0"` |
| deepgram_stt_model / deepgram_tts_model | str | `"nova-3"` / `"aura-2-thalia-en"` |
| bling_region | str | `"San Francisco Bay Area, CA"` |
| bling_data_dir | Path | `Path("data")` |
| public_base_url | `str \| None` | None (https, no trailing slash) |
| exa_timeout_s / jev_timeout_s / plan_deadline_s | float | 5.0 / 2.5 / 8.0 |

`require(value, name) -> str` returns `value.get_secret_value()`, or raises
`RuntimeError(f"{name} is not set")`. A missing key fails where it is used, never at import.

## 2. Domain (`domain.py`, pydantic v2)

```python
class TripRequest(BaseModel):
    destination: str
    origin: str | None = None
    arrive_by: str | None = None      # free text as the user said it ("6pm")
    situation: str | None = None      # rider context, e.g. the Deepgram transcript

class Incident(BaseModel):     road: str; summary: str; severity: Literal["minor","moderate","severe"]
class TransitAlert(BaseModel): line: str; summary: str; severity: Literal["minor","moderate","severe"]

class Conditions(BaseModel):
    incidents: list[Incident] = []
    alerts: list[TransitAlert] = []
    sources: list[str] = []          # result URLs
    missing: list[str] = []          # "traffic" / "transit" when that search failed or timed out
    exa_cost_usd: float = 0.0

class Recommendation(BaseModel):
    mode: Literal["drive", "transit", "either"] | None   # None = Jev unavailable, no verdict
    traffic_bad: float | None = None      # Jev Noul probability
    transit_disrupted: float | None = None
    conditions: Conditions
    trip: TripRequest
    text: str                              # the reply, ≤ 320 chars
```

## 3. Exa conditions (`conditions.py`)

Follow `.claude/skills/build-with-exa/` exactly. Two searches run concurrently via
`asyncio.gather`, each under `asyncio.timeout(settings.exa_timeout_s)`. `exa` is any object with
`async def search(query, **kwargs)` (`exa_py.AsyncExa` in production). The literal calls (`D` is
the destination, `O` is the origin or `settings.bling_region`, `R` is `settings.bling_region`):

```python
TRAFFIC_SCHEMA = {"type": "object", "properties": {"incidents": {"type": "array", "items": {
    "type": "object", "properties": {"road": {"type": "string"}, "summary": {"type": "string"},
    "severity": {"type": "string", "enum": ["minor", "moderate", "severe"]}},
    "required": ["road", "summary", "severity"]}}}, "required": ["incidents"]}
TRANSIT_SCHEMA = same shape with key "alerts" and "line" in place of "road"

await exa.search(
    f"traffic crashes, road closures and congestion right now between {O} and {D}, {R}",
    type="auto",
    objective=(f"Find today's traffic incident and closure reports that would slow a drive from {O} "
               f"to {D}. Rank official DOT/511 alerts and local news traffic reports first; exclude "
               "old articles, generic directions pages and forecasts. Pull the road, what happened, "
               "and how severe it is."),
    system_prompt=("Include only incidents reported today that plausibly affect this drive. Never "
                   "invent incidents; return an empty list when none are reported."),
    output_schema=TRAFFIC_SCHEMA,
    contents={"highlights": True, "max_age_hours": 1, "livecrawl_timeout": 3000},
)
await exa.search(
    f"public transit service alerts and delays right now for trips to {D}, {R}",
    type="auto",
    objective=(f"Find today's service alerts, delays, suspensions and planned work on the public "
               f"transit lines a rider would take from {O} to {D}. Rank the transit agency's own "
               "alert pages first; exclude old news and schedules without alerts. Pull the line, "
               "what is wrong, and how severe it is."),
    system_prompt=("Include only alerts in effect today that plausibly affect this trip. Never "
                   "invent alerts; return an empty list when service is normal."),
    output_schema=TRANSIT_SCHEMA,
    contents={"highlights": True, "max_age_hours": 1, "livecrawl_timeout": 3000},
)
```

Never set `category`, `num_results`, domain filters or date filters. Never put `situation` in a
query. Read `output.content` from the response; it may be a dict or a JSON string, so handle both.
Read the result URLs into `sources`, and `cost_dollars.total` when present. Check the installed
exa-py for the exact attribute names; don't guess. A search that raises or times out adds
`"traffic"`/`"transit"` to `missing`. It never fabricates entries. Invalid items are skipped.
Tests assert the exact kwargs passed to `search`.

## 4. Jev decision (`decision.py`)

Use `typesafe_sdk` exactly as `reference/avicv_jev.py` does: `client.system_one(state=...,
questions=...)`, then `response.choices[k].choice`, `response.nouls[k].noul`. `jev` is duck-typed.
Production uses `AsyncTypeSafeClient(api_key=..., model=settings.jev_model)`. The call runs under
`asyncio.timeout(settings.jev_timeout_s)`.

```python
QUESTIONS = {
  "mode": Choice(
    instructions="Given `trip`, the current `conditions`, and the rider's `situation` (if any), "
                 "should the rider drive or take public transit for this trip?",
    criteria={
      "drive": "Driving is clearly the better choice: transit is disrupted, impractical for this "
               "trip, or the rider's situation needs a car, and roads are reasonably clear.",
      "transit": "Transit is clearly the better choice: roads have significant incidents or "
                 "congestion, or parking/cost/the rider's situation favor transit, and service is running.",
      "either": "Neither option is clearly better given what is known."}),
  "traffic_bad": Noul(
    instructions="Do `conditions` report traffic problems likely to delay a drive on this trip?",
    criteria=NoulCriteria(true="A reported incident, closure or heavy congestion affects the likely route.",
                          false="No reported problem affects the likely driving route.")),
  "transit_disrupted": Noul(
    instructions="Do `conditions` report transit problems likely to delay this trip?",
    criteria=NoulCriteria(true="A reported alert, delay or suspension affects the likely transit lines.",
                          false="No reported problem affects the likely transit lines.")),
}
state = {"trip": {destination, origin, arrive_by}, "situation": situation or "none given",
         "conditions": {"incidents": [...], "alerts": [...],
                        "searches_failed": missing, "note": "Empty lists mean nothing was reported."}}
```

`decide(trip, conditions, jev, settings) -> Recommendation`. If Jev is `None`, raises, or times
out, then `mode=None`. **No verdict is ever picked by code.**

## 5. Pipeline (`pipeline.py`)

`async def plan_trip(trip, *, exa, jev, settings) -> Recommendation`. It fetches conditions, then
decides. The total runtime is capped by `plan_deadline_s`, and anything outstanding at the
deadline is cancelled. If `exa` is `None`, conditions are empty with `missing=["traffic","transit"]`.

`reply_text(rec) -> str` (≤ 320 chars, plain sentences, no URLs):
- the verdict first: "Drive." / "Take transit." / "Either works." / "I couldn't make the call right now."
- then the most severe incident ("On the road: US-101: crash blocking two lanes.") or "No reported
  traffic problems."; then the most severe alert, or "Transit is running normally.". If a
  search is in `missing`, say "I couldn't check traffic" / "I couldn't check transit" instead.
- truncate cleanly at a word boundary.

## 6. Deepgram (`deepgram.py`), using the user's own `DEEPGRAM_API_KEY`

On calls, Vapi talks to Deepgram (see §7). Bling's own client exists so the CLI can test the same
ears and voice without a phone call.

`DeepgramClient(api_key, http: httpx.AsyncClient, stt_model, tts_model)`:
- `async transcribe(audio: bytes, content_type: str, keyterms: list[str] = []) -> str`: `POST
  https://api.deepgram.com/v1/listen?model={stt_model}&smart_format=true` plus one repeated
  `keyterm=<term>` query param per keyterm (httpx `params` as a list of tuples). Headers are
  `Authorization: Token {key}` and `Content-Type: {content_type}`, with raw bytes as the body.
  Returns `results.channels[0].alternatives[0].transcript` (`""` if missing). Timeout 30 s. A
  non-2xx response raises `RuntimeError("deepgram listen HTTP <code>")`.
- `async speak(text: str) -> bytes`: `POST https://api.deepgram.com/v1/speak?model={tts_model}`,
  JSON `{"text": text}`, the same auth header. Returns MP3 bytes. Timeout 30 s. Same error rule.
Tests use `respx`, asserting the URL, the repeated keyterm params, the auth header and the body.

## 7. Vapi (`vapi.py`): the phone assistant

**Webhook `POST /vapi/webhook`.** It requires the header `x-bling-secret` to equal
`VAPI_SERVER_SECRET` (`hmac.compare_digest`). If it's unset or wrong, respond 401. The body is
`{"message": {"type": ..., "toolCallList": [{"id", "function": {"name", "arguments"}}]}}`, where
`arguments` may be a dict or a JSON string. For `type=="tool-calls"`, run every call concurrently
and respond 200 `{"results": [{"name": n, "toolCallId": id, "result": "<string>"}]}`, with
`"error"` in place of `"result"` on failure (never both). For any other type, respond 200 `{}`.

**One tool:** `plan_trip(destination: str, origin?: str, arrive_by?: str, situation?: str)`,
which returns `reply_text(rec)`. The `situation` parameter description: "Anything the caller said
about their circumstances that could change the choice: luggage, kids, mobility, budget, parking,
being in a hurry, the weather where they are. Omit it if they said nothing." The tool also has
`"messages": [{"type": "request-start", "content": "Let me check the roads and transit."}]`
so the caller hears something while Exa and Jev run.

**Keyterms.** `KEYTERMS: list[str]` is a constant of Bay Area names Nova-3 should hear reliably:
`["BART", "Muni", "Caltrain", "AC Transit", "VTA", "SamTrans", "Golden Gate Transit",
"Salesforce Transit Center", "Embarcadero", "SFO", "Oakland Airport", "San Jose Airport",
"Bay Bridge", "Golden Gate Bridge", "San Mateo Bridge", "Dumbarton Bridge", "Richmond Bridge",
"US-101", "I-80", "I-280", "I-580", "I-680", "I-880", "Highway 1"]`. Used both in the
assistant's transcriber and in `bling ask --audio`.

**Assistant definition** `assistant_body(settings) -> dict`:
```python
{"name": "Bling",
 "firstMessage": "Hey, it's Bling. Where are you headed?",
 "transcriber": {"provider": "deepgram", "model": settings.deepgram_stt_model, "language": "en",
                 "keyterm": KEYTERMS, "endpointing": 300},
 "voice": {"provider": "deepgram", "voiceId": settings.vapi_voice_id},
 "model": {"provider": settings.vapi_llm_provider, "model": settings.vapi_llm_model,
           "messages": [{"role": "system", "content": SYSTEM_PROMPT}],
           "tools": [<plan_trip function tool>]},
 "server": {"url": f"{public_base_url}/vapi/webhook",
            "headers": {"x-bling-secret": <secret>}},
 "serverMessages": ["tool-calls"],
 # only when DEEPGRAM_API_KEY is set: Vapi then bills Deepgram usage to the user's own account
 "credentials": [{"provider": "deepgram", "apiKey": <deepgram key>}]}
```
A function tool is `{"type": "function", "function": {"name", "description", "parameters": <JSON
schema>}, "messages": [...]}`. `endpointing: 300` follows Vapi's guidance for short, one-word
answers like "SFO". `SYSTEM_PROMPT` is a constant: "You are Bling, a voice assistant that helps someone in
the San Francisco Bay Area decide whether to drive or take public transit. Get the destination,
and the origin and arrival time if they offer them. If they mention their circumstances
(luggage, kids, mobility, budget, parking, urgency), pass them as situation. Ask at most one
short follow-up. Then call plan_trip and say its answer in your own words, keeping every fact.
Never guess traffic or transit conditions yourself. Speak in short sentences. No lists, no URLs."

**`VapiApi(api_key, http)`**: `create_assistant(body)` is `POST https://api.vapi.ai/assistant`,
and `update_assistant(id, body)` is `PATCH https://api.vapi.ai/assistant/{id}`, both with
`Authorization: Bearer`. A non-2xx response raises with the status code and Vapi's error
message, which must never echo the request body (it contains keys).

**Phone number (manual, not code).** Bling uses a **Free Vapi Number** (a real US number,
area code 415, or 628/510 if unavailable), created in the Vapi dashboard, with
**Inbound Settings → Assistant** set to Bling. A Free Vapi SIP address is not used: it can't be
dialed from a normal phone. No code manages phone numbers; the webhook works the same for any
number attached to the assistant.

## 8. App (`app.py`)

`create_app(settings=None, *, exa=None, jev=None) -> FastAPI`. In the lifespan, it builds real
clients from the keys that are set (`AsyncExa(api_key=...)`, `AsyncTypeSafeClient(...)`) unless
injected (tests inject fakes), and closes them on shutdown. Routes: `POST /vapi/webhook` and
`GET /healthz` → `{"status": "ok"}`, nothing else. `docs_url=None, redoc_url=None, openapi_url=None`.

## 9. CLI (`cli.py`)

- `bling ask DESTINATION [--from ORIGIN] [--by TIME] [--situation TEXT] [--audio FILE] [--say OUT.mp3]`
  runs `plan_trip` with the real clients and prints `reply_text`.
  - `--audio FILE`: transcribe the file with Deepgram (content type from the extension: wav,
    mp3, m4a, webm, ogg, flac, defaulting to `application/octet-stream`) using `KEYTERMS`. Print
    `heard: <transcript>`, then use the transcript as `situation`. If `--situation` is also given,
    join them with " ".
  - `--say OUT.mp3`: write the reply as speech with Deepgram TTS (`deepgram_tts_model`).
  - Either flag without `DEEPGRAM_API_KEY` exits 1 with "DEEPGRAM_API_KEY is not set".
- `bling serve [--host 127.0.0.1] [--port 8000]`.
- `bling vapi-sync` builds `assistant_body`. It requires `VAPI_API_KEY`, `VAPI_SERVER_SECRET`
  and `PUBLIC_BASE_URL`. It PATCHes if `VAPI_ASSISTANT_ID` is set, otherwise POSTs and prints
  "Add VAPI_ASSISTANT_ID=<id> to .env". With `--dry-run` it prints the body with every secret
  replaced by `"***"` and sends nothing.

## 10. Privacy and secrets

Never log secrets, transcripts, raw request bodies, or phone numbers. Log tool names, timings,
`mode`, and `missing`. Never write keys into files other than `.env`.
