from __future__ import annotations

import json
import os
from unittest.mock import patch

import pytest

from openadapt_telemetry.failure_signals import (
    FAILURE_SIGNAL_EVENT,
    ActionKind,
    AutomationFailureSignal,
    DeliveryState,
    EffectTier,
    ExecutionOutcome,
    ExecutionProfile,
    FailureKind,
    IdentityState,
    ResolutionRung,
    RiskClass,
    Substrate,
    capture_automation_failure,
)


class _CaptureQueue:
    def __init__(self) -> None:
        self.payload = None

    def put_nowait(self, payload):  # noqa: ANN001
        self.payload = payload


def _signal(**overrides) -> AutomationFailureSignal:  # noqa: ANN003
    values = {
        "failure_kind": FailureKind.DELIVERY_UNCERTAIN,
        "substrate": Substrate.CITRIX,
        "action_kind": ActionKind.CLICK,
        "risk_class": RiskClass.CONSEQUENTIAL,
        "resolution_rung": ResolutionRung.OCR,
        "identity_state": IdentityState.VERIFIED,
        "effect_tier": EffectTier.PERSISTED_REACQUISITION,
        "delivery_state": DeliveryState.UNCERTAIN,
        "execution_profile": ExecutionProfile.REGULATED,
        "outcome": ExecutionOutcome.HALTED,
        "runtime_version": "1.23.0",
        "model_calls": 0,
        "external_network_calls": "none",
        "occurred_at": "2026-07-26T19:37:22+00:00",
    }
    values.update(overrides)
    return AutomationFailureSignal(**values)


def test_envelope_is_closed_coarse_and_deterministic() -> None:
    signal = _signal()
    envelope = signal.to_envelope()
    assert envelope["occurred_at"] == "2026-07-26T19:00:00Z"
    assert (
        envelope["failure_signature"]
        == _signal(runtime_version="1.24.0", occurred_at="2026-08-01T10:00:00Z").failure_signature
    )
    forbidden = {
        "tenant",
        "workflow",
        "step",
        "application",
        "origin",
        "message",
        "exception",
        "text",
        "screenshot",
        "parameter",
        "evidence",
    }
    serialized = json.dumps(envelope, sort_keys=True).lower()
    assert all(term not in serialized for term in forbidden)


def test_invalid_free_form_inputs_fail_closed() -> None:
    with pytest.raises(TypeError, match="failure_kind"):
        _signal(failure_kind="patient john smith")
    with pytest.raises(ValueError, match="runtime_version"):
        _signal(runtime_version="patient@example.com")


def test_capture_groups_by_failure_not_installation() -> None:
    queue = _CaptureQueue()
    with patch.dict(
        os.environ,
        {
            "OPENADAPT_TELEMETRY_ENABLED": "true",
            "OPENADAPT_TELEMETRY_DISTINCT_ID": "must-not-leave",
        },
        clear=False,
    ):
        with patch("openadapt_telemetry.posthog._ensure_worker", return_value=queue):
            signal = _signal()
            assert capture_automation_failure(signal) is True
    assert queue.payload["event"] == FAILURE_SIGNAL_EVENT
    assert queue.payload["distinct_id"] == f"failure:{signal.failure_signature}"
    assert "must-not-leave" not in json.dumps(queue.payload)


def test_capture_respects_do_not_track() -> None:
    with patch.dict(os.environ, {"DO_NOT_TRACK": "1"}, clear=False):
        assert capture_automation_failure(_signal()) is False
