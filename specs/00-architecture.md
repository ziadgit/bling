# 00 — Architecture

## Purpose

This spec fixes Bling's module boundaries, how data moves between them, the directory layout,
and the external surfaces: HTTP routes, CLI commands, and Vapi tools. Every later spec fills in
one module listed here. When a later spec needs a different boundary, it must change this
document in the same loop. All other specs build on this one. It names files, owners, layers,
and protocols, but it does not define payload fields. Those belong to the owning specs (02–11).

## Requirements

1. All package code lives under `src/bling/`. The modules, their layers, and their owning specs
   are listed in the layout and layering tables below. Adding a module requires changing both
   tables in this spec.
2. Tests sit beside the code they test as `<module>_test.py` (for example
   `src/bling/pipeline_test.py`). Shared fakes live in `src/bling/testing/`, which is a real
   package, not test files. Pytest collects `src/**/*_test.py`; spec 01 configures this.
3. Import layering is enforced, and `src/bling/architecture_test.py` checks it with `ast`. A
   module may import a `bling.*` module only from its own layer or a lower one, with the
   same-layer exceptions in "Layering". Imports inside `if TYPE_CHECKING:` blocks count too;
   they are **not** exempt. The checker fails on any `bling` module that is missing from the
   layering table.
4. Every external service sits behind a `typing.Protocol` defined in the module that consumes
   it: Exa search, TypeSafe/Jev, the travel-time provider, the SMS sender, and the Vapi REST
   API. The pipeline and the channel handlers depend only on these protocols. SDK clients
   (`AsyncExa`, `AsyncTypeSafeClient`) are constructed **only** in `bling/services.py`. The
   httpx-based implementations for Vapi, SMS, and travel times are classes defined in their own
   modules, taking plain `str` credentials and an `httpx.AsyncClient`. They too are
   instantiated only in `bling/services.py`. Only `services.py` imports `exa_py` or
   `typesafe_sdk` at runtime. Other modules may import those SDKs only under `TYPE_CHECKING`,
   and only if they are layer ≥ 2.
5. All network I/O is `async`. Exa uses `exa_py.AsyncExa`. Jev uses
   `typesafe_sdk.AsyncTypeSafeClient`. Vapi, SMS, and travel-time providers use
   `httpx.AsyncClient`. No module imports the sync clients `exa_py.Exa` or
   `typesafe_sdk.TypeSafeClient`.
6. Every voice, SMS, and CLI trip request goes through the same core entry point:
   `bling.pipeline.plan_trip(request, *, exa, jev, travel, settings) -> PlanResult`.
   Neither channel adds its own decision logic. The channel turns the `PlanResult` into words
   by calling `reply.voice(result)` or `reply.sms(result)`. `pipeline` never calls `reply`.
7. Bling exposes exactly three HTTP routes: `POST /vapi/webhook`, `POST /sms/webhook`, and
   `GET /healthz`. FastAPI's docs routes are disabled.
8. The `bling` CLI provides exactly these commands: `ask`, `serve`, `vapi sync`, and
   `profile set` / `profile show` / `profile clear`.
9. The Vapi assistant gets exactly three function tools: `plan_trip`, `save_home`, and
   `web_search`. The IDEA default for `web_search` is "yes", and this spec confirms it.
10. **Privacy denylist.** Caller phone numbers never reach `conditions`, `decision`,
    `travel_times`, `pipeline`, `vapi.web_search`, or any outbound request except two:
    `SmsSender.send(to=...)` and the profile store. A **saved home address**, meaning a
    `TripRequest` origin with `origin_source == "profile"`, is never placed in an Exa query,
    objective, or system prompt (IDEA hard constraint). `conditions` builds those queries from
    the destination, the origin only when `origin_source == "request"`, and `Settings`'
    default city (spec 03). The travel-time provider may receive the origin address, because
    routing requires it, but never the phone number (spec 04).
11. **Logging.** Phone numbers are logged only as `privacy.phone_hash()` or
    `privacy.mask_phone()`. Home addresses are never logged; log `origin_source` instead.
    `privacy.redact(text)` (spec 01) scrubs E.164-looking numbers from free text, such as an
    SMS body or a traceback, before it is logged.
12. Secrets are declared only in `bling.config.Settings`, as `SecretStr`. `.get_secret_value()`
    may be called only in `bling/services.py`, `bling/vapi/webhook.py` (server-secret
    comparison), and `bling/sms/transport.py` (signature verification). An AST test enforces
    this.
13. All clients are created once per process, either in the FastAPI lifespan or in the CLI
    command, and closed on shutdown (`aclose()`). No module creates a client or opens a socket
    at import time. Importing any module with no environment variables set must succeed.
14. Webhooks fail closed. If `VAPI_SERVER_SECRET` is unset, every `POST /vapi/webhook` returns
    401. If the SMS signing credential is unset, every `POST /sms/webhook` returns 401. Both
    log a one-line warning naming the missing setting, not its value.

## Data model / interfaces

### Directory layout

```
pyproject.toml            # spec 01
.env.example              # spec 01 extends (SMS keys from spec 08)
data/                     # gitignored; SQLite lives here (BLING_DATA_DIR)
src/bling/
  __init__.py             # __version__ only                                    spec 01
  __main__.py             # `python -m bling` → cli.app()                       spec 09
  config.py               # Settings (pydantic-settings)                        spec 01
  logs.py                 # configure_logging(), JSON formatter                 spec 01 / 11
  privacy.py              # phone_hash(), mask_phone(), redact()                spec 01
  errors.py               # BlingError hierarchy (below)                        spec 00
  domain.py               # TripRequest, Conditions, Incident, TransitAlert,
                          # TravelTimes, Recommendation, PlanResult, CostLine   spec 02
  profiles.py             # ProfileStore (SQLite), CallerProfile                spec 02
  conditions.py           # ExaSearcher protocol; Exa searches → Conditions     spec 03
  travel_times.py         # TravelTimeProvider protocol, impl, NullProvider     spec 04
  decision.py             # JevClient protocol; questions, state, mapping       spec 05
  costs.py                # price(CostLine list) → usd; cost log line           spec 11
  reply.py                # PlanResult → voice / SMS wording                    spec 06
  parse.py                # free text ("to Union Station by 6pm") → TripRequest spec 08
  pipeline.py             # plan_trip(): fan-out, deadline, degrade             spec 06
  services.py             # Services dataclass, build_services(), aclose()      spec 00 / 09
  vapi/
    __init__.py           # empty
    api.py                # VapiApi protocol + HttpVapiApi                      spec 07
    assistant.py          # assistant definition as code (prompt, tools)        spec 07
    web_search.py         # `web_search` tool → one Exa search                  spec 07 (+03 rules)
    webhook.py            # auth, message dispatch, tool-call handling          spec 07
  sms/
    __init__.py           # empty
    transport.py          # SmsSender protocol + impl, signature verify, inbound parse   spec 08
    handler.py            # inbound text → plan_trip / save_home → reply        spec 08
  app.py                  # create_app(settings, services=None) FastAPI         spec 09
  cli.py                  # typer app                                           spec 09
  testing/
    __init__.py           # empty
    fakes.py              # FakeExa, FakeJev, FakeTravelTimes, FakeSms, FakeVapiApi
                          # (each owning spec adds its fake: 03, 04, 05, 07, 08)
    fixtures/             # recorded JSON (data, not modules)                   spec 10
  eval/
    __init__.py           # empty
    golden.py             # golden-trip runner                                  spec 10
```

`logs.py` and `app.py` are named this way on purpose, so they don't shadow the stdlib
`logging` and `http` modules.

### Layering (lowest → highest)

| Layer | Modules | Same-layer imports allowed? |
|------:|---------|-----------------------------|
| 0 | `bling` (`__init__`), `errors`, `privacy`, `config`, `logs` | yes |
| 1 | `domain` | — |
| 2 | `profiles`, `conditions`, `travel_times`, `decision`, `costs`, `reply`, `parse` | **no** |
| 3 | `pipeline`, `vapi.api`, `vapi.assistant`, `vapi.web_search`, `sms.transport` | no |
| 4 | `services`, `testing.fakes` | no |
| 5 | `vapi.webhook`, `sms.handler` | no |
| 6 | `app`, `cli`, `eval.golden` | `app` and `cli` may import each other only as `cli` → `app` |
| 7 | `__main__` | — |

Package `__init__` modules (`bling.vapi`, `bling.sms`, `bling.testing`, `bling.eval`) are empty,
import nothing, and count as layer 0. `testing.fakes` may be imported only by `*_test.py` files
and `eval.golden`. The checker enforces this.

### Errors (`bling/errors.py`, owned here)

```python
class BlingError(Exception):
    """Base for all expected, handled failures."""

class ConfigError(BlingError):
    """A required setting is missing, e.g. EXA_API_KEY when an Exa call is reached."""

class UpstreamError(BlingError):
    """An external service failed or timed out after its own retries."""
    def __init__(self, service: str, detail: str) -> None:
        super().__init__(f"{service}: {detail}")
        self.service = service   # "exa" | "jev" | "travel_times" | "vapi" | "sms"
        self.detail = detail

class BadRequest(BlingError):
    """Input could not be understood (unparseable SMS, tool args failing validation)."""

class AuthError(BlingError):
    """Webhook secret / signature missing or wrong. HTTP layer maps it to 401."""
```

`detail` must not contain secrets, phone numbers, addresses, or request bodies. Callers pass a
short reason such as `"timeout after 4.5s"` or `"HTTP 502"`.

### Protocols

These signatures are fixed. Owning specs may add keyword-only parameters that have defaults,
but must not change the ones shown here.

```python
# conditions.py (spec 03). Declares exactly the exa-py kwargs Bling uses; AsyncExa.search
# accepts all of them with defaults, so it satisfies this structurally.
class ExaSearcher(Protocol):
    async def search(
        self,
        query: str,
        *,
        type: str | None = None,
        contents: dict[str, Any] | None = None,
        objective: str | None = None,
        system_prompt: str | None = None,
        output_schema: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> Any: ...

async def fetch_conditions(trip: TripRequest, exa: ExaSearcher, settings: Settings,
                           *, timeout_s: float) -> Conditions: ...

# travel_times.py (spec 04)
class TravelTimeProvider(Protocol):
    async def estimate(self, trip: TripRequest, *, timeout_s: float) -> TravelTimes | None: ...

# decision.py (spec 05). Keyword-only, matching how the SDK is called in reference/avicv_jev.py.
class JevClient(Protocol):
    async def system_one(self, *, state: Any, questions: Mapping[str, Any]) -> Any: ...

async def decide(trip: TripRequest, conditions: Conditions, travel: TravelTimes | None,
                 jev: JevClient, *, timeout_s: float) -> Recommendation: ...

# sms/transport.py (spec 08)
class SmsSender(Protocol):
    async def send(self, *, to: str, body: str) -> None: ...

# vapi/api.py (spec 07)
class VapiApi(Protocol):
    async def get_assistant(self, assistant_id: str) -> dict[str, Any]: ...
    async def create_assistant(self, body: dict[str, Any]) -> dict[str, Any]: ...
    async def update_assistant(self, assistant_id: str, body: dict[str, Any]) -> dict[str, Any]: ...
```

Specs 03 and 05 must each include a mypy conformance check in their module, under
`if TYPE_CHECKING:`: `def _conforms(c: AsyncExa) -> ExaSearcher: return c` and
`def _conforms(c: AsyncTypeSafeClient) -> JevClient: return c`. If the real SDK signature does
not match, the spec adapts the protocol, or wraps the client in a thin adapter class defined in
`services.py`, and records the reason.

### Cost accounting

`domain.CostLine` is defined in spec 02:

```python
class CostLine(BaseModel):
    service: Literal["exa", "jev", "travel_times", "vapi", "sms"]
    quantity: float
    unit: str            # "usd" (Exa costDollars.total), "input_tokens" (Jev), "request"
```

`Conditions.costs` and `Recommendation.costs` (`list[CostLine]`) are filled by `conditions` and
`decision` from their SDK responses. `pipeline` concatenates them into `PlanResult.costs`.
`costs.price(lines, settings) -> float` converts each line to USD using
`Settings`' per-unit prices, and `costs.log_cost(...)` emits the cost log line. The channel
layer calls both after `plan_trip` returns (spec 11).

### Services container (`bling/services.py`)

```python
@dataclass
class Services:
    settings: Settings
    exa: ExaSearcher | None          # None when EXA_API_KEY unset
    jev: JevClient | None            # None when TYPESAFE_API_KEY unset
    travel: TravelTimeProvider       # NullTravelTimeProvider when not configured (spec 04)
    profiles: ProfileStore
    sms: SmsSender | None            # None when SMS keys unset
    vapi: VapiApi | None             # None when VAPI_API_KEY unset
    _closers: list[Callable[[], Awaitable[None]]] = field(default_factory=list)

    async def aclose(self) -> None: ...   # awaits every closer; logs and swallows each error

def build_services(settings: Settings) -> Services: ...   # constructs clients; no network I/O
```

`build_services` never performs network I/O. It passes explicit timeouts from `Settings` to
both SDK constructors (spec 01 names the fields). A missing key leaves that field `None`. When
code reaches a `None` service, it raises `ConfigError("<KEY> is not set")`, so failures happen at
the call site, not at import (AGENT.md). `pipeline.plan_trip` raises `ConfigError` up front when
`exa` or `jev` is `None`.

### Data flow

```
POST /vapi/webhook ─▶ vapi.webhook.handle(body, services)
     tool plan_trip ─┐    tool save_home ─▶ services.profiles.save_home(phone, address)
                     │    tool web_search ─▶ vapi.web_search.run(args, services.exa)
POST /sms/webhook ─▶ sms.handler.handle(request, services) ─┤
bling ask "..."   ─▶ cli ─▶ parse.parse_trip(text) ─────────┤
                                                            ▼
   channel layer: profiles.get(phone) → fill origin (origin_source="profile")
                  build TripRequest (no phone inside)
                                                            ▼
   pipeline.plan_trip(trip, exa=, jev=, travel=, settings=) -> PlanResult
       ├─ asyncio.gather under one deadline:
       │     conditions.fetch_conditions(trip, exa, settings)      # spec 03
       │     travel.estimate(trip)                                 # spec 04 (optional)
       └─ decision.decide(trip, conditions, travel_times, jev)     # spec 05
                                                            ▼
   channel layer: reply.voice(result) | reply.sms(result)          # spec 06
                  costs.price + costs.log_cost                     # spec 11
                  Vapi tool result string | SMS reply              # spec 07 / 08
```

`PlanResult` is defined in spec 02. It carries the `Recommendation`, the `Conditions` used, the
degraded-mode flags, and `costs`.

### HTTP surface (bodies owned by specs 07, 08, 09)

| Route | Auth | Success | Auth failure / unset secret |
|-------|------|---------|-----------------------------|
| `POST /vapi/webhook` | Vapi server secret (the exact header is verified live in spec 07) | 200 JSON. For `tool-calls`: `{"results": [{"toolCallId", "result"\|"error"}]}`. For informational messages: `{}` | 401 |
| `POST /sms/webhook` | provider signature (spec 08) | as spec 08 | 401 |
| `GET /healthz` | none | 200 `{"status": "ok", "version": "<__version__>"}` | — |

`/healthz` never calls external services and never reveals which keys are configured.

### CLI surface (flags owned by spec 09)

```
bling ask TEXT [--from ORIGIN] [--phone E164] [--json]   # parse → plan_trip → reply.voice; prints
bling serve [--host 127.0.0.1] [--port 8000]             # uvicorn on app.create_app()
bling vapi sync [--dry-run]                              # create-or-update assistant from code
bling profile set --phone E164 --home "ADDRESS"
bling profile show --phone E164                          # prints masked phone + home
bling profile clear --phone E164
```

### Vapi tools (schemas owned by spec 07)

| Tool | Args (model-written) | Server action |
|------|----------------------|---------------|
| `plan_trip` | `destination` (req), `arrive_by?`, `origin?` | profile origin fallback → `pipeline.plan_trip` → `reply.voice` |
| `save_home` | `address` (req) | `profiles.save_home(call.customer.number, address)`. If the call has no customer number, return `error`: "I can only save a home address when you call from a phone." |
| `web_search` | `query` (req), `objective` (req; description is the skill's verbatim text) | one Exa `/search` with the model's `query` and `objective`, unchanged, under `Settings`' web-search timeout. The tool description must say "search the live web" |

Vapi sends tool calls as `message.type == "tool-calls"` with `message.toolCallList[].id` and
`.function.{name, arguments}`, where `arguments` is a JSON object. Bling must answer HTTP 200
with one `results[]` entry per call, echoing `toolCallId`. The value goes in either `result` or
`error`, as a flat string, never both (verified at the docs cited below).

## Behavior & edge cases

- **Time budget ownership.** The 8 s p95 limit is measured at the HTTP boundary: from receiving
  a `tool-calls` request to sending the response. Spec 06 splits it between the parallel
  fetch phase (Exa and travel times) and the Jev call, and leaves headroom for parsing and
  serialization. Every lower module accepts an explicit `timeout_s` and enforces it with its
  SDK timeout plus `asyncio.timeout`. Lower modules never pick their own budget. Both SDK
  defaults are far too long for voice: exa-py uses a 600 s inactivity timeout and the TypeSafe
  SDK a 10 s per-operation timeout. So `build_services` sets explicit client timeouts, and
  calls also pass per-call timeouts.
- **Multiple tool calls in one Vapi message** run concurrently with `asyncio.gather` and share
  the one 8 s budget. All results come back in one response.
- **Cancellation.** If the deadline passes, the pipeline cancels outstanding tasks and awaits
  them. Because every client is async, cancelling a task closes its HTTP request. As in
  `reference/avicv_jev.py`, the pipeline must not leave paid requests running.
- **Partial failure.** A lower module raises `UpstreamError`, or returns empty or `None`.
  Turning that into degraded output belongs to the pipeline and reply (spec 06). Lower modules
  never fabricate conditions.
- **No verdict without Jev.** The drive/transit verdict is always a Jev `Choice`. If Jev is
  unconfigured, fails, or times out, there is no verdict. Spec 06 defines an honest "I couldn't
  make the call right now" reply. That reply may still state the conditions that were found,
  but it never contains a code-picked mode.
- **Webhook errors.** Inside `/vapi/webhook`, any `BlingError` raised while running a tool
  becomes that call's `error` string, still with HTTP 200. An unexpected exception gets the
  same treatment, with the generic text "Sorry, something went wrong checking that trip." The
  traceback is logged after `privacy.redact`. Only `AuthError` turns into a non-200 (401).
- **Profile store concurrency.** Each `ProfileStore` method runs its work inside
  `asyncio.to_thread`. It opens its own `sqlite3` connection inside that thread and closes it
  before returning, so connections are never shared across threads.
- **Startup.** `create_app` creates `BLING_DATA_DIR` if it is missing. Network clients are
  created only in the lifespan startup.

## Acceptance criteria

1. Every module in the layout table appears in the layering table, and its owning spec is
   listed in `specs/PLAN.md`.
2. Once built: `python -c "import bling, bling.app, bling.cli"` succeeds with an empty
   environment.
3. Once built: `architecture_test.py` passes. Its synthetic-violation tests prove that it
   detects (a) an upward import, including one under `TYPE_CHECKING`, (b) a same-layer import
   in layer 2, (c) an unknown module, (d) a sync SDK import, and (e) `.get_secret_value()`
   outside the allowlist.
4. Once built: the paths in `create_app().routes` are exactly `/vapi/webhook`, `/sms/webhook`,
   and `/healthz`, and `GET /docs`, `/redoc`, and `/openapi.json` each return 404.
5. Once built: `bling --help` lists exactly `ask`, `serve`, `vapi`, and `profile`.
   `bling vapi --help` lists exactly `sync`. `bling profile --help` lists exactly `set`,
   `show`, and `clear`.
6. Once built: with `VAPI_SERVER_SECRET` unset, `POST /vapi/webhook` with any body returns 401.
   With the SMS credential unset, `POST /sms/webhook` returns 401.

## Test plan

- `src/bling/architecture_test.py` holds a pure function,
  `check(sources: dict[str, str]) -> list[str]`, which maps module name to source and returns
  violations. It runs against the real tree and against synthetic inputs.
  - `test_real_tree_clean`: loads every `src/bling/**/*.py` except `*_test.py`, and asserts
    `check(...) == []`.
  - `test_upward_import_detected`, `test_type_checking_import_detected`,
    `test_same_layer_2_detected`, `test_unknown_module_detected`, and
    `test_fakes_import_outside_tests_detected` each feed one synthetic source and assert
    exactly one violation.
  - `test_sync_sdk_detected`: `ImportFrom` nodes from `exa_py` naming `Exa`, and from
    `typesafe_sdk` naming `TypeSafeClient`, are violations. Names are compared exactly, so
    `AsyncExa` and `AsyncTypeSafeClient` pass. Runtime SDK imports outside `services` are also
    violations.
  - `test_secret_unwrap_allowlist`: an `Attribute` node named `get_secret_value` in a module
    other than `services`, `vapi.webhook`, or `sms.transport` is a violation.
  - `test_import_without_env`: uses `monkeypatch.delenv` on all keys, then imports every module
    with `importlib.import_module` in a subprocess (`sys.executable -c`), so the module cache
    is clean.
- `src/bling/services_test.py`
  - Asserts that `build_services(Settings(_env_file=None))` with no keys returns `exa is None`,
    `jev is None`, `sms is None`, `vapi is None`, and `travel` as the null provider.
  - Asserts that, with dummy keys, `build_services` returns non-`None` clients and makes no
    request. For `AsyncExa`, which uses httpx, this runs under
    `respx.mock(assert_all_mocked=True)` with no routes. `typesafe-sdk` 0.7.5 uses **`httpx2`**,
    not httpx (spec 01, open question 11), so respx cannot see it. For the TypeSafe client the
    check is constructor-level instead, as spec 05 defines it.
  - Asserts that `aclose()` awaits every closer even when one raises.
- Specs 09 (`app_test.py`, `cli_test.py`) and 07 / 08 own the tests for acceptance criteria 4–6.
- The fakes in `bling/testing/fakes.py` satisfy each protocol structurally, and mypy checks
  this. Each owning spec defines its fake's recorded-call API.

## Open questions (resolved)

1. **One module or a package for Exa conditions?** One module, `conditions.py`. It holds a few
   query builders and one parser, and a package would add indirection without a payoff.
2. **Where does the general `web_search` tool live?** In `vapi/web_search.py`. It exists only
   for the voice LLM. It follows the same Exa rules as spec 03, but its `query`/`objective`
   come from the model. Keeping it out of `conditions.py` means spec 03 owns only Bling's own
   queries.
3. **Can the saved home address reach Exa?** No. IDEA says saved home addresses are never sent
   to Exa. When `origin_source == "profile"`, Exa queries use the destination and the default
   city or region only. An origin the caller states in the request is part of what they asked
   about, so it may appear in a query.
4. **Who resolves origin from the profile?** The channel layer (`vapi.webhook`, `sms.handler`,
   `cli`). It looks up the profile and builds a complete `TripRequest`, with `origin_source`
   set, before calling `plan_trip`. That keeps `pipeline` free of phone numbers.
5. **How does `pipeline` get its clients without importing `services` (layer 4)?**
   `plan_trip` takes explicit keyword arguments (`exa`, `jev`, `travel`, `settings`). The
   channel unpacks `Services`. This avoids an upward import and keeps the pipeline easy to test.
6. **Where does free-text parsing live?** In `parse.py` (layer 2), owned by spec 08, because
   SMS is the main free-text channel. `bling ask` reuses it.
7. **SMS route path when the transport isn't chosen yet?** It is fixed as `/sms/webhook`
   whatever the provider. Spec 08 defines its body and auth.
8. **Sync or async SDKs?** Async only. `AsyncExa` supports per-call `timeout` and
   cancel-by-task, per the exa-py README. `AsyncTypeSafeClient` takes `timeout` and `retry` and
   has `aclose()`, per the TypeSafe docs. Both give the cancellation the 8 s budget needs.
9. **Unset webhook secret: 401 or 503?** 401 for both. IDEA says "reject anything unsigned". A
   single failure code is simpler, and the warning log names the cause.
10. **Do we need a DI framework?** No. The plain `Services` dataclass is built once and passed
    explicitly. Tests build it, or pass protocol arguments, with fakes.

## References (read live, 2026-11-09)

- Vapi server events (`tool-calls` body, `results` response): https://docs.vapi.ai/server-url/events
- Vapi function tools (flat-string `result`/`error`, always HTTP 200): https://docs.vapi.ai/tools/custom-tools
- exa-py README (`AsyncExa`, timeouts, cancellation): https://github.com/exa-labs/exa-py
- TypeSafe Python SDK basic usage (`AsyncTypeSafeClient`, env vars): https://docs.typesafe.ai/sdk/python/usage/basic
- Exa skill: `.claude/skills/build-with-exa/SKILL.md`, `references/sdks.md`
