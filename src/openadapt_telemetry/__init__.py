"""OpenAdapt Telemetry - Unified error tracking and telemetry for OpenAdapt packages.

This package provides a privacy-first telemetry system for all OpenAdapt packages,
using GlitchTip/Sentry SDK for error tracking and performance monitoring.

Features:
- Unified error tracking across all packages
- Privacy-first design with automatic PII scrubbing
- Configurable opt-out (DO_NOT_TRACK, OPENADAPT_TELEMETRY_ENABLED)
- CI/dev mode detection for filtering internal usage
- Convenient decorators for tracking errors, performance, and features

Quick Start:
    from openadapt_telemetry import get_telemetry

    # Initialize telemetry (typically in package __init__.py)
    get_telemetry().initialize(
        dsn="https://xxx@app.glitchtip.com/XXXX",
        package_name="openadapt-mypackage",
        package_version="0.1.0",
    )

    # Capture exceptions
    try:
        risky_operation()
    except Exception as e:
        get_telemetry().capture_exception(e)
        raise

Decorators:
    from openadapt_telemetry import track_errors, track_performance, track_feature

    @track_errors()
    def process_data(data):
        ...

    @track_performance("indexing.build_faiss")
    def build_index(vectors):
        ...

    @track_feature("retrieval.add_demo")
    def add_demo(demo_id, task):
        ...

Opt-out:
    # Environment variable opt-out
    export DO_NOT_TRACK=1
    # Or
    export OPENADAPT_TELEMETRY_ENABLED=false
"""

from openadapt_telemetry.client import (
    TelemetryClient,
    get_telemetry,
    is_ci_environment,
    is_internal_user,
    is_running_from_executable,
)
from openadapt_telemetry.config import (
    CONFIG_DIR,
    CONFIG_FILE,
    DEFAULTS,
    TelemetryConfig,
    load_config,
    save_config,
)
from openadapt_telemetry.decorators import (
    TelemetrySpan,
    track_errors,
    track_feature,
    track_performance,
)
from openadapt_telemetry.events import (
    EventCategory,
    EventSeverity,
    TelemetryEvent,
    track_command,
    track_error,
    track_operation,
    track_shutdown,
    track_startup,
)
from openadapt_telemetry.privacy import (
    PII_DENYLIST,
    create_before_send_filter,
    is_sensitive_key,
    sanitize_path,
    scrub_dict,
    scrub_exception_data,
    scrub_list,
    scrub_string,
)

__version__ = "0.1.0"

__all__ = [
    # Version
    "__version__",
    # Client
    "TelemetryClient",
    "get_telemetry",
    "is_ci_environment",
    "is_internal_user",
    "is_running_from_executable",
    # Config
    "TelemetryConfig",
    "load_config",
    "save_config",
    "CONFIG_DIR",
    "CONFIG_FILE",
    "DEFAULTS",
    # Privacy
    "sanitize_path",
    "scrub_dict",
    "scrub_list",
    "scrub_string",
    "scrub_exception_data",
    "is_sensitive_key",
    "create_before_send_filter",
    "PII_DENYLIST",
    # Decorators
    "track_errors",
    "track_performance",
    "track_feature",
    "TelemetrySpan",
    # Events
    "TelemetryEvent",
    "EventCategory",
    "EventSeverity",
    "track_startup",
    "track_shutdown",
    "track_command",
    "track_operation",
    "track_error",
]
