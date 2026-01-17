"""Configuration management for OpenAdapt telemetry.

This module handles configuration from environment variables, config files,
and package defaults following the priority order:
1. Environment variables (highest priority)
2. Configuration file (~/.config/openadapt/telemetry.json)
3. Package defaults (lowest priority)
"""

from __future__ import annotations

import json
import os
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
}

# Config file location
CONFIG_DIR = Path.home() / ".config" / "openadapt"
CONFIG_FILE = CONFIG_DIR / "telemetry.json"


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
    return value.lower() in ("true", "1", "yes", "on")


def _load_config_file() -> dict[str, Any]:
    """Load configuration from file if it exists."""
    if not CONFIG_FILE.exists():
        return {}

    try:
        with open(CONFIG_FILE) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _get_env_config() -> dict[str, Any]:
    """Get configuration from environment variables."""
    config: dict[str, Any] = {}

    # Universal opt-out (DO_NOT_TRACK standard)
    if os.getenv("DO_NOT_TRACK", "").lower() in ("1", "true"):
        config["enabled"] = False

    # Package-specific opt-out
    enabled_env = os.getenv("OPENADAPT_TELEMETRY_ENABLED", "")
    if enabled_env:
        config["enabled"] = _parse_bool(enabled_env)

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

    return config


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

    # Remove None values for fields that should use defaults
    config_dict = {k: v for k, v in merged.items() if v is not None or k == "dsn"}

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
    }

    with open(CONFIG_FILE, "w") as f:
        json.dump(config_dict, f, indent=2)
