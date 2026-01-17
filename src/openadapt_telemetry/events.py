"""Event types and helpers for OpenAdapt telemetry.

This module provides structured event types for consistent telemetry
across all OpenAdapt packages.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional

from .client import get_telemetry


class EventCategory(str, Enum):
    """Categories of telemetry events."""

    # Error events
    ERROR = "error"
    EXCEPTION = "exception"

    # Feature usage events
    FEATURE = "feature"
    OPERATION = "operation"

    # Performance events
    PERFORMANCE = "performance"
    TIMING = "timing"

    # Lifecycle events
    STARTUP = "startup"
    SHUTDOWN = "shutdown"

    # User interaction events
    COMMAND = "command"
    ACTION = "action"


class EventSeverity(str, Enum):
    """Severity levels for events."""

    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    FATAL = "fatal"


@dataclass
class TelemetryEvent:
    """Structured telemetry event.

    Provides a consistent format for all telemetry events across packages.
    """

    name: str
    category: EventCategory
    severity: EventSeverity = EventSeverity.INFO
    properties: Dict[str, Any] = field(default_factory=dict)
    tags: Dict[str, str] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def send(self) -> Optional[str]:
        """Send this event to the telemetry backend.

        Returns:
            Event ID if sent, None if telemetry is disabled.
        """
        telemetry = get_telemetry()

        # Merge properties
        all_properties = {
            "category": self.category.value,
            "timestamp": self.timestamp.isoformat(),
            **self.properties,
        }

        return telemetry.capture_event(
            event_name=self.name,
            properties=all_properties,
        )


def track_startup(
    package_name: str,
    package_version: str,
    **extra: Any,
) -> Optional[str]:
    """Track package startup event.

    Args:
        package_name: Name of the package starting up.
        package_version: Version of the package.
        **extra: Additional properties to track.

    Returns:
        Event ID if sent.
    """
    event = TelemetryEvent(
        name=f"{package_name}:startup",
        category=EventCategory.STARTUP,
        severity=EventSeverity.INFO,
        properties={
            "package_name": package_name,
            "package_version": package_version,
            **extra,
        },
    )
    return event.send()


def track_shutdown(
    package_name: str,
    uptime_seconds: Optional[float] = None,
    **extra: Any,
) -> Optional[str]:
    """Track package shutdown event.

    Args:
        package_name: Name of the package shutting down.
        uptime_seconds: How long the package was running.
        **extra: Additional properties to track.

    Returns:
        Event ID if sent.
    """
    properties = {"package_name": package_name, **extra}
    if uptime_seconds is not None:
        properties["uptime_seconds"] = uptime_seconds

    event = TelemetryEvent(
        name=f"{package_name}:shutdown",
        category=EventCategory.SHUTDOWN,
        severity=EventSeverity.INFO,
        properties=properties,
    )
    return event.send()


def track_command(
    command_name: str,
    package_name: str,
    success: bool = True,
    duration_ms: Optional[float] = None,
    **extra: Any,
) -> Optional[str]:
    """Track CLI command execution.

    Args:
        command_name: Name of the command executed.
        package_name: Package the command belongs to.
        success: Whether the command succeeded.
        duration_ms: Execution time in milliseconds.
        **extra: Additional properties to track.

    Returns:
        Event ID if sent.
    """
    properties = {
        "command": command_name,
        "package_name": package_name,
        "success": success,
        **extra,
    }
    if duration_ms is not None:
        properties["duration_ms"] = duration_ms

    event = TelemetryEvent(
        name=f"command:{command_name}",
        category=EventCategory.COMMAND,
        severity=EventSeverity.INFO if success else EventSeverity.ERROR,
        properties=properties,
    )
    return event.send()


def track_operation(
    operation_name: str,
    package_name: str,
    success: bool = True,
    duration_ms: Optional[float] = None,
    item_count: Optional[int] = None,
    **extra: Any,
) -> Optional[str]:
    """Track a significant operation.

    Args:
        operation_name: Name of the operation.
        package_name: Package performing the operation.
        success: Whether the operation succeeded.
        duration_ms: Execution time in milliseconds.
        item_count: Number of items processed (if applicable).
        **extra: Additional properties to track.

    Returns:
        Event ID if sent.
    """
    properties = {
        "operation": operation_name,
        "package_name": package_name,
        "success": success,
        **extra,
    }
    if duration_ms is not None:
        properties["duration_ms"] = duration_ms
    if item_count is not None:
        properties["item_count"] = item_count

    event = TelemetryEvent(
        name=f"operation:{operation_name}",
        category=EventCategory.OPERATION,
        severity=EventSeverity.INFO if success else EventSeverity.ERROR,
        properties=properties,
    )
    return event.send()


def track_error(
    error_type: str,
    error_message: str,
    package_name: str,
    recoverable: bool = True,
    **extra: Any,
) -> Optional[str]:
    """Track an error that occurred.

    Note: For exceptions, prefer capture_exception() which includes stack traces.
    This is for logical/business errors that aren't exceptions.

    Args:
        error_type: Type/category of the error.
        error_message: Human-readable error message.
        package_name: Package where the error occurred.
        recoverable: Whether the error is recoverable.
        **extra: Additional properties to track.

    Returns:
        Event ID if sent.
    """
    event = TelemetryEvent(
        name=f"error:{error_type}",
        category=EventCategory.ERROR,
        severity=EventSeverity.ERROR if recoverable else EventSeverity.FATAL,
        properties={
            "error_type": error_type,
            "error_message": error_message,
            "package_name": package_name,
            "recoverable": recoverable,
            **extra,
        },
    )
    return event.send()
