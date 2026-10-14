"""Configuration management for OpenAdapt telemetry.

This module handles configuration from environment variables, config files,
and package defaults following the priority order:
1. Environment variables (highest priority)
2. Configuration file (~/.config/openadapt/telemetry.json)
3. Package defaults (lowest priority)

Whether telemetry runs at all is decided by :func:`is_telemetry_allowed`, which
also honors ``[tool.openadapt] telemetry = false`` in the nearest pyproject.toml.
"""

from __future__ import annotations

import json
import os
import secrets
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

# Default configuration values
DEFAULTS = {
    "enabled": True,
    "internal": False,
    "dsn": None,  # Must be provided via env or config
    "environment": "production",
    "sample_rate": 1.0,
    "traces_sample_rate": 0.01,
    "error_tracking": True,
    "performance_tracking": True,
    "feature_usage": True,
    "send_default_pii": False,
    "anon_salt": None,
}

# Config file location
CONFIG_DIR = Path.home() / ".config" / "openadapt"
CONFIG_FILE = CONFIG_DIR / "telemetry.json"
_INVALID_ANON_SALT_WARNED = False


@dataclass
class TelemetryConfig:
    """Configuration for telemetry collection."""

    enabled: bool = True
    internal: bool = False
    dsn: Optional[str] = None
    environment: str = "production"
    sample_rate: float = 1.0
    traces_sample_rate: float = 0.01
    error_tracking: bool = True
    performance_tracking: bool = True
    feature_usage: bool = True
    send_default_pii: bool = False
    anon_salt: Optional[str] = None

    _loaded: bool = field(default=False, repr=False)

    def __post_init__(self) -> None:
        """Validate configuration values."""
        if not 0.0 <= self.sample_rate <= 1.0:
            raise ValueError(f"sample_rate must be between 0.0 and 1.0, got {self.sample_rate}")
        if not 0.0 <= self.traces_sample_rate <= 1.0:
            raise ValueError(
                f"traces_sample_rate must be between 0.0 and 1.0, got {self.traces_sample_rate}"
            )


def _parse_bool(value: str) -> bool:
    """Parse a boolean from a string value."""
    return value.strip().lower() in ("true", "1", "yes", "on")


def _pyproject_opts_out() -> bool:
    """Return True when the nearest pyproject.toml turns telemetry off.

    Walks up from the current directory to the first ``pyproject.toml`` and
    reads::

        [tool.openadapt]
        telemetry = false

    This lets a team commit one file to turn telemetry off for everyone who
    works in the repository.
    """
    try:
        import tomllib
    except ImportError:
        try:
            import tomli as tomllib  # type: ignore[no-redef]
        except ImportError:
            return False

    try:
        cwd = Path.cwd()
    except OSError:
        return False

    for parent in [cwd, *cwd.parents]:
        pyproject = parent / "pyproject.toml"
        if pyproject.is_file():
            try:
                data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
            except Exception:
                return False
            value = data.get("tool", {}).get("openadapt", {}).get("telemetry")
            if value is None:
                return False
            return not _parse_bool(str(value))
    return False


def _file_opts_out(file_config: dict[str, Any]) -> bool:
    """Return True when the config file sets ``"enabled"`` to a false value."""
    value = file_config.get("enabled")
    if isinstance(value, bool):
        return not value
    if isinstance(value, str):
        return not _parse_bool(value)
    return False


def is_telemetry_allowed() -> bool:
    """Apply the opt-out rule shared by error reports and usage events.

    In order of precedence:

    1. ``DO_NOT_TRACK`` set to ``1``, ``true``, ``yes`` or ``on`` turns telemetry off.
    2. ``OPENADAPT_TELEMETRY_ENABLED``, when set, decides.
    3. ``[tool.openadapt] telemetry = false`` in the nearest pyproject.toml turns it off.
    4. ``"enabled": false`` in ~/.config/openadapt/telemetry.json turns it off.

    Otherwise telemetry is allowed.
    """
    if _parse_bool(os.getenv("DO_NOT_TRACK", "")):
        return False
    explicit = os.getenv("OPENADAPT_TELEMETRY_ENABLED", "").strip()
    if explicit:
        return _parse_bool(explicit)
    if _pyproject_opts_out():
        return False
    return not _file_opts_out(_load_config_file())


def _load_config_file() -> dict[str, Any]:
    """Load configuration from file if it exists."""
    if not CONFIG_FILE.exists():
        return {}

    try:
        with open(CONFIG_FILE) as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _get_env_config() -> dict[str, Any]:
    """Get configuration from environment variables."""
    config: dict[str, Any] = {}

    # Package-specific toggle
    enabled_env = os.getenv("OPENADAPT_TELEMETRY_ENABLED", "")
    if enabled_env:
        config["enabled"] = _parse_bool(enabled_env)

    # Universal opt-out (DO_NOT_TRACK standard) always wins.
    if _parse_bool(os.getenv("DO_NOT_TRACK", "")):
        config["enabled"] = False

    # Internal/developer flags
    if os.getenv("OPENADAPT_INTERNAL", "").lower() in ("true", "1", "yes"):
        config["internal"] = True
    if os.getenv("OPENADAPT_DEV", "").lower() in ("true", "1", "yes"):
        config["internal"] = True

    # DSN override
    dsn = os.getenv("OPENADAPT_TELEMETRY_DSN")
    if dsn:
        config["dsn"] = dsn

    # Environment name
    env = os.getenv("OPENADAPT_TELEMETRY_ENVIRONMENT")
    if env:
        config["environment"] = env

    # Sample rates
    sample_rate = os.getenv("OPENADAPT_TELEMETRY_SAMPLE_RATE")
    if sample_rate:
        try:
            config["sample_rate"] = float(sample_rate)
        except ValueError:
            pass

    traces_sample_rate = os.getenv("OPENADAPT_TELEMETRY_TRACES_SAMPLE_RATE")
    if traces_sample_rate:
        try:
            config["traces_sample_rate"] = float(traces_sample_rate)
        except ValueError:
            pass

    # Optional override for deterministic anonymization in controlled environments.
    anon_salt = os.getenv("OPENADAPT_TELEMETRY_ANON_SALT")
    if anon_salt:
        if _is_valid_anon_salt(anon_salt):
            config["anon_salt"] = anon_salt.strip()
        else:
            _warn_invalid_anon_salt_once()

    return config


def _is_valid_anon_salt(value: Any) -> bool:
    """Check whether a salt value is valid for HMAC anonymization."""
    return isinstance(value, str) and len(value.strip()) >= 32


def _warn_invalid_anon_salt_once() -> None:
    """Warn once per process when OPENADAPT_TELEMETRY_ANON_SALT is invalid."""
    global _INVALID_ANON_SALT_WARNED
    if _INVALID_ANON_SALT_WARNED:
        return
    warnings.warn(
        "Ignoring invalid OPENADAPT_TELEMETRY_ANON_SALT; must be >= 32 chars.",
        stacklevel=2,
    )
    _INVALID_ANON_SALT_WARNED = True


def _generate_anon_salt() -> str:
    """Generate a high-entropy random salt."""
    return secrets.token_hex(32)


def get_or_create_anon_salt() -> str:
    """Get anonymization salt from env/config, creating one if missing.

    Priority:
    1. OPENADAPT_TELEMETRY_ANON_SALT (if valid)
    2. telemetry config file `anon_salt` (if valid)
    3. generated and persisted random salt
    """
    env_salt = os.getenv("OPENADAPT_TELEMETRY_ANON_SALT")
    if env_salt:
        if _is_valid_anon_salt(env_salt):
            return env_salt.strip()
        _warn_invalid_anon_salt_once()

    config_data = _load_config_file()
    file_salt = config_data.get("anon_salt")
    if _is_valid_anon_salt(file_salt):
        return str(file_salt).strip()

    generated = _generate_anon_salt()
    config_data["anon_salt"] = generated
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_FILE, "w") as f:
            json.dump(config_data, f, indent=2)
    except OSError:
        warnings.warn(
            "Failed to persist telemetry anonymization salt; using ephemeral salt for this process.",
            stacklevel=2,
        )
    return generated


def load_config() -> TelemetryConfig:
    """Load telemetry configuration from all sources.

    Priority order (highest to lowest):
    1. Environment variables
    2. Configuration file
    3. Package defaults

    Returns:
        TelemetryConfig: The merged configuration.
    """
    # Start with defaults
    merged = dict(DEFAULTS)

    # Layer in config file
    file_config = _load_config_file()
    merged.update(file_config)

    # Layer in environment variables (highest priority)
    env_config = _get_env_config()
    merged.update(env_config)

    # One opt-out rule for every telemetry path (see is_telemetry_allowed).
    merged["enabled"] = is_telemetry_allowed()

    # Remove None values for fields that should use defaults
    config_dict = {k: v for k, v in merged.items() if v is not None or k in {"dsn", "anon_salt"}}

    return TelemetryConfig(**config_dict, _loaded=True)


def save_config(config: TelemetryConfig) -> None:
    """Save configuration to file.

    Args:
        config: The configuration to save.
    """
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    config_dict = {
        "enabled": config.enabled,
        "internal": config.internal,
        "dsn": config.dsn,
        "environment": config.environment,
        "sample_rate": config.sample_rate,
        "traces_sample_rate": config.traces_sample_rate,
        "error_tracking": config.error_tracking,
        "performance_tracking": config.performance_tracking,
        "feature_usage": config.feature_usage,
        "send_default_pii": config.send_default_pii,
        "anon_salt": config.anon_salt,
    }

    with open(CONFIG_FILE, "w") as f:
        json.dump(config_dict, f, indent=2)
