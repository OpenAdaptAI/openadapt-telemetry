"""Tests for telemetry configuration."""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from openadapt_telemetry.config import (
    CONFIG_FILE,
    TelemetryConfig,
    _get_env_config,
    _load_config_file,
    _parse_bool,
    load_config,
    save_config,
)


class TestParseBool:
    """Tests for boolean parsing."""

    def test_true_values(self):
        """Various true string representations."""
        assert _parse_bool("true") is True
        assert _parse_bool("True") is True
        assert _parse_bool("TRUE") is True
        assert _parse_bool("1") is True
        assert _parse_bool("yes") is True
        assert _parse_bool("YES") is True
        assert _parse_bool("on") is True

    def test_false_values(self):
        """Various false string representations."""
        assert _parse_bool("false") is False
        assert _parse_bool("False") is False
        assert _parse_bool("0") is False
        assert _parse_bool("no") is False
        assert _parse_bool("off") is False
        assert _parse_bool("") is False
        assert _parse_bool("anything_else") is False


class TestTelemetryConfig:
    """Tests for TelemetryConfig dataclass."""

    def test_default_values(self):
        """Default configuration values."""
        config = TelemetryConfig()

        assert config.enabled is True
        assert config.internal is False
        assert config.dsn is None
        assert config.environment == "production"
        assert config.sample_rate == 1.0
        assert config.traces_sample_rate == 0.01
        assert config.error_tracking is True
        assert config.performance_tracking is True
        assert config.feature_usage is True
        assert config.send_default_pii is False

    def test_custom_values(self):
        """Custom configuration values."""
        config = TelemetryConfig(
            enabled=False,
            dsn="https://test@example.com/1",
            environment="staging",
            sample_rate=0.5,
        )

        assert config.enabled is False
        assert config.dsn == "https://test@example.com/1"
        assert config.environment == "staging"
        assert config.sample_rate == 0.5

    def test_sample_rate_validation(self):
        """Sample rate must be between 0 and 1."""
        with pytest.raises(ValueError):
            TelemetryConfig(sample_rate=-0.1)

        with pytest.raises(ValueError):
            TelemetryConfig(sample_rate=1.5)

    def test_traces_sample_rate_validation(self):
        """Traces sample rate must be between 0 and 1."""
        with pytest.raises(ValueError):
            TelemetryConfig(traces_sample_rate=-0.1)

        with pytest.raises(ValueError):
            TelemetryConfig(traces_sample_rate=1.5)


class TestEnvConfig:
    """Tests for environment variable configuration."""

    def test_do_not_track(self):
        """DO_NOT_TRACK should disable telemetry."""
        with patch.dict(os.environ, {"DO_NOT_TRACK": "1"}, clear=False):
            config = _get_env_config()
            assert config.get("enabled") is False

        with patch.dict(os.environ, {"DO_NOT_TRACK": "true"}, clear=False):
            config = _get_env_config()
            assert config.get("enabled") is False

    def test_explicit_disable(self):
        """OPENADAPT_TELEMETRY_ENABLED=false should disable."""
        with patch.dict(os.environ, {"OPENADAPT_TELEMETRY_ENABLED": "false"}, clear=False):
            config = _get_env_config()
            assert config.get("enabled") is False

    def test_internal_flag(self):
        """OPENADAPT_INTERNAL should set internal flag."""
        with patch.dict(os.environ, {"OPENADAPT_INTERNAL": "true"}, clear=False):
            config = _get_env_config()
            assert config.get("internal") is True

    def test_dev_flag(self):
        """OPENADAPT_DEV should set internal flag."""
        with patch.dict(os.environ, {"OPENADAPT_DEV": "true"}, clear=False):
            config = _get_env_config()
            assert config.get("internal") is True

    def test_dsn_override(self):
        """OPENADAPT_TELEMETRY_DSN should override DSN."""
        test_dsn = "https://test@custom.example.com/1"
        with patch.dict(os.environ, {"OPENADAPT_TELEMETRY_DSN": test_dsn}, clear=False):
            config = _get_env_config()
            assert config.get("dsn") == test_dsn

    def test_environment_override(self):
        """OPENADAPT_TELEMETRY_ENVIRONMENT should override environment."""
        with patch.dict(os.environ, {"OPENADAPT_TELEMETRY_ENVIRONMENT": "staging"}, clear=False):
            config = _get_env_config()
            assert config.get("environment") == "staging"

    def test_sample_rate_override(self):
        """OPENADAPT_TELEMETRY_SAMPLE_RATE should override sample rate."""
        with patch.dict(os.environ, {"OPENADAPT_TELEMETRY_SAMPLE_RATE": "0.5"}, clear=False):
            config = _get_env_config()
            assert config.get("sample_rate") == 0.5

    def test_invalid_sample_rate_ignored(self):
        """Invalid sample rate values should be ignored."""
        with patch.dict(os.environ, {"OPENADAPT_TELEMETRY_SAMPLE_RATE": "invalid"}, clear=False):
            config = _get_env_config()
            assert "sample_rate" not in config


class TestConfigFile:
    """Tests for configuration file loading."""

    def test_load_nonexistent_file(self):
        """Loading a nonexistent config file should return empty dict."""
        # Mock CONFIG_FILE to a path that doesn't exist
        with patch("openadapt_telemetry.config.CONFIG_FILE", Path("/nonexistent/path/config.json")):
            config = _load_config_file()
            assert config == {}

    def test_load_valid_config(self):
        """Loading a valid config file should work."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"enabled": False, "environment": "test"}, f)
            f.flush()

            with patch("openadapt_telemetry.config.CONFIG_FILE", Path(f.name)):
                config = _load_config_file()
                assert config["enabled"] is False
                assert config["environment"] == "test"

            os.unlink(f.name)

    def test_load_invalid_json(self):
        """Loading invalid JSON should return empty dict."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("not valid json {{{")
            f.flush()

            with patch("openadapt_telemetry.config.CONFIG_FILE", Path(f.name)):
                config = _load_config_file()
                assert config == {}

            os.unlink(f.name)


class TestLoadConfig:
    """Tests for full configuration loading."""

    def test_load_defaults(self):
        """Loading with no config file or env vars should use defaults."""
        with patch.dict(os.environ, {}, clear=True):
            with patch("openadapt_telemetry.config.CONFIG_FILE", Path("/nonexistent/path")):
                config = load_config()

                assert config.enabled is True
                assert config.internal is False
                assert config.environment == "production"

    def test_env_overrides_file(self):
        """Environment variables should override config file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"environment": "staging"}, f)
            f.flush()

            env = {"OPENADAPT_TELEMETRY_ENVIRONMENT": "production"}
            with patch.dict(os.environ, env, clear=False):
                with patch("openadapt_telemetry.config.CONFIG_FILE", Path(f.name)):
                    config = load_config()
                    assert config.environment == "production"

            os.unlink(f.name)


class TestSaveConfig:
    """Tests for configuration saving."""

    def test_save_and_load(self):
        """Saved config should be loadable."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir) / "openadapt"
            config_file = config_dir / "telemetry.json"

            with patch("openadapt_telemetry.config.CONFIG_DIR", config_dir):
                with patch("openadapt_telemetry.config.CONFIG_FILE", config_file):
                    # Save config
                    config = TelemetryConfig(
                        enabled=False,
                        environment="test",
                        sample_rate=0.5,
                    )
                    save_config(config)

                    # Verify file exists
                    assert config_file.exists()

                    # Load and verify
                    loaded = load_config()
                    assert loaded.enabled is False
                    assert loaded.environment == "test"
                    assert loaded.sample_rate == 0.5
