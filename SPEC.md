# Bling: the build spec (single source of truth)

Text or call Bling where you're going. It checks live traffic and transit conditions with **Exa**,
lets **Jev** decide, and answers **drive** or **take transit**, with the reason. Over text, you
can ask for a **voice link**:

- **review**: a page that plays the recommendation, spoken by **Deepgram** TTS.
- **explain**: a page where you record yourself explaining your situation. Deepgram transcribes
  it, Jev re-decides with that context, and the page shows the answer and speaks it.

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
  deepgram.py      DeepgramClient: transcribe(), speak()
  links.py         LinkStore: tokens for review/explain links
  pages.py         the two HTML pages (inline strings, no templates dir)
  vapi.py          webhook handling, assistant definition, VapiApi (sync)
  app.py           create_app() FastAPI
  cli.py           typer: ask, serve, vapi-sync
  *_test.py        tests beside code
```

Python ≥ 3.11, uv, hatchling, `src/` layout. Runtime deps: `exa-py`, `typesafe-sdk>=0.7.5,<0.8`,
`fastapi`, `uvicorn`, `typer`, `pydantic-settings`, `httpx`, `python-multipart`. Dev group
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
| jev_model | str | `"jev-1.13.0"` |
| deepgram_stt_model / deepgram_tts_model | str | `"nova-3"` / `"aura-2-thalia-en"` |
| bling_region | str | `"San Francisco Bay Area, CA"` |
| bling_data_dir | Path | `Path("data")` |
| public_base_url | `str \| None` | None (https, no trailing slash) |
| exa_timeout_s / jev_timeout_s / plan_deadline_s | float | 5.0 / 2.5 / 8.0 |
| link_ttl_hours | int | 24 |

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

`DeepgramClient(api_key, http: httpx.AsyncClient, stt_model, tts_model)`:
- `async transcribe(audio: bytes, content_type: str) -> str`: `POST
  https://api.deepgram.com/v1/listen?model={stt_model}&smart_format=true`, headers
  `Authorization: Token {key}` and `Content-Type: {content_type}`, raw bytes as the body. Returns
  `results.channels[0].alternatives[0].transcript` (`""` if missing). Timeout 30 s. A non-2xx
  response raises `RuntimeError("deepgram listen HTTP <code>")`.
- `async speak(text: str) -> bytes`: `POST https://api.deepgram.com/v1/speak?model={tts_model}`,
  JSON `{"text": text}`, the same auth header. Returns the MP3 bytes (the default encoding).
  Timeout 30 s. Same error rule.
Tests use `respx`, asserting the URL, the query params, the auth header and the body.

## 7. Links (`links.py`, `pages.py`)

`LinkStore(dir: Path, ttl_hours)` stores one JSON file per token at
`{bling_data_dir}/links/{token}.json`. Tokens are `secrets.token_urlsafe(16)`. Records:
`{"kind": "review"|"explain", "created": epoch, "trip": TripRequest, "rec": Recommendation|None,
"used": bool}`. `get()` returns `None` for unknown, expired or malformed tokens. Tokens must match
`^[A-Za-z0-9_-]{16,32}$` before touching the filesystem (no path traversal). The audio cache is
`{token}.mp3` beside the JSON.

Routes (in `app.py`):
- `GET /v/{token}`: the review page. The verdict text, plus `<audio controls autoplay
  src="/v/{token}/audio">`. 404 page if the token is bad.
- `GET /v/{token}/audio`: `audio/mpeg`. Calls `speak(rec.text)` once and caches the MP3.
- `GET /e/{token}`: the explain page. "Tell me about your trip to {destination}", a
  record/stop button using `MediaRecorder`, which uploads the blob to `/e/{token}/audio` with
  `fetch` (multipart field `audio`). It then shows the returned `text` and plays `audio_url`.
- `POST /e/{token}/audio`: requires `kind=="explain"` and `used==false`, otherwise 409/404.
  Rejects uploads over 10 MB (413). Calls `transcribe` (content type from the upload, default
  `audio/webm`). An empty transcript gives 422 `{"error": "I didn't catch that, try again."}`.
  Otherwise it sets `trip.situation = transcript`, runs `plan_trip`, stores the rec, sets
  `used=true`, creates a **review** token for that rec, and returns `{"text": rec.text,
  "audio_url": "/v/{review_token}/audio", "transcript": transcript}`.
The pages are small inline HTML strings, mobile-friendly, with all values HTML-escaped. No
external scripts.

## 8. Vapi (`vapi.py`): one assistant for voice calls and SMS chat

**Webhook `POST /vapi/webhook`.** It requires the header `x-bling-secret` to equal
`VAPI_SERVER_SECRET` (`hmac.compare_digest`). If it's unset or wrong, respond 401. The body is
`{"message": {"type": ..., "toolCallList": [{"id", "function": {"name", "arguments"}}]}}`.
`arguments` may be a dict or a JSON string. For `type=="tool-calls"`, run every call concurrently and
respond 200 `{"results": [{"name": n, "toolCallId": id, "result": "<string>"}]}` (or `"error"`
in place of `"result"` on failure; never both). For any other type, respond 200 `{}`.

Tools:
- `plan_trip(destination: str, origin?: str, arrive_by?: str)` returns `reply_text(rec)`.
- `voice_link(mode: "review"|"explain", destination: str, origin?: str, arrive_by?: str)`:
  - review: runs `plan_trip`, stores a review token, returns
    `"{rec.text} Listen here: {public_base_url}/v/{token}"`.
  - explain: stores an explain token (no rec yet), returns
    `"Record your situation here and I'll decide with it: {public_base_url}/e/{token}"`.
  - If `public_base_url` is unset, returns error "Voice links aren't set up yet."

**Assistant definition** `assistant_body(settings) -> dict`:
```python
{"name": "Bling",
 "firstMessage": "Hey, it's Bling. Where are you headed?",
 "transcriber": {"provider": "deepgram", "model": settings.deepgram_stt_model},
 "voice": {"provider": "deepgram", "voiceId": "asteria"},
 "model": {"provider": settings.vapi_llm_provider, "model": settings.vapi_llm_model,
           "messages": [{"role": "system", "content": SYSTEM_PROMPT}],
           "tools": [<plan_trip function tool>, <voice_link function tool>]},
 "server": {"url": f"{public_base_url}/vapi/webhook",
            "headers": {"x-bling-secret": <secret>}},
 "serverMessages": ["tool-calls"]}
```
Function tools look like `{"type": "function", "function": {"name", "description", "parameters": <JSON schema>}}`.
`SYSTEM_PROMPT` (a constant): "You are Bling. You help someone decide whether to drive or take
public transit. Get the destination (and the origin and arrival time if they offer them), then
call plan_trip and relay its answer briefly, word for word on facts. Never guess traffic or
transit conditions yourself. In a text conversation: if the person wants to hear the
recommendation, call voice_link with mode "review"; if they want to explain their situation by
voice, call voice_link with mode "explain". Send the link exactly as returned. Keep replies
under two sentences."

**`VapiApi(api_key, http)`**: `create_assistant(body)` is `POST https://api.vapi.ai/assistant`,
and `update_assistant(id, body)` is `PATCH https://api.vapi.ai/assistant/{id}`, both with
`Authorization: Bearer`. A non-2xx response raises with the status code.

## 9. App and CLI

`create_app(settings=None, *, exa=None, jev=None, deepgram=None) -> FastAPI`. In the lifespan,
it builds real clients from the keys that are set (`AsyncExa(api_key=...)`,
`AsyncTypeSafeClient(...)`, `DeepgramClient` with a shared `httpx.AsyncClient`) unless injected
(tests inject fakes), and closes them on shutdown. Routes: `/vapi/webhook`, `/v/*`, `/e/*`,
`GET /healthz` → `{"status": "ok"}`. `docs_url=None, redoc_url=None, openapi_url=None`.

CLI (`typer`):
- `bling ask DESTINATION [--from ORIGIN] [--by TIME] [--situation TEXT]` runs `plan_trip` with
  the real clients and prints `reply_text`.
- `bling serve [--host 127.0.0.1] [--port 8000]`.
- `bling vapi-sync` builds `assistant_body`. It requires `VAPI_API_KEY`, `VAPI_SERVER_SECRET`
  and `PUBLIC_BASE_URL`. It PATCHes if `VAPI_ASSISTANT_ID` is set, otherwise POSTs and prints
  "Add VAPI_ASSISTANT_ID=<id> to .env".

## 10. Privacy and secrets

Never log secrets, transcripts, raw request bodies, or phone numbers. Log tool names, timings,
`mode`, and `missing`. Never write keys into files other than `.env`.
