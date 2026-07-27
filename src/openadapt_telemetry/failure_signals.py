"""Closed, privacy-safe automation failure signals.

The full run report, screenshots, OCR, workflow parameters, application names,
target origins, exception messages, and exact step/workflow identifiers stay in
the declared execution boundary.  This module emits only a coarse structural
signature assembled from enums.  The signature can reveal recurrence without
becoming a customer evidence channel.

This is discovery telemetry, not repair authorization.  A recurring signal may
open a reviewed repair candidate, but it can never promote a patch or weaken an
identity, effect, risk, or policy contract.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from .posthog import _base_properties, _queue_capture_payload, _usage_enabled

FAILURE_SIGNAL_SCHEMA = "openadapt.automation-failure-signal/v1"
FAILURE_SIGNAL_EVENT = "automation_failure_observed"
_RELEASE_RE = re.compile(r"^[0-9A-Za-z][0-9A-Za-z.+_-]{0,63}$")


class _ValueEnum(str, Enum):
    def __str__(self) -> str:
        return self.value


class FailureKind(_ValueEnum):
    RUNTIME_BUG = "runtime_bug"
    RESOLUTION_AMBIGUOUS = "resolution_ambiguous"
    TARGET_NOT_FOUND = "target_not_found"
    STALE_STATE = "stale_state"
    IDENTITY_REFUTED = "identity_refuted"
    IDENTITY_UNVERIFIABLE = "identity_unverifiable"
    DELIVERY_UNCERTAIN = "delivery_uncertain"
    EFFECT_REFUTED = "effect_refuted"
    EFFECT_UNVERIFIABLE = "effect_unverifiable"
    AUTHORIZATION_REFUSED = "authorization_refused"
    INFRASTRUCTURE_FAILURE = "infrastructure_failure"
    OPERATOR_OVER_HALT = "operator_over_halt"
    WRONG_EFFECT_DETECTED = "wrong_effect_detected"


class Substrate(_ValueEnum):
    WEB = "web"
    WINDOWS = "windows"
    MACOS = "macos"
    LINUX = "linux"
    RDP = "rdp"
    CITRIX = "citrix"
    MIXED = "mixed"
    UNKNOWN = "unknown"


class ActionKind(_ValueEnum):
    CLICK = "click"
    DOUBLE_CLICK = "double_click"
    RIGHT_CLICK = "right_click"
    DRAG = "drag"
    TYPE = "type"
    KEY = "key"
    HOTKEY = "hotkey"
    WAIT = "wait"
    SCROLL = "scroll"
    NAVIGATE = "navigate"
    API = "api"
    MCP = "mcp"
    TOOL = "tool"
    FILE = "file"
    CLIPBOARD = "clipboard"
    UNKNOWN = "unknown"


class RiskClass(_ValueEnum):
    READ_ONLY = "read_only"
    STATE_CHANGING = "state_changing"
    CONSEQUENTIAL = "consequential"
    IRREVERSIBLE = "irreversible"
    UNKNOWN = "unknown"


class ResolutionRung(_ValueEnum):
    STRUCTURAL = "structural"
    TEMPLATE = "template"
    OCR = "ocr"
    GEOMETRY = "geometry"
    GROUNDER = "grounder"
    NONE = "none"
    UNKNOWN = "unknown"


class IdentityState(_ValueEnum):
    VERIFIED = "verified"
    REFUTED = "refuted"
    UNVERIFIABLE = "unverifiable"
    NOT_REQUIRED = "not_required"
    UNKNOWN = "unknown"


class EffectTier(_ValueEnum):
    INDEPENDENT_SYSTEM = "tier_1"
    INDEPENDENT_SESSION = "tier_2"
    PERSISTED_REACQUISITION = "tier_3"
    IMMEDIATE_SCREEN = "tier_4"
    NONE = "none"
    UNKNOWN = "unknown"


class DeliveryState(_ValueEnum):
    NOT_ATTEMPTED = "not_attempted"
    CONFIRMED = "confirmed"
    UNCERTAIN = "uncertain"
    UNKNOWN = "unknown"


class ExecutionProfile(_ValueEnum):
    DEMO = "demo"
    STANDARD = "standard"
    REGULATED = "regulated"
    UNKNOWN = "unknown"


class ExecutionOutcome(_ValueEnum):
    VERIFIED = "VERIFIED"
    COMPLETED_UNVERIFIED = "COMPLETED_UNVERIFIED"
    HALTED = "HALTED"
    FAILED = "FAILED"
    ROLLED_BACK = "ROLLED_BACK"


_SEVERITY = {
    FailureKind.RUNTIME_BUG: "error",
    FailureKind.RESOLUTION_AMBIGUOUS: "warning",
    FailureKind.TARGET_NOT_FOUND: "warning",
    FailureKind.STALE_STATE: "warning",
    FailureKind.IDENTITY_REFUTED: "warning",
    FailureKind.IDENTITY_UNVERIFIABLE: "warning",
    FailureKind.DELIVERY_UNCERTAIN: "critical",
    FailureKind.EFFECT_REFUTED: "critical",
    FailureKind.EFFECT_UNVERIFIABLE: "error",
    FailureKind.AUTHORIZATION_REFUSED: "warning",
    FailureKind.INFRASTRUCTURE_FAILURE: "error",
    FailureKind.OPERATOR_OVER_HALT: "info",
    FailureKind.WRONG_EFFECT_DETECTED: "critical",
}


def _hour_bucket(value: datetime | None) -> str:
    current = value or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    current = current.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)
    return current.isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class AutomationFailureSignal:
    """A coarse failure observation safe for aggregate recurrence analysis."""

    failure_kind: FailureKind
    substrate: Substrate
    action_kind: ActionKind = ActionKind.UNKNOWN
    risk_class: RiskClass = RiskClass.UNKNOWN
    resolution_rung: ResolutionRung = ResolutionRung.UNKNOWN
    identity_state: IdentityState = IdentityState.UNKNOWN
    effect_tier: EffectTier = EffectTier.UNKNOWN
    delivery_state: DeliveryState = DeliveryState.UNKNOWN
    execution_profile: ExecutionProfile = ExecutionProfile.UNKNOWN
    outcome: ExecutionOutcome = ExecutionOutcome.HALTED
    runtime_version: str = "unknown"
    model_calls: int = 0
    external_network_calls: str = "unknown"
    occurred_at: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.failure_kind, FailureKind):
            raise TypeError("failure_kind must be a FailureKind")
        for name, enum_type in (
            ("substrate", Substrate),
            ("action_kind", ActionKind),
            ("risk_class", RiskClass),
            ("resolution_rung", ResolutionRung),
            ("identity_state", IdentityState),
            ("effect_tier", EffectTier),
            ("delivery_state", DeliveryState),
            ("execution_profile", ExecutionProfile),
            ("outcome", ExecutionOutcome),
        ):
            if not isinstance(getattr(self, name), enum_type):
                raise TypeError(f"{name} must be a {enum_type.__name__}")
        if self.runtime_version != "unknown" and not _RELEASE_RE.fullmatch(self.runtime_version):
            raise ValueError("runtime_version must be a bounded release identifier")
        if not isinstance(self.model_calls, int) or not 0 <= self.model_calls <= 1_000_000:
            raise ValueError("model_calls must be a bounded non-negative integer")
        if self.external_network_calls not in {"none", "observed", "unknown"}:
            raise ValueError("external_network_calls must be none, observed, or unknown")
        if self.occurred_at:
            parsed = datetime.fromisoformat(self.occurred_at.replace("Z", "+00:00"))
            object.__setattr__(self, "occurred_at", _hour_bucket(parsed))
        else:
            object.__setattr__(self, "occurred_at", _hour_bucket(None))

    @property
    def failure_signature(self) -> str:
        """Cross-install recurrence key derived from closed categories only."""
        basis = {
            "schema": FAILURE_SIGNAL_SCHEMA,
            "failure_kind": self.failure_kind.value,
            "substrate": self.substrate.value,
            "action_kind": self.action_kind.value,
            "risk_class": self.risk_class.value,
            "resolution_rung": self.resolution_rung.value,
            "identity_state": self.identity_state.value,
            "effect_tier": self.effect_tier.value,
            "delivery_state": self.delivery_state.value,
            "execution_profile": self.execution_profile.value,
            "outcome": self.outcome.value,
        }
        encoded = json.dumps(basis, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode()).hexdigest()

    def to_envelope(self) -> dict[str, Any]:
        """Return the exact schema-limited egress envelope."""
        values = asdict(self)
        return {
            "schema": FAILURE_SIGNAL_SCHEMA,
            "failure_signature": self.failure_signature,
            "failure_kind": self.failure_kind.value,
            "severity": _SEVERITY[self.failure_kind],
            "substrate": self.substrate.value,
            "action_kind": self.action_kind.value,
            "risk_class": self.risk_class.value,
            "resolution_rung": self.resolution_rung.value,
            "identity_state": self.identity_state.value,
            "effect_tier": self.effect_tier.value,
            "delivery_state": self.delivery_state.value,
            "execution_profile": self.execution_profile.value,
            "outcome": self.outcome.value,
            "runtime_version": values["runtime_version"],
            "model_calls": values["model_calls"],
            "external_network_calls": values["external_network_calls"],
            "occurred_at": values["occurred_at"],
        }


def capture_automation_failure(
    signal: AutomationFailureSignal,
    *,
    package_name: str = "openadapt-flow",
) -> bool:
    """Queue a closed failure signal while honoring the standard opt-out.

    The PostHog ``distinct_id`` is the coarse failure signature itself, not an
    installation, user, workflow, or tenant pseudonym.  Consequently this event
    supports recurrence counts but cannot be used to reconstruct who observed
    it.  No raw evidence is accepted by this API.
    """
    if not isinstance(signal, AutomationFailureSignal):
        raise TypeError("signal must be an AutomationFailureSignal")
    if not _usage_enabled():
        return False
    return _queue_capture_payload(
        event=FAILURE_SIGNAL_EVENT,
        distinct_id=f"failure:{signal.failure_signature}",
        properties={
            **_base_properties(package_name),
            **signal.to_envelope(),
        },
    )
