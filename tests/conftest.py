"""Pytest configuration and fixtures for telemetry tests."""

import os
from unittest.mock import patch

import pytest
import sentry_sdk
from sentry_sdk.transport import Transport

from openadapt_telemetry.client import TelemetryClient


class CapturingTransport(Transport):
    """Keep every Sentry envelope in memory instead of sending it."""

    envelopes: list = []

    def capture_envelope(self, envelope):
        CapturingTransport.envelopes.append(envelope)


@pytest.fixture
def sentry_events():
    """Route real Sentry clients to memory; return a reader for captured events.

    ``sentry_events("event")`` returns error and message events and
    ``sentry_events("transaction")`` returns transactions, as the server
    would receive them.
    """
    real_init = sentry_sdk.init

    def init(*args, **kwargs):
        kwargs["transport"] = CapturingTransport
        return real_init(*args, **kwargs)

    def read(kind: str) -> list[dict]:
        sentry_sdk.flush()
        return [
            item.payload.json
            for envelope in CapturingTransport.envelopes
            for item in envelope.items
            if item.headers.get("type") == kind
        ]

    CapturingTransport.envelopes = []
    with patch.object(sentry_sdk, "init", init):
        yield read
    sentry_sdk.flush()
    real_init()  # replace the client with one that sends nothing
    TelemetryClient.reset_instance()


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    """Keep tests away from the real ~/.config/openadapt and ~/.openadapt files."""
    config_dir = tmp_path / "config" / "openadapt"
    monkeypatch.setattr("openadapt_telemetry.config.CONFIG_DIR", config_dir)
    monkeypatch.setattr("openadapt_telemetry.config.CONFIG_FILE", config_dir / "telemetry.json")
    monkeypatch.setattr(
        "openadapt_telemetry.posthog.DISTINCT_ID_FILE",
        tmp_path / "openadapt" / "telemetry_distinct_id",
    )


@pytest.fixture(autouse=True)
def reset_telemetry():
    """Reset telemetry singleton before and after each test."""
    TelemetryClient.reset_instance()
    yield
    TelemetryClient.reset_instance()


@pytest.fixture
def clean_env():
    """Provide a clean environment without telemetry-related variables."""
    env_vars_to_clear = [
        "DO_NOT_TRACK",
        "OPENADAPT_TELEMETRY_ENABLED",
        "OPENADAPT_INTERNAL",
        "OPENADAPT_DEV",
        "OPENADAPT_TELEMETRY_DSN",
        "OPENADAPT_TELEMETRY_ENVIRONMENT",
        "OPENADAPT_TELEMETRY_SAMPLE_RATE",
        "OPENADAPT_TELEMETRY_TRACES_SAMPLE_RATE",
    ]

    # Store original values
    original = {var: os.environ.get(var) for var in env_vars_to_clear}

    # Clear the variables
    for var in env_vars_to_clear:
        if var in os.environ:
            del os.environ[var]

    yield

    # Restore original values
    for var, value in original.items():
        if value is not None:
            os.environ[var] = value
        elif var in os.environ:
            del os.environ[var]


@pytest.fixture
def mock_sentry():
    """Mock sentry_sdk for testing."""
    with patch("openadapt_telemetry.client.sentry_sdk") as mock:
        yield mock


@pytest.fixture
def enabled_telemetry(clean_env, mock_sentry):
    """Provide an enabled and initialized telemetry client."""
    client = TelemetryClient.get_instance()
    client.initialize(
        dsn="https://test@example.com/1",
        package_name="test-package",
        package_version="1.0.0",
    )
    return client


@pytest.fixture
def disabled_telemetry():
    """Provide a disabled telemetry client."""
    with patch.dict(os.environ, {"DO_NOT_TRACK": "1"}):
        TelemetryClient.reset_instance()
        client = TelemetryClient.get_instance()
        yield client
