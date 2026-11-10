# 01 — Scaffold

## Purpose

This spec fixes the project skeleton: `pyproject.toml` (uv, hatchling, `src/` layout, a PEP 735
`dev` group), the lint, type, and test configuration, the root `conftest.py` that keeps tests
off the network and away from the developer's `.env`, and the four layer-0 modules
`bling/__init__.py`, `config.py` (`Settings`), `logs.py`, and `privacy.py`. It also tells the
scaffold item to create `errors.py` exactly as spec 00 defines it. Later specs may add
`Settings` fields (see Requirement 6) but must not rename the ones defined here.

## Requirements

1. `pyproject.toml` is exactly the document in "pyproject.toml" below, apart from dependency
   additions that later specs make. `uv.lock` is committed. `.python-version` contains `3.11`.
2. `uv sync` from a clean checkout installs the runtime and `dev` dependencies into `.venv/`.
   After that, every command in AGENT.md's table works: `.venv/bin/ruff check .`,
   `.venv/bin/mypy src/bling`, `.venv/bin/pytest -x -q`, and `.venv/bin/python -c "import bling"`.
3. The version has a single source: `src/bling/__init__.py` holds `__version__ = "0.1.0"` and
   nothing else (apart from a module docstring). Hatch reads it from there
   (`[tool.hatch.version]`).
4. Pytest collects only `src/**/*_test.py`. `asyncio_mode = "auto"` is set, so async tests need
   no marker.
5. `src/bling/config.py` defines `Settings(BaseSettings)` with exactly the fields in "Settings"
   below. `Settings()` constructs without error when no environment variables are set and no
   `.env` file exists. Every secret is `SecretStr | None` and defaults to `None`. An empty value
   in `.env` (for example `EXA_API_KEY=`) counts as unset (`env_ignore_empty=True`).
6. Later specs add `Settings` fields by editing `config.py`, and by adding a row to the table in
   their own spec. New secrets must be `SecretStr | None = None`. Every new field needs a default,
   so Requirement 5 stays true. Spec 08 adds the SMS credentials.
7. `Settings` validates its values when constructed and raises `pydantic.ValidationError` on
   invalid ones: timeouts must be `> 0` and `<= 8.0`; `jev_max_retries` must be in `0..3`;
   `bling_timezone` must load with `zoneinfo.ZoneInfo`; `bling_log_level` must be one of
   `DEBUG|INFO|WARNING|ERROR`; prices must be `>= 0`; `public_base_url`, when set, must start with
   `https://` and must not end with `/`.
8. `config.require(value: SecretStr | None, env_name: str) -> SecretStr` returns `value`, or
   raises `ConfigError(f"{env_name} is not set")` when it is `None`. It does not unwrap the
   secret, so `config.py` stays off spec 00's `.get_secret_value()` allowlist.
9. `src/bling/logs.py` defines `configure_logging(level: str, fmt: Literal["text", "json"]) ->
   None`. It is idempotent: calling it twice leaves exactly one Bling handler on the root
   logger. Both formats pass the message and any traceback through `privacy.redact`. The JSON
   format writes exactly one JSON object per line.
10. `src/bling/privacy.py` defines `phone_hash`, `mask_phone`, and `redact`, with the exact
    behaviour in "privacy.py" below. None of them performs I/O. `phone_hash` and `mask_phone` never
    return any of the input digits except, for `mask_phone`, the last four.
11. The root `conftest.py` contains two autouse fixtures. `_clean_env` deletes every
    environment variable `Settings` reads, then `chdir`s into the test's `tmp_path`, so a bare
    `Settings()` can never load the developer's real `.env`. `_no_network` makes any
    `AF_INET` / `AF_INET6` `socket.connect` or `connect_ex` raise
    `RuntimeError("network access in tests")`. Tests that build `Settings` pass either
    `_env_file=None` or an explicit `tmp_path` file.
12. The scaffold item also creates `src/bling/errors.py` exactly as written in spec 00
    ("Errors"), and the empty package files `src/bling/testing/__init__.py` and
    `src/bling/testing/fakes.py`. The fakes module holds only a docstring until specs 03–08 add
    their fakes. The other packages (`vapi/`, `sms/`, `eval/`) are created by the items that
    first add a module to them.
13. Importing `bling`, `bling.config`, `bling.logs`, `bling.privacy`, or `bling.errors` touches
    no network, reads no files except `.env`, and only when `Settings()` is constructed, never at
    import. It also configures no logging.

## Data model / interfaces

### pyproject.toml

```toml
[project]
name = "bling"
dynamic = ["version"]
description = "Call or text where you're going; Bling says drive or take transit."
readme = "README.md"
requires-python = ">=3.11"
dependencies = [
    "exa-py>=2.28.0",
    "typesafe-sdk>=0.7.5,<0.8",
    "fastapi>=0.162.2",
    "uvicorn>=0.54.0",
    "typer>=0.29.0",
    "pydantic>=2.14.3",
    "pydantic-settings>=2.16.2",
    "httpx>=0.28.1",
    "tzdata>=2026.6",
]

[project.scripts]
bling = "bling.cli:app"

[dependency-groups]
dev = [
    "pytest>=9.2.0",
    "pytest-asyncio>=1.4.1",
    "respx>=0.23.1",
    "ruff>=0.17.4",
    "mypy>=2.4.1",
]

[build-system]
requires = ["hatchling>=1.33.0"]
build-backend = "hatchling.build"

[tool.hatch.version]
path = "src/bling/__init__.py"

[tool.hatch.build.targets.wheel]
packages = ["src/bling"]
exclude = ["**/*_test.py"]

[tool.pytest.ini_options]
testpaths = ["src"]
python_files = ["*_test.py"]
asyncio_mode = "auto"
asyncio_default_fixture_loop_scope = "function"
addopts = "-ra --strict-markers"

[tool.ruff]
line-length = 100
target-version = "py311"
src = ["src"]
extend-exclude = ["reference"]

[tool.ruff.lint]
select = ["E", "F", "W", "I", "UP", "B", "SIM", "RUF", "ASYNC"]

[tool.mypy]
python_version = "3.11"
strict = true
plugins = ["pydantic.mypy"]
mypy_path = "src"
packages = ["bling"]

[tool.pydantic-mypy]
init_forbid_extra = true
init_typed = true
warn_required_dynamic_aliases = true
```

Notes the build phase needs:

- The `bling` console script points at `bling.cli:app`, which spec 09 creates. Until then the
  installed script fails on import. That is expected. The scaffold acceptance criteria never
  run `bling`.
- `typesafe-sdk` is pinned `<0.8` because it is pre-1.0 and Bling depends on
  `system_one`, `Choice`, `Noul`, `Score`, and `RetryPolicy`. The pin is raised deliberately,
  with a check against `reference/avicv_jev.py` usage.
- `tzdata` is a runtime dependency so `ZoneInfo` works on slim container images that ship no
  system zone database (spec 11).
- The `dev` group is installed by `uv sync` by default (uv docs, cited below).
- `reference/` is excluded from ruff. It holds a sibling app's code kept for reading, not
  Bling code. With this rule set, ruff reports 17 errors in `reference/avicv_jev.py`.

### Directory files created by the scaffold item

```
.python-version          # "3.11"
pyproject.toml
uv.lock                  # generated by `uv sync`, committed
conftest.py              # repo root; see "conftest.py"
src/bling/__init__.py    # __version__ = "0.1.0"
src/bling/errors.py      # spec 00 "Errors", verbatim
src/bling/config.py
src/bling/logs.py
src/bling/privacy.py
src/bling/testing/__init__.py   # empty
src/bling/testing/fakes.py      # docstring only
src/bling/config_test.py
src/bling/logs_test.py
src/bling/privacy_test.py
```

`conftest.py` is at the repo root, not under `src/bling/`, so spec 00's architecture checker
never sees it as an unknown `bling` module. Pytest still loads it because it sits in the
rootdir.

### Settings

`src/bling/config.py`:

```python
from pathlib import Path
from typing import Literal
from pydantic import SecretStr, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="ignore",
        case_sensitive=False,
    )
    # fields: exactly the table below, in this order
```

There is no `env_prefix`. Each field's environment variable is its name in upper case. That
keeps the variable names already in `.env.example` (`EXA_API_KEY`, `JEV_MODEL`,
`BLING_DATA_DIR`, `PUBLIC_BASE_URL`).

| Field | Type | Default | Env var | Used by |
|-------|------|---------|---------|---------|
| `exa_api_key` | `SecretStr \| None` | `None` | `EXA_API_KEY` | services (03) |
| `typesafe_api_key` | `SecretStr \| None` | `None` | `TYPESAFE_API_KEY` | services (05) |
| `vapi_api_key` | `SecretStr \| None` | `None` | `VAPI_API_KEY` | services (07) |
| `vapi_server_secret` | `SecretStr \| None` | `None` | `VAPI_SERVER_SECRET` | vapi.webhook (07) |
| `jev_model` | `str` | `"jev-1.13.0"` | `JEV_MODEL` | services (05) |
| `jev_max_retries` | `int` | `0` | `JEV_MAX_RETRIES` | services → `RetryPolicy(max_retries=...)` (05) |
| `exa_timeout_s` | `float` | `6.0` | `EXA_TIMEOUT_S` | `AsyncExa(timeout=...)` client ceiling (03) |
| `jev_timeout_s` | `float` | `6.0` | `JEV_TIMEOUT_S` | `AsyncTypeSafeClient(timeout=...)` client ceiling (05) |
| `travel_timeout_s` | `float` | `4.0` | `TRAVEL_TIMEOUT_S` | travel-time `httpx.AsyncClient` ceiling (04) |
| `vapi_http_timeout_s` | `float` | `8.0` | `VAPI_HTTP_TIMEOUT_S` | Vapi REST `httpx.AsyncClient` (07) |
| `sms_http_timeout_s` | `float` | `8.0` | `SMS_HTTP_TIMEOUT_S` | SMS send `httpx.AsyncClient` (08) |
| `web_search_timeout_s` | `float` | `6.0` | `WEB_SEARCH_TIMEOUT_S` | per-call timeout of the `web_search` tool (07) |
| `plan_deadline_s` | `float` | `7.0` | `PLAN_DEADLINE_S` | total `plan_trip` budget; spec 06 splits it |
| `bling_region` | `str` | `"Chicago, IL"` | `BLING_REGION` | default city or region in Exa queries (03) and the parser (08) |
| `bling_timezone` | `str` | `"America/Chicago"` | `BLING_TIMEZONE` | resolves "by 6" into an aware datetime (02, 08) |
| `bling_data_dir` | `Path` | `Path("data")` | `BLING_DATA_DIR` | SQLite location (02); created by `create_app` (00) |
| `bling_log_level` | `str` | `"INFO"` | `BLING_LOG_LEVEL` | `configure_logging` |
| `bling_log_format` | `Literal["text", "json"]` | `"text"` | `BLING_LOG_FORMAT` | `configure_logging`; spec 11 sets `json` in deploy |
| `public_base_url` | `str \| None` | `None` | `PUBLIC_BASE_URL` | webhook URLs given to Vapi / SMS provider (07, 08) |
| `price_exa_usd_per_usd` | `float` | `1.0` | `PRICE_EXA_USD_PER_USD` | `costs.price` for `unit="usd"` (11) |
| `price_jev_usd_per_mtok` | `float` | `0.042` | `PRICE_JEV_USD_PER_MTOK` | `costs.price` for `unit="input_tokens"` (11) |
| `price_travel_usd_per_request` | `float` | `0.0` | `PRICE_TRAVEL_USD_PER_REQUEST` | `costs.price` (04 sets the real default) |
| `price_sms_usd_per_message` | `float` | `0.0` | `PRICE_SMS_USD_PER_MESSAGE` | `costs.price` (08 sets the real default) |

Timeout fields are client ceilings. Every lower module still receives an explicit `timeout_s`
from its caller (spec 00). The ceilings matter because both SDK defaults are far too long for
voice: exa-py's `DEFAULT_REQUEST_TIMEOUT` is 600 s and the TypeSafe SDK's `DEFAULT_TIMEOUT` is
10 s (both read in the 2026-11-09 wheels). `jev_max_retries` defaults to `0` because the SDK's
default `RetryPolicy` (`max_retries=2`, backoff up to 5 s) cannot fit inside the voice budget.

Validators (`field_validator`, all raising `ValueError`, which pydantic wraps):

```python
_TIMEOUT_FIELDS = ("exa_timeout_s", "jev_timeout_s", "travel_timeout_s", "vapi_http_timeout_s",
                   "sms_http_timeout_s", "web_search_timeout_s", "plan_deadline_s")
# each: 0 < v <= 8.0
# jev_max_retries: 0 <= v <= 3
# bling_timezone: ZoneInfo(v) must not raise
# bling_log_level: v.upper() in {"DEBUG", "INFO", "WARNING", "ERROR"}; stored upper-cased
# price_*: v >= 0
# public_base_url: None, or startswith("https://") and not endswith("/")
```

Helpers in the same module:

```python
def require(value: SecretStr | None, env_name: str) -> SecretStr:
    """Return value, or raise ConfigError(f"{env_name} is not set")."""

def tz(settings: Settings) -> ZoneInfo:
    """ZoneInfo(settings.bling_timezone)."""
```

`config.py` never calls `.get_secret_value()`. `Settings.__repr__` and `str()` show secrets as
`SecretStr('**********')`, which pydantic does by default. Nothing overrides that.

### logs.py

```python
def configure_logging(level: str = "INFO", fmt: Literal["text", "json"] = "text") -> None: ...

class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str: ...

class TextFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str: ...
```

- The root logger gets one `StreamHandler(sys.stderr)` with the attribute
  `_bling_handler = True`. `configure_logging` removes any existing handler that has that
  attribute before it adds the new one. Handlers without the attribute, such as pytest's
  caplog handler, are left alone.
- The root level is set to `level`. The `httpx`, `httpcore`, and `hpack` loggers are set to
  `WARNING`, so request lines are not logged at INFO.
- **JSON line** keys, in this order: `ts` (UTC ISO-8601 with milliseconds and `Z`, for example
  `"2026-11-09T18:16:32.123Z"`), `level` (`"INFO"`), `logger` (`record.name`), `msg`
  (`redact(record.getMessage())`), then every `extra=` attribute in insertion order, then `exc`
  (`redact(formatted traceback)`) when `exc_info` is set. Extras are the record attributes not
  present on a fresh `logging.LogRecord`, excluding `message` and `asctime`, which
  `logging.Formatter` adds while formatting. Values are emitted with
  `json.dumps(..., default=str, ensure_ascii=False)`. `str` extras also pass through `redact`.
- **Text line:** `HH:MM:SS.mmm LEVEL logger: msg key=value ...`, in local time, followed by a
  redacted traceback on the next lines. The message, `str` extras, and the traceback all pass
  through `redact`, as in the JSON format.
- Modules log through `logging.getLogger(__name__)`. Nothing in `bling` calls `print` except
  `cli.py` (spec 09).

### privacy.py

```python
def phone_hash(phone: str) -> str: ...
def mask_phone(phone: str) -> str: ...
def redact(text: str) -> str: ...
```

- `phone_hash(phone)`: keep only the digits of `phone`, compute
  `hmac.new(_PROCESS_KEY, digits.encode(), "sha256").hexdigest()[:12]`, and return
  `"ph_" + that`. `_PROCESS_KEY = secrets.token_bytes(32)` is generated once at import. So a
  number hashes the same way throughout one process, so log lines can be correlated, but the
  hash cannot be reversed by trying every phone number, and it does not match across restarts.
  Input with no digits returns `"ph_none"`.
- `mask_phone(phone)`: keep only the digits. If there are fewer than 4, return `"****"`.
  Otherwise return `"+"` (only if `phone` started with `"+"`), then `"*"` for every digit except
  the last four, then the last four. Example: `mask_phone("+13125551234") == "+*******1234"`.
- `redact(text)` replaces every match of the two patterns below, in this order, with the
  literal `"[phone]"`:
  1. E.164, optionally with separators:
     `\+\d{1,3}(?:[\s.\-]?\(?\d{2,4}\)?){2,4}[\s.\-]?\d{2,4}` where the match contains 8 to 15
     digits. A match outside that range is left as is.
  2. NANP without a `+`: `(?<!\d)\(?\d{3}\)?[\s.\-]?\d{3}[\s.\-]?\d{4}(?!\d)`.

  Redacting too much is acceptable (a 10-digit Unix timestamp becomes `[phone]`). Redacting
  too little is a bug. ISO dates and times (`2026-11-09 18:16:32`) must not match, because
  neither pattern accepts `:` as a separator and the NANP pattern needs a 3-3-4 grouping.

### conftest.py (repo root)

```python
import socket
from pathlib import Path

import pytest
from bling.config import Settings

_SETTINGS_ENV = [name.upper() for name in Settings.model_fields]

@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    for name in _SETTINGS_ENV:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.chdir(tmp_path)   # a bare Settings() can never see the repo's real .env

@pytest.fixture(autouse=True)
def _no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    real_connect = socket.socket.connect
    def guarded(self: socket.socket, address: object) -> None:
        if self.family in (socket.AF_INET, socket.AF_INET6):
            raise RuntimeError("network access in tests")
        real_connect(self, address)  # AF_UNIX (e.g. asyncio internals) passes
    real_connect_ex = socket.socket.connect_ex
    def guarded_ex(self: socket.socket, address: object) -> int:
        if self.family in (socket.AF_INET, socket.AF_INET6):
            raise RuntimeError("network access in tests")
        return real_connect_ex(self, address)
    monkeypatch.setattr(socket.socket, "connect", guarded)
    monkeypatch.setattr(socket.socket, "connect_ex", guarded_ex)
```

`_SETTINGS_ENV` comes from `Settings.model_fields`, so fields added by later specs are covered
automatically. FastAPI's `TestClient` and `respx` never open real sockets, so the guard does not
affect them.

## Behavior & edge cases

- **`.env` absent:** `Settings()` returns all defaults. **`.env` present but the process
  environment also sets a key:** the process environment wins (pydantic-settings precedence).
- **Whitespace-only secret** (`EXA_API_KEY="  "`): it is not empty, so it loads as a
  `SecretStr`, and the provider rejects it at call time. Bling does not strip secrets. Stripping
  would hide copy-paste errors that the provider's 401 makes obvious.
- **Unknown keys in `.env`** (for example the SMS keys before spec 08 lands) are ignored
  (`extra="ignore"`).
- **Relative `BLING_DATA_DIR`** is resolved against the current working directory when used,
  not at construction. `Settings` does not create directories.
- **`configure_logging` with an invalid level** raises `ValueError`. Callers pass
  `settings.bling_log_level`, which is already validated.
- **Logging a `SecretStr`** prints `**********`. Logging a raw phone number in a message or
  traceback gets `[phone]` from `redact`. That is a backstop, not permission to log raw numbers
  (spec 00 Requirement 11).
- **`phone_hash` across processes** (the CLI and the server) produces different hashes. This is
  intended, and is documented in spec 11's log guide.

## Acceptance criteria

1. On a clean checkout with uv 0.11+, `uv sync` succeeds and creates `.venv/` and `uv.lock`.
2. `.venv/bin/ruff check .`, `.venv/bin/mypy src/bling`, and `.venv/bin/pytest -x -q` all exit 0.
3. `env -i PATH="$PATH" .venv/bin/python -c "import bling, bling.config, bling.logs,
   bling.privacy, bling.errors; print(bling.__version__)"` prints `0.1.0`.
4. `uv build` produces a wheel that contains `bling/__init__.py` and `bling/config.py` and no
   `*_test.py` file.
5. `Settings(_env_file=None)` with an empty environment has every secret set to `None`,
   `jev_model == "jev-1.13.0"`, and `plan_deadline_s == 7.0`.
6. Every test in the test plan below exists and passes.

## Test plan

No test touches the network. The root `conftest.py` guard enforces this, and none of these
tests need HTTP mocks.

`src/bling/config_test.py`
- `test_defaults_with_empty_env`: `Settings(_env_file=None)`. Assert every secret is `None` and
  every default matches the table, by comparing against a dict literal of the table.
- `test_env_var_names_match_table`: `monkeypatch.setenv` for each table env var with a valid
  value, then assert that each field picked it up. This catches an accidental `env_prefix` or a
  renamed field.
- `test_empty_string_is_unset`: write `EXA_API_KEY=\n` to a `tmp_path/.env`, call
  `Settings(_env_file=tmp_path/".env")`, and assert `exa_api_key is None`.
- `test_env_file_loaded`: a `.env` in `tmp_path` containing `JEV_MODEL=jev-1.14.0` is picked up.
  A process env var for the same key overrides the file.
- `test_secret_not_in_repr`: set `EXA_API_KEY=sk-test-123`. Assert `"sk-test-123"` appears in
  neither `repr(settings)` nor `str(settings)`.
- `test_timeout_bounds` (parametrized over `_TIMEOUT_FIELDS`, with values `0`, `-1`, and `8.01`,
  passed as kwargs: `Settings(_env_file=None, **{field: v})`): each raises `ValidationError`.
  `8.0` is accepted. The other bounds tests below pass their values as kwargs too, except where
  an env var is named.
- `test_jev_max_retries_bounds`: `-1` and `4` are rejected; `0` and `3` are accepted.
- `test_bad_timezone_rejected`: `BLING_TIMEZONE=Mars/Olympus` raises `ValidationError`.
- `test_log_level_normalized`: `debug` is stored as `DEBUG`, and `TRACE` is rejected.
- `test_public_base_url_rules`: `http://x`, `https://x/` are rejected; `https://x.ngrok.app`
  is accepted.
- `test_negative_price_rejected`.
- `test_require`: `require(None, "EXA_API_KEY")` raises `ConfigError` with the message
  `"EXA_API_KEY is not set"`. `require(SecretStr("k"), "X")` returns the same object.
- `test_tz_helper`: `tz(Settings(_env_file=None)).key == "America/Chicago"`.

`src/bling/privacy_test.py`
- `test_phone_hash_stable_within_process`: `"+1 (312) 555-1234"` and `"+13125551234"` give the
  same hash. It matches `^ph_[0-9a-f]{12}$` and contains none of `3125551234`.
- `test_phone_hash_differs_across_processes`: run `phone_hash("+13125551234")` in two
  subprocesses (`sys.executable -c`) and assert the outputs differ.
- `test_phone_hash_no_digits`: `phone_hash("anonymous") == "ph_none"`.
- `test_mask_phone` (parametrized): `"+13125551234"` → `"+*******1234"`, `"3125551234"` →
  `"******1234"`, `"123"` → `"****"`, `""` → `"****"`.
- `test_redact_phones` (parametrized, each must become `[phone]` and leave the surrounding text
  intact): `"+13125551234"`, `"+1 312 555 1234"`, `"+1 (312) 555-1234"`, `"+44 20 7946 0958"`,
  `"(312) 555-1234"`, `"312-555-1234"`, `"312.555.1234"`, `"3125551234"`.
- `test_redact_leaves_non_phones` (parametrized, unchanged): `"2026-11-09 18:16:32"`,
  `"2026-11-09T18:16:32Z"`, `"I-90"`, `"Route 66"`, `"arrive by 6:30"`, `"delay 12 min"`,
  `"ZIP 60601"`.
- `test_redact_multiple`: `"from +13125551234 to 312-555-9876"` becomes
  `"from [phone] to [phone]"`.

`src/bling/logs_test.py`
- `test_idempotent`: calling `configure_logging()` twice leaves exactly one root handler with
  `_bling_handler`.
- `test_preserves_foreign_handlers`: a handler without the attribute survives
  `configure_logging()`.
- `test_json_line_shape`: format a record with `extra={"call": "abc", "n": 2}` and `exc_info`
  through `JsonFormatter`. The result `json.loads` to keys in the order
  `ts, level, logger, msg, call, n, exc`. `ts` matches
  `^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z$`. The output contains no `\n`.
- `test_json_redacts`: a message `"sms from +13125551234"`, an extra `body="call 312-555-1234"`,
  and an exception whose text contains `+13125551234` all come out with `[phone]` and with no
  `5551234` anywhere in the line.
- `test_text_redacts`: the same check through `TextFormatter`.
- `test_httpx_quieted`: after `configure_logging("DEBUG")`,
  `logging.getLogger("httpx").level == logging.WARNING`.
- `test_secretstr_extra`: `extra={"k": SecretStr("sk-x")}` renders as `**********`, never
  `sk-x`.

`conftest.py` guard self-test, in `src/bling/config_test.py`:
- `test_network_guard`: `socket.create_connection(("127.0.0.1", 9))` raises
  `RuntimeError("network access in tests")`.
- `test_real_dotenv_not_read`: a bare `Settings()` (default `env_file=".env"`) has every
  secret `None`, even though the repo root may hold a real `.env` and the developer's shell may
  export keys. This proves that both `_clean_env` steps (delenv and chdir) work. It needs no
  import from `conftest`.

## Open questions (resolved)

1. **Env var prefix (`BLING_`) or none?** None. `.env.example` already uses unprefixed
   provider names (`EXA_API_KEY`, `JEV_MODEL`). Bling-only knobs carry a `bling_` field name
   where a bare name would be ambiguous (`bling_region`, `bling_data_dir`).
2. **Default `JEV_MODEL`: `jev-1.13.0` or the newer `jev-1.14.0`?** `jev-1.13.0`. It is what the
   seed and `reference/avicv_jev.py` use. Both are listed live at the same price
   ($0.042 / Mtok), and switching is an env change. Spec 05 may raise the default after it has
   reviewed 1.14.
3. **Jev price default?** `0.042` USD per million input tokens, read from the TypeSafe pricing
   page on 2026-11-09.
4. **Travel and SMS prices?** `0.0` until specs 04 and 08 choose providers and verify their
   prices. A zero is visible in the cost logs, whereas a guessed number would be silently wrong.
5. **Default region and timezone?** `"Chicago, IL"` and `America/Chicago`. The IDEA's
   example trip (Union Station, I-90, the Red Line) is in Chicago, and both are one env change
   away.
6. **How are phone numbers hashed without a secret in `privacy.py`?** An HMAC with a random
   per-process key. An unsalted SHA-256 of a 10-digit number can be reversed by trying every
   number. A configured key would put `.get_secret_value()` outside spec 00's allowlist.
   Correlation within one process is enough for debugging a call.
7. **Where does `conftest.py` go?** At the repo root. Under `src/bling/` the architecture checker
   would flag it as an unknown module, and a root conftest still applies to `testpaths=src`.
8. **Block the network with a plugin (`pytest-socket`) or a fixture?** A 10-line fixture. The
   stack is fixed (AGENT.md), and the fixture covers the only case that matters (TCP connect).
9. **Text or JSON logs by default?** Text. Local `bling ask` and `bling serve` are read by
   people. Spec 11 sets `BLING_LOG_FORMAT=json` for deploy.
10. **`uvicorn[standard]`?** No. Plain uvicorn is enough for one webhook server, and the extras
    (uvloop, httptools, watchfiles) add native builds for no measured gain. Spec 11 may revisit.
11. **Does the TypeSafe SDK use `httpx`, so `respx` can intercept it?** No. `typesafe-sdk`
    0.7.5 depends on **`httpx2`**, a separate package, not `httpx` (its wheel METADATA, read
    2026-11-09). `respx` cannot intercept it. Spec 05 therefore fakes Jev at the `JevClient`
    protocol only. Spec 00's `services_test` "no request" check is amended in this loop:
    respx covers `AsyncExa`, and the TypeSafe client is checked at constructor level. PLAN.md
    hands the details to spec 05.

## References (read live, 2026-11-09)

- uv dependency groups (PEP 735 `[dependency-groups]`, `dev` synced by default):
  https://docs.astral.sh/uv/concepts/projects/dependencies/
- pytest-asyncio configuration (`asyncio_mode`, `asyncio_default_fixture_loop_scope`):
  https://pytest-asyncio.readthedocs.io/en/stable/reference/configuration.html
- PyPI JSON for current versions: `https://pypi.org/pypi/<name>/json`, giving exa-py 2.28.0,
  typesafe-sdk 0.7.5, fastapi 0.162.2, uvicorn 0.54.0, typer 0.29.0, pydantic 2.14.3,
  pydantic-settings 2.16.2 (requires Python ≥ 3.11), httpx 0.28.1, pytest 9.2.0,
  pytest-asyncio 1.4.1.post1, respx 0.23.1, ruff 0.17.4, mypy 2.4.1, hatchling 1.33.0,
  tzdata 2026.6
- exa-py 2.28.0 wheel, `exa_py/api.py`: `AsyncExa(api_key=None, api_base=..., timeout=600.0)`
  and `DEFAULT_REQUEST_TIMEOUT = 600.0`
- typesafe-sdk 0.7.5 wheel: `AsyncTypeSafeClient(api_key, model, retry: RetryPolicy | None,
  timeout: float | httpx2.Timeout | None, transport, http_client, base_url)`,
  `constants.DEFAULT_TIMEOUT = 10.0`, `RetryPolicy.max_retries = 2`, `backoff_max = 5.0`, and
  `Requires-Dist: httpx2>=2.0.0`
- pydantic-settings `env_ignore_empty`: pydantic-settings 2.16.2 `main.py`
- TypeSafe pricing (jev-1.13.0 and jev-1.14.0 at $0.042 / Mtok): https://typesafe.ai/pricing
