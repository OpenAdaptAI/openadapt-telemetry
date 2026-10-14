"""End-to-end checks on what the Sentry SDK would send, using a capturing transport."""

from __future__ import annotations

import logging
import re

import pytest
import sentry_sdk

from openadapt_telemetry import TelemetryClient, TelemetrySpan, get_telemetry, track_performance

HEX32 = re.compile(r"^[0-9a-f]{32}$")


@pytest.fixture
def live_client(clean_env, sentry_events):
    """A real Sentry client whose transport keeps events in memory."""
    TelemetryClient.reset_instance()
    client = get_telemetry()
    assert client.initialize(
        dsn="https://public@example.invalid/1",
        package_name="openadapt-test",
        package_version="1.0.0",
        traces_sample_rate=1.0,
    )
    return client


def _fail(note: str) -> None:
    path = "/Users/alice/records/" + note
    raise FileNotFoundError(f"No such file: {path!r}")


def test_sdk_default_pii_is_off(live_client):
    assert sentry_sdk.get_client().should_send_default_pii() is False


def test_error_event_carries_no_personal_or_application_data(live_client, sentry_events):
    try:
        _fail("visit-notes.txt")
    except FileNotFoundError as exc:
        assert live_client.capture_exception(exc)

    (event,) = sentry_events("event")
    assert "server_name" not in event
    assert "sys.argv" not in event.get("extra", {})
    (exception,) = event["exception"]["values"]
    assert exception["value"] == "No such file: '/Users/<user>/records/visit-notes.txt'"
    for frame in exception["stacktrace"]["frames"]:
        assert not {"vars", "pre_context", "context_line", "post_context"} & set(frame)
        assert "alice" not in frame.get("abs_path", "")
    assert HEX32.match(event["contexts"]["trace"]["trace_id"])
    assert event["tags"]["package"] == "openadapt-test"


def test_release_is_the_package_version_not_a_git_commit(live_client, sentry_events):
    """The tests run inside a git checkout, where the SDK would send its commit hash."""
    live_client.capture_message("hello")
    (event,) = sentry_events("event")
    assert event["release"] == "openadapt-test@1.0.0"


def test_caller_can_set_the_release(clean_env, sentry_events):
    TelemetryClient.reset_instance()
    get_telemetry().initialize(
        dsn="https://public@example.invalid/1", package_name="pkg", release="pkg@abc"
    )
    get_telemetry().capture_message("hello")
    (event,) = sentry_events("event")
    assert event["release"] == "pkg@abc"


def test_transactions_go_through_the_privacy_filter(live_client, sentry_events):
    @track_performance("indexing.build")
    def build():
        with TelemetrySpan("indexing", "load") as span:
            span.set_data("source", "/home/alice/data.csv")
            span.set_data("api_key", "abc")
        return 1

    build()

    (transaction,) = sentry_events("transaction")
    assert transaction["transaction"] == "indexing.build"
    assert "server_name" not in transaction
    assert "sys.argv" not in transaction.get("extra", {})
    assert HEX32.match(transaction["contexts"]["trace"]["trace_id"])
    (span,) = transaction["spans"]
    assert span["data"]["source"] == "/home/<user>/data.csv"
    assert span["data"]["api_key"] == "[REDACTED]"


def test_log_arguments_and_url_queries_are_scrubbed(live_client, sentry_events):
    logging.getLogger("openadapt-test").error(
        "save failed for %s (%s)", "/Users/alice/out.json", "alice@example.com"
    )
    sentry_sdk.add_breadcrumb(
        type="http",
        category="httplib",
        data={"url": "https://emr.example/api/visits", "http.query": "token=abc123"},
    )
    live_client.capture_message("after request")

    log_event, message_event = sentry_events("event")
    assert log_event["logentry"]["params"] == ["/Users/<user>/out.json", "[REDACTED]"]
    assert "alice" not in log_event["logentry"].get("formatted", "")
    (http,) = [b for b in message_event["breadcrumbs"]["values"] if b.get("type") == "http"]
    assert http["data"] == {"url": "https://emr.example/api/visits"}
