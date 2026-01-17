"""Telemetry client for OpenAdapt packages.

This module provides a unified telemetry interface using the Sentry SDK,
compatible with both Sentry and GlitchTip backends.
"""

from __future__ import annotations

import os
import platform
import sys
from pathlib import Path
from typing import Any, Callable, Dict, Optional

import sentry_sdk
from sentry_sdk.types import Event, Hint

from .config import TelemetryConfig, load_config
from .privacy import create_before_send_filter, sanitize_path


def is_running_from_executable() -> bool:
    """Check if running from a frozen/bundled executable.

    Returns:
        True if running from PyInstaller, cx_Freeze, etc.
    """
    return getattr(sys, "frozen", False) or hasattr(sys, "_MEIPASS")


def is_ci_environment() -> bool:
    """Check if running in a CI/CD environment.

    Detects common CI platforms via environment variables.

    Returns:
        True if running in CI.
    """
    ci_env_vars = [
        "CI",
        "CONTINUOUS_INTEGRATION",
        "GITHUB_ACTIONS",
        "GITLAB_CI",
        "JENKINS_URL",
        "TRAVIS",
        "CIRCLECI",
        "BUILDKITE",
        "AZURE_PIPELINES",
        "TF_BUILD",  # Azure DevOps
        "CODEBUILD_BUILD_ID",  # AWS CodeBuild
        "TEAMCITY_VERSION",
        "BITBUCKET_BUILD_NUMBER",
    ]
    return any(os.getenv(var) for var in ci_env_vars)


def is_internal_user() -> bool:
    """Determine if current usage is from internal team.

    Uses multiple heuristics to detect internal/developer usage:
    1. Explicit OPENADAPT_INTERNAL environment variable
    2. OPENADAPT_DEV environment variable
    3. Not running from frozen executable
    4. Git repository present in current directory
    5. CI environment detected

    Returns:
        True if this appears to be internal usage.
    """
    # Method 1: Explicit environment variable
    if os.getenv("OPENADAPT_INTERNAL", "").lower() in ("true", "1", "yes"):
        return True

    # Method 2: Development environment
    if os.getenv("OPENADAPT_DEV", "").lower() in ("true", "1", "yes"):
        return True

    # Method 3: Not running from executable (indicates dev mode)
    if not is_running_from_executable():
        return True

    # Method 4: Git repository present (development checkout)
    if Path(".git").exists() or Path("../.git").exists():
        return True

    # Method 5: CI/CD environment
    if is_ci_environment():
        return True

    return False


class TelemetryClient:
    """Unified telemetry client for all OpenAdapt packages.

    This client wraps the Sentry SDK and provides:
    - Automatic opt-out detection (DO_NOT_TRACK, etc.)
    - Internal user tagging for filtering
    - Privacy-first data filtering
    - Easy integration with all OpenAdapt packages
    """

    _instance: Optional["TelemetryClient"] = None
    _lock: bool = False

    def __init__(self) -> None:
        """Initialize telemetry client."""
        self._initialized = False
        self._config: Optional[TelemetryConfig] = None
        self._enabled = self._check_enabled()
        self._internal = is_internal_user()

    @classmethod
    def get_instance(cls) -> "TelemetryClient":
        """Get singleton instance of the telemetry client.

        Returns:
            The singleton TelemetryClient instance.
        """
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Reset the singleton instance (useful for testing)."""
        cls._instance = None

    def _check_enabled(self) -> bool:
        """Check if telemetry should be enabled.

        Checks environment variables for opt-out signals.

        Returns:
            True if telemetry should be enabled.
        """
        # Universal opt-out (DO_NOT_TRACK standard)
        if os.getenv("DO_NOT_TRACK", "").lower() in ("1", "true"):
            return False

        # Package-specific opt-out
        if os.getenv("OPENADAPT_TELEMETRY_ENABLED", "").lower() in ("false", "0", "no"):
            return False

        return True

    @property
    def enabled(self) -> bool:
        """Whether telemetry is enabled."""
        return self._enabled

    @property
    def internal(self) -> bool:
        """Whether this is internal/developer usage."""
        return self._internal

    @property
    def initialized(self) -> bool:
        """Whether the client has been initialized."""
        return self._initialized

    @property
    def config(self) -> Optional[TelemetryConfig]:
        """The current telemetry configuration."""
        return self._config

    def initialize(
        self,
        dsn: Optional[str] = None,
        package_name: str = "openadapt",
        package_version: str = "unknown",
        environment: Optional[str] = None,
        **kwargs: Any,
    ) -> bool:
        """Initialize the telemetry client with Sentry SDK.

        This should be called once at package startup. Subsequent calls
        will be ignored unless force=True is passed.

        Args:
            dsn: The Sentry/GlitchTip DSN. If not provided, uses environment
                variable or config file.
            package_name: Name of the package initializing telemetry.
            package_version: Version of the package.
            environment: Environment name (production, staging, development).
            **kwargs: Additional arguments passed to sentry_sdk.init().

        Returns:
            True if initialization succeeded, False if disabled or already initialized.
        """
        if not self._enabled:
            return False

        if self._initialized and not kwargs.get("force", False):
            return True

        # Load configuration
        self._config = load_config()

        # Override with explicit parameters
        if dsn:
            self._config.dsn = dsn
        if environment:
            self._config.environment = environment

        # Skip if no DSN configured
        if not self._config.dsn:
            return False

        # Create privacy filter
        before_send = create_before_send_filter()

        # Initialize Sentry SDK
        sentry_kwargs = {
            "dsn": self._config.dsn,
            "environment": self._config.environment,
            "sample_rate": self._config.sample_rate,
            "traces_sample_rate": self._config.traces_sample_rate,
            "send_default_pii": self._config.send_default_pii,
            "before_send": before_send,
        }

        # Merge in any additional kwargs
        sentry_kwargs.update(kwargs)
        # Remove our internal kwargs
        sentry_kwargs.pop("force", None)

        sentry_sdk.init(**sentry_kwargs)

        # Set default tags
        sentry_sdk.set_tag("internal", self._internal)
        sentry_sdk.set_tag("package", package_name)
        sentry_sdk.set_tag("package_version", package_version)
        sentry_sdk.set_tag("python_version", platform.python_version())
        sentry_sdk.set_tag("os", platform.system())
        sentry_sdk.set_tag("os_version", platform.release())
        sentry_sdk.set_tag("ci", is_ci_environment())

        self._initialized = True
        return True

    def capture_exception(
        self,
        exception: Optional[BaseException] = None,
        **kwargs: Any,
    ) -> Optional[str]:
        """Capture an exception and send to telemetry backend.

        Args:
            exception: The exception to capture. If None, captures the
                current exception from sys.exc_info().
            **kwargs: Additional context passed to Sentry.

        Returns:
            The event ID if sent, None if telemetry is disabled.
        """
        if not self._enabled or not self._initialized:
            return None
        return sentry_sdk.capture_exception(exception, **kwargs)

    def capture_message(
        self,
        message: str,
        level: str = "info",
        **kwargs: Any,
    ) -> Optional[str]:
        """Capture a message and send to telemetry backend.

        Args:
            message: The message to capture.
            level: Log level (debug, info, warning, error, fatal).
            **kwargs: Additional context passed to Sentry.

        Returns:
            The event ID if sent, None if telemetry is disabled.
        """
        if not self._enabled or not self._initialized:
            return None
        return sentry_sdk.capture_message(message, level=level, **kwargs)

    def capture_event(
        self,
        event_name: str,
        properties: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        """Capture a custom event (feature usage tracking).

        Args:
            event_name: Name of the event (e.g., "feature:recording_started").
            properties: Additional properties for the event.

        Returns:
            The event ID if sent, None if telemetry is disabled.
        """
        if not self._enabled or not self._initialized:
            return None

        properties = properties or {}

        with sentry_sdk.push_scope() as scope:
            for key, value in properties.items():
                scope.set_extra(key, value)
            return sentry_sdk.capture_message(
                f"event:{event_name}",
                level="info",
            )

    def set_user(
        self,
        user_id: str,
        **kwargs: Any,
    ) -> None:
        """Set user context for telemetry events.

        Note: Only sets anonymous user ID. Never set email, name, or other PII.

        Args:
            user_id: Anonymous user identifier.
            **kwargs: Additional user properties (id only recommended).
        """
        if not self._enabled or not self._initialized:
            return
        sentry_sdk.set_user({"id": user_id, **kwargs})

    def set_tag(self, key: str, value: str) -> None:
        """Set a custom tag for all subsequent events.

        Args:
            key: Tag name.
            value: Tag value.
        """
        if not self._enabled or not self._initialized:
            return
        sentry_sdk.set_tag(key, value)

    def set_context(self, name: str, context: Dict[str, Any]) -> None:
        """Set additional context for events.

        Args:
            name: Context name.
            context: Context data dictionary.
        """
        if not self._enabled or not self._initialized:
            return
        sentry_sdk.set_context(name, context)

    def add_breadcrumb(
        self,
        message: str,
        category: str = "default",
        level: str = "info",
        **kwargs: Any,
    ) -> None:
        """Add a breadcrumb for debugging context.

        Args:
            message: Breadcrumb message.
            category: Category for grouping breadcrumbs.
            level: Log level.
            **kwargs: Additional breadcrumb data.
        """
        if not self._enabled or not self._initialized:
            return
        sentry_sdk.add_breadcrumb(
            message=message,
            category=category,
            level=level,
            **kwargs,
        )

    def flush(self, timeout: float = 2.0) -> None:
        """Flush pending events to the backend.

        Args:
            timeout: Maximum time to wait in seconds.
        """
        if not self._enabled or not self._initialized:
            return
        sentry_sdk.flush(timeout=timeout)


# Convenience function for singleton access
def get_telemetry() -> TelemetryClient:
    """Get the singleton telemetry client instance.

    Returns:
        The TelemetryClient singleton.
    """
    return TelemetryClient.get_instance()
