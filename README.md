# openadapt-telemetry

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/downloads/)

<!-- PyPI badges (uncomment once package is published)
[![PyPI version](https://img.shields.io/pypi/v/openadapt-telemetry.svg)](https://pypi.org/project/openadapt-telemetry/)
[![Downloads](https://img.shields.io/pypi/dm/openadapt-telemetry.svg)](https://pypi.org/project/openadapt-telemetry/)
-->

Unified telemetry and error tracking for OpenAdapt packages.

## Features

- **Unified Error Tracking**: Consistent error reporting across all OpenAdapt packages
- **Privacy-First Design**: Automatic PII scrubbing and path sanitization
- **Configurable Opt-Out**: Respects `DO_NOT_TRACK` and custom environment variables
- **CI/Dev Mode Detection**: Automatically tags internal usage for filtering
- **GlitchTip/Sentry Compatible**: Uses the Sentry SDK for maximum compatibility

## Installation

```bash
pip install openadapt-telemetry
```

Or with development dependencies:

```bash
pip install openadapt-telemetry[dev]
```

## Quick Start

### Initialize Telemetry

```python
from openadapt_telemetry import get_telemetry

# Initialize once at package startup
get_telemetry().initialize(
    dsn="https://xxx@app.glitchtip.com/XXXX",
    package_name="openadapt-mypackage",
    package_version="0.1.0",
)
```

### Capture Exceptions

```python
from openadapt_telemetry import get_telemetry

try:
    risky_operation()
except Exception as e:
    get_telemetry().capture_exception(e)
    raise
```

### Using Decorators

```python
from openadapt_telemetry import track_errors, track_performance, track_feature

@track_errors()
def process_data(data):
    """Exceptions are automatically captured."""
    return transform(data)

@track_performance("indexing.build_faiss")
def build_index(vectors):
    """Execution time is automatically tracked."""
    return create_index(vectors)

@track_feature("retrieval.add_demo")
def add_demo(demo_id, task):
    """Feature usage is tracked for analytics."""
    save_demo(demo_id, task)
```

### Span Context Manager

```python
from openadapt_telemetry import TelemetrySpan

with TelemetrySpan("indexing", "build_faiss_index") as span:
    span.set_tag("num_vectors", 1000)
    # ... indexing operations ...
```

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DO_NOT_TRACK` | - | Universal opt-out (1 = disabled) |
| `OPENADAPT_TELEMETRY_ENABLED` | `true` | Enable/disable telemetry |
| `OPENADAPT_INTERNAL` | `false` | Tag as internal usage |
| `OPENADAPT_DEV` | `false` | Development mode |
| `OPENADAPT_TELEMETRY_DSN` | - | GlitchTip/Sentry DSN |
| `OPENADAPT_TELEMETRY_ENVIRONMENT` | `production` | Environment name |
| `OPENADAPT_TELEMETRY_SAMPLE_RATE` | `1.0` | Error sampling rate (0.0-1.0) |
| `OPENADAPT_TELEMETRY_TRACES_SAMPLE_RATE` | `0.01` | Performance sampling rate |

### Configuration File

Create `~/.config/openadapt/telemetry.json`:

```json
{
  "enabled": true,
  "internal": false,
  "dsn": "https://xxx@app.glitchtip.com/XXXX",
  "environment": "production",
  "sample_rate": 1.0,
  "traces_sample_rate": 0.01
}
```

### Priority Order

1. Environment variables (highest priority)
2. Configuration file
3. Package defaults (lowest priority)

## Opt-Out

To disable telemetry, set either:

```bash
# Universal standard
export DO_NOT_TRACK=1

# Or package-specific
export OPENADAPT_TELEMETRY_ENABLED=false
```

## Privacy

### What We Collect

| Category | Data | Purpose |
|----------|------|---------|
| Errors | Exception type, stack trace | Bug fixing |
| Performance | Function timing | Optimization |
| Feature Usage | Feature names, counts | Prioritization |
| Environment | OS, Python version | Compatibility |

### What We Never Collect

- Screenshots or images
- Text content or file contents
- Personal information (names, emails, IPs)
- API keys or passwords
- Full file paths with usernames

### Automatic Scrubbing

- File paths have usernames replaced with `<user>`
- Sensitive fields (password, token, api_key, etc.) are redacted
- Email addresses and phone numbers are scrubbed from messages

## Internal Usage Tagging

Internal/developer usage is automatically detected via:

1. `OPENADAPT_INTERNAL=true` environment variable
2. `OPENADAPT_DEV=true` environment variable
3. Running from source (not frozen executable)
4. Git repository present in working directory
5. CI environment detected (GitHub Actions, GitLab CI, etc.)

Filter in GlitchTip:
```
tag:internal IS false  # External users only
tag:internal IS true   # Internal users only
```

## Development

```bash
# Clone and install
git clone https://github.com/OpenAdaptAI/openadapt-telemetry
cd openadapt-telemetry
pip install -e ".[dev]"

# Run tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=openadapt_telemetry
```

## License

MIT License - see [LICENSE](LICENSE) for details.

## Links

- [Documentation](https://github.com/OpenAdaptAI/openadapt-telemetry#readme)
- [Issues](https://github.com/OpenAdaptAI/openadapt-telemetry/issues)
- [GlitchTip](https://glitchtip.com)
- [Sentry SDK](https://docs.sentry.io/platforms/python/)
