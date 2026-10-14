# Data handling reference

This page is for operators, security reviewers and maintainers. The
[README](../README.md) lists what is sent and how to turn it off. This page
gives the rules the code applies, so a reviewer can check them against
`src/openadapt_telemetry/`.

## Opt-out rule

`config.is_telemetry_allowed()` decides whether anything is sent. Error
reports, usage events and automation failure signals all call it. It applies
these checks in order and stops at the first that decides:

1. `DO_NOT_TRACK` set to `1`, `true`, `yes` or `on` (any case): off.
2. `OPENADAPT_TELEMETRY_ENABLED` set to a non-empty value: on for `1`, `true`,
   `yes` or `on`, off for anything else.
3. `telemetry = false` under `[tool.openadapt]` in the nearest `pyproject.toml`,
   searching from the current directory upward: off. Only the nearest file is
   read.
4. `"enabled": false` (or the string `"false"`) in
   `~/.config/openadapt/telemetry.json`: off.
5. Otherwise: on.

Usage events and failure signals have one more rule: in CI (detected from
`CI`, `GITHUB_ACTIONS`, `GITLAB_CI` and other common variables) they stay off
unless `OPENADAPT_TELEMETRY_IN_CI` or `OPENADAPT_TELEMETRY_ENABLED` is true.
Error reports in CI are sent, tagged `ci` and `internal`.

## Error reports

Error reports use the Sentry SDK (2.15 or later) and go to the DSN in
`OPENADAPT_TELEMETRY_DSN`, the config file, or the `dsn` argument of
`initialize()`. There is no default DSN.

`TelemetryClient.initialize()` sets these SDK options, and callers can't
weaken them:

| Option | Value |
|--------|-------|
| `send_default_pii` | SDK default (off). Passing it is refused with a warning. |
| `data_collection` | Not set. Passing it is refused with a warning, because newer SDKs let it override `send_default_pii`. |
| `include_local_variables` | `False` |
| `include_source_context` | `False` |
| `before_send`, `before_send_transaction` | The privacy filter. A caller's own hook runs first and the filter runs last. |

If the filter raises, the event is dropped.

### What the filter does

The filter (`privacy.create_before_send_filter()`) runs on every error,
message and transaction event:

| Event field | Treatment |
|-------------|-----------|
| `server_name` | Removed |
| `message`, `logentry` message, formatted text and arguments | String scrub |
| Exception messages | String scrub |
| Stack frames (exceptions and threads) | Local variables (`vars`) and source lines (`pre_context`, `context_line`, `post_context`) removed. `filename` and `abs_path` lose the user name. File, function and line stay. |
| Breadcrumbs | Message: string scrub. Data: `http.query` and `http.fragment` removed, then key and string scrub. |
| `extra` | `sys.argv` removed, then key and string scrub |
| `contexts` | Key and string scrub, except `trace_id`, `span_id`, `parent_span_id` and the sampling context in `contexts.trace` |
| Transaction spans | Description: string scrub. Data: key and string scrub. Tags: tag rules. |
| `tags` | Tag rules |
| `request` | `query_string` and `cookies` removed. Headers and data: key and string scrub. |
| `user` | Only `id` is kept, replaced by `anon:v2:` and the first 16 hex characters of an HMAC-SHA256 |

**String scrub** (`privacy.scrub_string`) replaces the user name in
`/Users/<name>/`, `/home/<name>/` and `C:\Users\<name>\` paths with `<user>`,
then replaces these with `[REDACTED]`: email addresses, phone numbers, card
numbers, social security numbers, `Bearer` tokens, alphanumeric strings of 32
or more characters, and base64-like strings of 40 or more characters.

**Key scrub** (`privacy.scrub_dict`) replaces the value with `[REDACTED]`
when the key contains any entry of `privacy.PII_DENYLIST`, for example
`password`, `token`, `secret`, `auth`, `cookie`, `session`, `email`, `phone`,
`address`, `ssn` or `credit_card`.

**Tag rules** keep the default tags (`package`, `package_version`,
`python_version`, `os`, `os_version`, `ci`, `internal`), drop keys that are
sensitive or don't match `^[a-zA-Z0-9._:-]{1,64}$`, keep at most 64 tags, and
string-scrub each value and cut it to 256 characters.

## Usage events

`capture_usage_event()` posts this JSON to `<OPENADAPT_POSTHOG_HOST>/capture/`:

| Field | Value |
|-------|-------|
| `api_key` | PostHog project token. OpenAdapt's by default, or `OPENADAPT_POSTHOG_PROJECT_API_KEY`. |
| `event` | Event name given by the caller |
| `distinct_id` | Random UUID saved in `~/.openadapt/telemetry_distinct_id`, or `OPENADAPT_TELEMETRY_DISTINCT_ID` |
| `properties` | `package`, `version`, `python_version`, `platform`, `timestamp` (Unix seconds), the caller's properties, and `$geoip_disable: true` |

Caller properties keep `None`, numbers and booleans as they are. Other values
become strings cut to 256 characters and get the string scrub. Properties
under sensitive keys, and values that are fully redacted, are dropped.

Events go into an in-memory queue of up to 2,048 events and a daemon thread
sends them with a 1-second timeout (`OPENADAPT_TELEMETRY_TIMEOUT_SECONDS`).
Network errors are ignored. Events still queued when the process exits are
not sent.

## Automation failure signals

`capture_automation_failure()` sends a closed-schema description of an
automation failure, for counting how often the same kind of failure recurs
across installs.

```python
from openadapt_telemetry import (
    ActionKind, AutomationFailureSignal, DeliveryState, ExecutionOutcome,
    FailureKind, RiskClass, Substrate, capture_automation_failure,
)

capture_automation_failure(AutomationFailureSignal(
    failure_kind=FailureKind.DELIVERY_UNCERTAIN,
    substrate=Substrate.CITRIX,
    action_kind=ActionKind.CLICK,
    risk_class=RiskClass.CONSEQUENTIAL,
    delivery_state=DeliveryState.UNCERTAIN,
    outcome=ExecutionOutcome.HALTED,
))
```

The event is `automation_failure_observed` with schema
`openadapt.automation-failure-signal/v1`. It carries the base properties of a
usage event (package, versions, platform and send time) and the signal's
fields. Every signal field is an enum, except:

- `runtime_version`: a release identifier such as `1.34.0`, or `unknown`
- `model_calls`: an integer from 0 to 1,000,000
- `external_network_calls`: `none`, `observed` or `unknown`
- `occurred_at`: rounded down to the hour, in UTC

The constructor rejects any other type or value, so application names, window
titles, workflow or step IDs, typed text, screenshots, exception messages and
URLs can't be attached. The `distinct_id` is `failure:` followed by a SHA-256
of the categorical fields, not the install ID, so the event shows that a
failure shape recurred but not which install reported it.

The signal carries none of the run report, screenshots or other evidence;
those stay wherever the caller keeps them. This package only sends the signal
and has no way to act on one, so a signal can't approve or apply a repair.

## Internal usage

Error reports carry an `internal` tag (`True` or `False`) so dashboards can
separate OpenAdapt's own use from outside use. A run counts as internal when
any of these holds:

- `OPENADAPT_INTERNAL` or `OPENADAPT_DEV` is true
- a CI variable is set
- `OPENADAPT_INTERNAL_FROM_GIT` is true and `.git` exists in the current or
  parent directory
- `"internal": true` is in the config file

## Identifiers

| Identifier | Where it comes from | Sent with |
|------------|---------------------|-----------|
| Install ID | Random UUID in `~/.openadapt/telemetry_distinct_id` | Usage events |
| Anonymous user ID | HMAC-SHA256 of the value passed to `set_user()`, keyed with `OPENADAPT_TELEMETRY_ANON_SALT` or a random salt saved as `anon_salt` in the config file | Error reports, only when a package calls `set_user()` |
| Failure signature | SHA-256 of a failure signal's categorical fields | Failure signals |
