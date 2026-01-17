# Claude Code Instructions for openadapt-telemetry

## Overview

`openadapt-telemetry` provides unified telemetry and error tracking for all OpenAdapt packages. It uses the Sentry SDK for GlitchTip/Sentry compatibility with a privacy-first design.

## Quick Commands

```bash
# Install dependencies
cd /Users/abrichr/oa/src/openadapt-telemetry
pip install -e ".[dev]"

# Run tests
pytest tests/ -v

# Run tests with coverage
pytest tests/ --cov=openadapt_telemetry

# Run linting
ruff check src/
```

## Package Structure

```
openadapt-telemetry/
├── src/openadapt_telemetry/
│   ├── __init__.py           # Public API exports
│   ├── config.py             # Configuration management (env vars, config file)
│   ├── client.py             # TelemetryClient (Sentry wrapper)
│   ├── privacy.py            # PII filtering and scrubbing
│   ├── decorators.py         # Convenience decorators
│   └── events.py             # Event types and helpers
├── tests/
│   ├── conftest.py           # Pytest fixtures
│   ├── test_client.py        # Client tests
│   ├── test_config.py        # Configuration tests
│   ├── test_decorators.py    # Decorator tests
│   └── test_privacy.py       # Privacy filtering tests
├── pyproject.toml            # Package metadata
├── README.md                 # Documentation
└── LICENSE                   # MIT License
```

## Key Components

### TelemetryClient (`client.py`)

The main telemetry client - a singleton that wraps Sentry SDK:

```python
from openadapt_telemetry import get_telemetry

# Initialize once at startup
get_telemetry().initialize(
    dsn="https://xxx@app.glitchtip.com/XXXX",
    package_name="openadapt-mypackage",
    package_version="0.1.0",
)

# Capture exceptions
get_telemetry().capture_exception(exception)

# Capture messages
get_telemetry().capture_message("Operation completed", level="info")

# Set tags
get_telemetry().set_tag("feature", "retrieval")
```

### Privacy Module (`privacy.py`)

Automatic PII scrubbing and path sanitization:

```python
from openadapt_telemetry import sanitize_path, scrub_dict

# Remove usernames from paths
sanitize_path("/Users/john/code/file.py")  # -> "/Users/<user>/code/file.py"

# Scrub sensitive fields
scrub_dict({"password": "secret", "name": "john"})
# -> {"password": "[REDACTED]", "name": "john"}
```

### Decorators (`decorators.py`)

Convenience decorators for common patterns:

```python
from openadapt_telemetry import track_errors, track_performance, track_feature

@track_errors()
def risky_operation():
    """Exceptions are automatically captured."""
    pass

@track_performance("indexing.build")
def build_index():
    """Execution time is tracked."""
    pass

@track_feature("retrieval.search")
def search():
    """Feature usage is recorded."""
    pass
```

### Configuration (`config.py`)

Handles configuration from environment variables and config files:

- `DO_NOT_TRACK=1` - Universal opt-out
- `OPENADAPT_TELEMETRY_ENABLED=false` - Package-specific opt-out
- `OPENADAPT_INTERNAL=true` - Tag as internal usage
- `OPENADAPT_TELEMETRY_DSN` - GlitchTip/Sentry DSN
- `OPENADAPT_TELEMETRY_ENVIRONMENT` - Environment name

Config file location: `~/.config/openadapt/telemetry.json`

## Internal User Detection

The package automatically detects internal/developer usage via:
1. `OPENADAPT_INTERNAL=true` environment variable
2. `OPENADAPT_DEV=true` environment variable
3. Running from source (not frozen executable)
4. Git repository present in working directory
5. CI environment detected (GitHub Actions, GitLab CI, etc.)

Internal users are tagged with `internal: true` for filtering in GlitchTip.

## Testing

Tests use mocks to avoid requiring actual Sentry/GlitchTip connections:

```bash
# Run all tests
pytest tests/ -v

# Run specific test file
pytest tests/test_privacy.py -v

# Run with coverage
pytest tests/ --cov=openadapt_telemetry --cov-report=term-missing
```

## Integration with Other Packages

To integrate telemetry into another OpenAdapt package:

```python
# In package __init__.py
try:
    from openadapt_telemetry import get_telemetry
    get_telemetry().initialize(
        package_name="openadapt-mypackage",
        package_version=__version__,
    )
except ImportError:
    pass  # Telemetry not installed
```

## Dependencies

Core:
- `sentry-sdk>=2.0.0` - Sentry/GlitchTip SDK

Dev:
- `pytest>=8.0.0` - Testing
- `pytest-cov>=4.0.0` - Coverage
- `ruff>=0.1.0` - Linting

## Related Projects

- [openadapt-retrieval](https://github.com/OpenAdaptAI/openadapt-retrieval) - Demo retrieval
- [openadapt-capture](https://github.com/OpenAdaptAI/openadapt-capture) - GUI recording
- [openadapt-ml](https://github.com/OpenAdaptAI/openadapt-ml) - ML training/inference

## References

- [GlitchTip Documentation](https://glitchtip.com/documentation/)
- [Sentry Python SDK](https://docs.sentry.io/platforms/python/)
- [DO_NOT_TRACK Standard](https://consoledonottrack.com/)
