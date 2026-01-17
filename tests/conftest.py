"""Pytest configuration and fixtures for telemetry tests."""

import os
from unittest.mock import patch

import pytest

from openadapt_telemetry.client import TelemetryClient


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
