# openadapt-telemetry

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/downloads/)
[![PyPI version](https://img.shields.io/pypi/v/openadapt-telemetry.svg)](https://pypi.org/project/openadapt-telemetry/)
[![Downloads](https://img.shields.io/pypi/dm/openadapt-telemetry.svg)](https://pypi.org/project/openadapt-telemetry/)

Error reports and usage counts for OpenAdapt packages. Data is filtered on the
user's machine before it is sent, and `DO_NOT_TRACK=1` turns everything off.

- **If you run OpenAdapt**, see [what is sent](#what-is-sent) and
  [how to turn it off](#turn-it-off).
- **If you build an OpenAdapt package**, the quick start below sends error
  reports to your GlitchTip or Sentry project. Other Python projects can use it
  the same way with their own DSN.

## Quick start

```bash
pip install openadapt-telemetry
export OPENADAPT_TELEMETRY_DSN="https://<key>@app.glitchtip.com/<project-id>"
```

```python
from openadapt_telemetry import get_telemetry

telemetry = get_telemetry()
telemetry.initialize(package_name="mypackage", package_version="0.1.0")

try:
    open("/Users/alice/notes.txt")
except OSError as exc:
    telemetry.capture_exception(exc)
```

GlitchTip receives
`FileNotFoundError: [Errno 2] No such file or directory: '/Users/<user>/notes.txt'`
with the file, function and line of each stack frame. Without a DSN, or after
an opt-out, `initialize()` returns `False` and nothing is sent.

To see the filter without a DSN:

```python
>>> from openadapt_telemetry import scrub_string
>>> scrub_string("Saved /Users/alice/notes.txt for alice@example.com")
'Saved /Users/<user>/notes.txt for [REDACTED]'
```

## Turn it off

Any one of these turns off both error reports and usage events:

| Where | Setting |
|-------|---------|
| Environment | `DO_NOT_TRACK=1` (or `true`, `yes`, `on`) |
| Environment | `OPENADAPT_TELEMETRY_ENABLED=false` |
| `pyproject.toml` of a repository, for everyone who works in it | `telemetry = false` under `[tool.openadapt]` |
| `~/.config/openadapt/telemetry.json` | `{"enabled": false}` |

`DO_NOT_TRACK` overrides everything else. `OPENADAPT_TELEMETRY_ENABLED=true`
overrides the two files. Usage events are also off in CI unless
`OPENADAPT_TELEMETRY_IN_CI=true` or `OPENADAPT_TELEMETRY_ENABLED=true`. Code can
check the result with `openadapt_telemetry.is_telemetry_allowed()`.

## What is sent

| | Error reports | Usage events |
|-|---------------|--------------|
| Destination | The GlitchTip or Sentry project named by the DSN. With no DSN, nothing is sent. | OpenAdapt's PostHog project, unless `OPENADAPT_POSTHOG_PROJECT_API_KEY` names another one |
| When | After `initialize()`: on `capture_exception` or `capture_message`, an uncaught exception, an `ERROR` log record, or a `track_*` decorator or `TelemetrySpan` | When a package calls `capture_usage_event` |
| Contents | Exception type and message; file, function and line of each stack frame; recent log lines and HTTP request URLs; timings; package, Python and OS versions; names and versions of installed Python packages; whether the run looks internal or CI | Event name; package, Python and OS versions; a timestamp; a random install ID kept in `~/.openadapt/telemetry_distinct_id`; the properties the package passes |
| Removed before sending | User names in home-directory paths; emails, phone, card and social security numbers, bearer tokens and long key-like strings; values under keys such as `password`, `token` or `email`; the host name; the command line; local variable values; source code lines; URL query strings | Properties under sensitive keys; the same patterns in property values. Strings are cut to 256 characters. |

Data-handling details, including the closed-schema automation failure signal
(`capture_automation_failure`), are in
[docs/COMPLIANCE.md](https://github.com/OpenAdaptAI/openadapt-telemetry/blob/main/docs/COMPLIANCE.md).

## Usage events

```python
from openadapt_telemetry import capture_usage_event

capture_usage_event("demo_recorded", properties={"steps": 12}, package_name="mypackage")
```

A background thread sends the event with a 1-second timeout, so a slow or
unreachable server doesn't block the caller. The function returns `False` when
telemetry is off or the queue is full.

## Decorators and spans

```python
from openadapt_telemetry import TelemetrySpan, track_errors, track_feature, track_performance

@track_errors()  # report exceptions, then re-raise
def process(data): ...

@track_performance("indexing.build")  # record a timed transaction
def build_index(vectors): ...

@track_feature("retrieval.add_demo")  # count each call
def add_demo(demo_id): ...

with TelemetrySpan("indexing", "load_vectors") as span:
    span.set_data("count", 1000)
```

These do nothing until `initialize()` succeeds.

## Configuration

Environment variables take precedence over `~/.config/openadapt/telemetry.json`,
which takes precedence over the defaults.

| Variable | Default | Effect |
|----------|---------|--------|
| `DO_NOT_TRACK` | unset | `1`, `true`, `yes` or `on` turns off all telemetry |
| `OPENADAPT_TELEMETRY_ENABLED` | unset (on) | `false` turns telemetry off; `true` overrides the opt-out files |
| `OPENADAPT_TELEMETRY_DSN` | none | GlitchTip or Sentry DSN for error reports |
| `OPENADAPT_TELEMETRY_ENVIRONMENT` | `production` | Environment name on error reports |
| `OPENADAPT_TELEMETRY_SAMPLE_RATE` | `1.0` | Share of errors sent (0.0 to 1.0) |
| `OPENADAPT_TELEMETRY_TRACES_SAMPLE_RATE` | `0.01` | Share of performance transactions sent |
| `OPENADAPT_TELEMETRY_IN_CI` | `false` | Send usage events from CI |
| `OPENADAPT_POSTHOG_PROJECT_API_KEY` | OpenAdapt's project | PostHog project token (`phc_...`) for usage events |
| `OPENADAPT_POSTHOG_HOST` | `https://us.i.posthog.com` | PostHog ingestion host |
| `OPENADAPT_TELEMETRY_DISTINCT_ID` | random UUID | Install ID for usage events |
| `OPENADAPT_TELEMETRY_TIMEOUT_SECONDS` | `1.0` | Network timeout for usage events |
| `OPENADAPT_INTERNAL`, `OPENADAPT_DEV` | `false` | Tag error reports as internal |
| `OPENADAPT_INTERNAL_FROM_GIT` | `false` | Tag error reports as internal when run from a git checkout |
| `OPENADAPT_TELEMETRY_ANON_SALT` | random, saved in the config file | Key for hashing user IDs passed to `set_user` (32 characters or more) |

The config file takes these keys:

```json
{
  "enabled": true,
  "internal": false,
  "dsn": "https://<key>@app.glitchtip.com/<project-id>",
  "environment": "production",
  "sample_rate": 1.0,
  "traces_sample_rate": 0.01
}
```

## Limits

- The string filter matches patterns. It doesn't recognize names, addresses or
  other free text, so an exception message such as `no record for Jane Doe` is
  sent as written.
- URL paths in HTTP breadcrumbs are kept, so an identifier in a path (for
  example `/patients/123`) is sent.
- GlitchTip, Sentry and PostHog see the IP address of each connection, as any
  web server does. The library doesn't put IP addresses in events and asks
  PostHog not to look up location.

## Development

```bash
git clone https://github.com/OpenAdaptAI/openadapt-telemetry
cd openadapt-telemetry
pip install -e ".[dev]"
pytest
ruff check .
```

## License

MIT. See [LICENSE](https://github.com/OpenAdaptAI/openadapt-telemetry/blob/main/LICENSE).
