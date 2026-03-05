"""PostHog usage-event client for OpenAdapt packages.

This module captures lightweight, privacy-safe usage counters (for example:
`agent_run`, `action_executed`, `demo_recorded`) to PostHog ingestion.
"""

from __future__ import annotations

import json
import os
import platform
import queue
import threading
import time
import urllib.error
import urllib.request
import uuid
from importlib import metadata
from pathlib import Path
from typing import Any

from .client import is_ci_environment
from .privacy import scrub_dict

DEFAULT_POSTHOG_HOST = "https://us.i.posthog.com"
DEFAULT_POSTHOG_PROJECT_API_KEY = "phc_935iWKc6O7u6DCp2eFAmK5WmCwv35QXMa6LulTJ3uqh"
DISTINCT_ID_FILE = Path.home() / ".openadapt" / "telemetry_distinct_id"
MAX_STRING_LEN = 256
QUEUE_MAXSIZE = 2048

_event_queue: queue.Queue[dict[str, Any]] | None = None
_worker_started = False
_worker_lock = threading.Lock()


def _is_truthy(raw: str | None) -> bool:
    return str(raw or "").strip().lower() in {"1", "true", "yes", "on"}


def _usage_enabled() -> bool:
    if _is_truthy(os.getenv("DO_NOT_TRACK")):
        return False

    explicit = os.getenv("OPENADAPT_TELEMETRY_ENABLED")
    if explicit is not None:
        return _is_truthy(explicit)

    if is_ci_environment() and not _is_truthy(os.getenv("OPENADAPT_TELEMETRY_IN_CI")):
        return False

    return True


def _posthog_host() -> str:
    return os.getenv("OPENADAPT_POSTHOG_HOST", DEFAULT_POSTHOG_HOST).rstrip("/")


def _posthog_project_api_key() -> str:
    return os.getenv("OPENADAPT_POSTHOG_PROJECT_API_KEY", DEFAULT_POSTHOG_PROJECT_API_KEY)


def _get_distinct_id() -> str:
    env_id = os.getenv("OPENADAPT_TELEMETRY_DISTINCT_ID")
    if env_id:
        return env_id

    try:
        if DISTINCT_ID_FILE.exists():
            existing = DISTINCT_ID_FILE.read_text(encoding="utf-8").strip()
            if existing:
                return existing
        DISTINCT_ID_FILE.parent.mkdir(parents=True, exist_ok=True)
        generated = str(uuid.uuid4())
        DISTINCT_ID_FILE.write_text(generated, encoding="utf-8")
        return generated
    except OSError:
        return str(uuid.uuid4())


def _normalize_value(value: Any) -> Any:
    if value is None or isinstance(value, (int, float, bool)):
        return value
    return str(value)[:MAX_STRING_LEN]


def _sanitize_properties(properties: dict[str, Any] | None) -> dict[str, Any]:
    if not properties:
        return {}
    normalized = {str(k): _normalize_value(v) for k, v in properties.items() if str(k).strip()}
    redacted = scrub_dict(normalized, deep=True, scrub_values=False)
    return {k: v for k, v in redacted.items() if v != "[REDACTED]"}


def _package_version(package_name: str) -> str:
    try:
        return metadata.version(package_name)
    except metadata.PackageNotFoundError:
        return "unknown"


def _base_properties(package_name: str) -> dict[str, Any]:
    return {
        "package": package_name,
        "version": _package_version(package_name),
        "python_version": platform.python_version(),
        "platform": platform.system().lower(),
        "timestamp": int(time.time()),
    }


def _send_payload(payload: dict[str, Any]) -> None:
    timeout_seconds = float(os.getenv("OPENADAPT_TELEMETRY_TIMEOUT_SECONDS", "1.0"))
    req = urllib.request.Request(
        f"{_posthog_host()}/capture/",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "User-Agent": "openadapt-telemetry-posthog/1",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_seconds):
            return
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return


def _worker_loop() -> None:
    assert _event_queue is not None
    while True:
        payload = _event_queue.get()
        _send_payload(payload)
        _event_queue.task_done()


def _ensure_worker() -> queue.Queue[dict[str, Any]]:
    global _event_queue
    global _worker_started

    with _worker_lock:
        if _event_queue is None:
            _event_queue = queue.Queue(maxsize=QUEUE_MAXSIZE)
        if not _worker_started:
            thread = threading.Thread(target=_worker_loop, daemon=True, name="oa-posthog")
            thread.start()
            _worker_started = True
    return _event_queue


def capture_event(
    event: str,
    properties: dict[str, Any] | None = None,
    package_name: str = "openadapt",
) -> bool:
    """Queue a usage event for PostHog ingestion.

    Returns True when queued; False when disabled or dropped.
    """
    event_name = str(event or "").strip()
    if not event_name or not _usage_enabled():
        return False

    payload = {
        "api_key": _posthog_project_api_key(),
        "event": event_name,
        "distinct_id": _get_distinct_id(),
        "properties": {
            **_base_properties(package_name),
            **_sanitize_properties(properties),
        },
    }

    try:
        _ensure_worker().put_nowait(payload)
        return True
    except queue.Full:
        return False


def capture_usage_event(
    event: str,
    properties: dict[str, Any] | None = None,
    package_name: str = "openadapt",
) -> bool:
    """Alias for capture_event to make usage intent explicit."""
    return capture_event(event=event, properties=properties, package_name=package_name)
