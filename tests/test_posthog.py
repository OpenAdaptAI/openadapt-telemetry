"""Tests for PostHog usage-event helpers."""

from __future__ import annotations

import os
from unittest.mock import patch

import openadapt_telemetry.posthog as posthog


class _CaptureQueue:
    def __init__(self) -> None:
        self.payload = None

    def put_nowait(self, payload):  # noqa: ANN001
        self.payload = payload


def test_capture_event_respects_do_not_track() -> None:
    with patch.dict(os.environ, {"DO_NOT_TRACK": "1"}, clear=False):
        assert posthog.capture_event("agent_run") is False


def test_capture_event_disabled_in_ci_by_default() -> None:
    with patch.dict(os.environ, {"CI": "1"}, clear=False):
        with patch("openadapt_telemetry.posthog._ensure_worker") as mock_worker:
            assert posthog.capture_event("agent_run") is False
            mock_worker.assert_not_called()


def test_capture_event_enabled_in_ci_with_override() -> None:
    queue = _CaptureQueue()
    with patch.dict(
        os.environ,
        {
            "CI": "1",
            "OPENADAPT_TELEMETRY_IN_CI": "true",
            "OPENADAPT_TELEMETRY_DISTINCT_ID": "test-id",
        },
        clear=False,
    ):
        with patch("openadapt_telemetry.posthog._ensure_worker", return_value=queue):
            assert posthog.capture_event("agent_run", {"mode": "live"}) is True
            assert queue.payload is not None
            assert queue.payload["event"] == "agent_run"
            assert queue.payload["distinct_id"] == "test-id"


def test_capture_event_scrubs_sensitive_properties() -> None:
    queue = _CaptureQueue()
    with patch.dict(
        os.environ,
        {
            "OPENADAPT_TELEMETRY_ENABLED": "true",
            "OPENADAPT_TELEMETRY_DISTINCT_ID": "test-id",
        },
        clear=False,
    ):
        with patch("openadapt_telemetry.posthog._ensure_worker", return_value=queue):
            ok = posthog.capture_event(
                "agent_run",
                {
                    "entrypoint": "oa evals run",
                    "api_key": "should-not-send",
                    "password": "secret",
                },
                package_name="openadapt-evals",
            )
            assert ok is True
            props = queue.payload["properties"]
            assert props["package"] == "openadapt-evals"
            assert props["entrypoint"] == "oa evals run"
            assert "api_key" not in props
            assert "password" not in props
