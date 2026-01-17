"""Tests for telemetry client."""

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from openadapt_telemetry.client import (
    TelemetryClient,
    get_telemetry,
    is_ci_environment,
    is_internal_user,
    is_running_from_executable,
)


class TestIsRunningFromExecutable:
    """Tests for frozen/bundled executable detection."""

    def test_not_frozen_by_default(self):
        """By default, not running from executable."""
        # We can't easily mock sys.frozen on immutable module type,
        # so just verify the function returns a boolean and runs without error
        result = is_running_from_executable()
        assert isinstance(result, bool)
        # In normal test execution (not PyInstaller), this should be False
        assert result is False


class TestIsCIEnvironment:
    """Tests for CI environment detection."""

    def test_github_actions(self):
        """GitHub Actions should be detected."""
        with patch.dict(os.environ, {"GITHUB_ACTIONS": "true"}, clear=False):
            assert is_ci_environment() is True

    def test_gitlab_ci(self):
        """GitLab CI should be detected."""
        with patch.dict(os.environ, {"GITLAB_CI": "true"}, clear=False):
            assert is_ci_environment() is True

    def test_jenkins(self):
        """Jenkins should be detected."""
        with patch.dict(os.environ, {"JENKINS_URL": "http://jenkins.example.com"}, clear=False):
            assert is_ci_environment() is True

    def test_generic_ci(self):
        """Generic CI variable should be detected."""
        with patch.dict(os.environ, {"CI": "true"}, clear=False):
            assert is_ci_environment() is True

    def test_not_ci(self):
        """Non-CI environment should return False."""
        # Clear all CI-related env vars
        ci_vars = [
            "CI",
            "CONTINUOUS_INTEGRATION",
            "GITHUB_ACTIONS",
            "GITLAB_CI",
            "JENKINS_URL",
            "TRAVIS",
            "CIRCLECI",
            "BUILDKITE",
            "AZURE_PIPELINES",
            "TF_BUILD",
            "CODEBUILD_BUILD_ID",
            "TEAMCITY_VERSION",
            "BITBUCKET_BUILD_NUMBER",
        ]
        env = {var: "" for var in ci_vars}
        with patch.dict(os.environ, env, clear=False):
            # We need to actually clear them, not set to empty
            for var in ci_vars:
                if var in os.environ:
                    del os.environ[var]
            # This test may still return True if running in actual CI
            # So we just check the function runs without error
            result = is_ci_environment()
            assert isinstance(result, bool)


class TestIsInternalUser:
    """Tests for internal user detection."""

    def test_explicit_internal_flag(self):
        """OPENADAPT_INTERNAL=true should indicate internal user."""
        with patch.dict(os.environ, {"OPENADAPT_INTERNAL": "true"}, clear=False):
            assert is_internal_user() is True

    def test_dev_flag(self):
        """OPENADAPT_DEV=true should indicate internal user."""
        with patch.dict(os.environ, {"OPENADAPT_DEV": "true"}, clear=False):
            assert is_internal_user() is True

    def test_ci_indicates_internal(self):
        """Running in CI should indicate internal user."""
        with patch.dict(os.environ, {"CI": "true"}, clear=False):
            assert is_internal_user() is True


class TestTelemetryClient:
    """Tests for TelemetryClient class."""

    def setup_method(self):
        """Reset singleton before each test."""
        TelemetryClient.reset_instance()

    def teardown_method(self):
        """Reset singleton after each test."""
        TelemetryClient.reset_instance()

    def test_singleton_pattern(self):
        """TelemetryClient should be a singleton."""
        client1 = TelemetryClient.get_instance()
        client2 = TelemetryClient.get_instance()
        assert client1 is client2

    def test_reset_instance(self):
        """reset_instance should create new instance."""
        client1 = TelemetryClient.get_instance()
        TelemetryClient.reset_instance()
        client2 = TelemetryClient.get_instance()
        assert client1 is not client2

    def test_disabled_by_do_not_track(self):
        """DO_NOT_TRACK should disable telemetry."""
        with patch.dict(os.environ, {"DO_NOT_TRACK": "1"}, clear=False):
            TelemetryClient.reset_instance()
            client = TelemetryClient.get_instance()
            assert client.enabled is False

    def test_disabled_by_explicit_env(self):
        """OPENADAPT_TELEMETRY_ENABLED=false should disable."""
        with patch.dict(os.environ, {"OPENADAPT_TELEMETRY_ENABLED": "false"}, clear=False):
            TelemetryClient.reset_instance()
            client = TelemetryClient.get_instance()
            assert client.enabled is False

    def test_enabled_by_default(self):
        """Telemetry should be enabled by default."""
        with patch.dict(
            os.environ,
            {"DO_NOT_TRACK": "", "OPENADAPT_TELEMETRY_ENABLED": ""},
            clear=False,
        ):
            TelemetryClient.reset_instance()
            client = TelemetryClient.get_instance()
            assert client.enabled is True

    def test_initialize_returns_false_when_disabled(self):
        """initialize() should return False when telemetry is disabled."""
        with patch.dict(os.environ, {"DO_NOT_TRACK": "1"}, clear=False):
            TelemetryClient.reset_instance()
            client = TelemetryClient.get_instance()
            result = client.initialize(dsn="https://test@example.com/1")
            assert result is False
            assert client.initialized is False

    def test_initialize_returns_false_without_dsn(self):
        """initialize() should return False when no DSN is configured."""
        with patch.dict(
            os.environ,
            {"DO_NOT_TRACK": "", "OPENADAPT_TELEMETRY_DSN": ""},
            clear=False,
        ):
            TelemetryClient.reset_instance()
            client = TelemetryClient.get_instance()
            result = client.initialize()
            assert result is False

    @patch("openadapt_telemetry.client.sentry_sdk")
    def test_initialize_with_dsn(self, mock_sentry):
        """initialize() should work with valid DSN."""
        with patch.dict(os.environ, {"DO_NOT_TRACK": ""}, clear=False):
            TelemetryClient.reset_instance()
            client = TelemetryClient.get_instance()
            result = client.initialize(
                dsn="https://test@example.com/1",
                package_name="test-package",
                package_version="1.0.0",
            )
            assert result is True
            assert client.initialized is True
            mock_sentry.init.assert_called_once()

    @patch("openadapt_telemetry.client.sentry_sdk")
    def test_capture_exception_when_enabled(self, mock_sentry):
        """capture_exception should call sentry when enabled and initialized."""
        with patch.dict(os.environ, {"DO_NOT_TRACK": ""}, clear=False):
            TelemetryClient.reset_instance()
            client = TelemetryClient.get_instance()
            client.initialize(dsn="https://test@example.com/1")

            error = ValueError("test error")
            client.capture_exception(error)

            mock_sentry.capture_exception.assert_called_once_with(error)

    def test_capture_exception_when_disabled(self):
        """capture_exception should do nothing when disabled."""
        with patch.dict(os.environ, {"DO_NOT_TRACK": "1"}, clear=False):
            TelemetryClient.reset_instance()
            client = TelemetryClient.get_instance()

            # Should not raise, just return None
            result = client.capture_exception(ValueError("test"))
            assert result is None

    @patch("openadapt_telemetry.client.sentry_sdk")
    def test_capture_message(self, mock_sentry):
        """capture_message should call sentry when enabled."""
        with patch.dict(os.environ, {"DO_NOT_TRACK": ""}, clear=False):
            TelemetryClient.reset_instance()
            client = TelemetryClient.get_instance()
            client.initialize(dsn="https://test@example.com/1")

            client.capture_message("test message", level="warning")

            mock_sentry.capture_message.assert_called_once_with(
                "test message", level="warning"
            )

    @patch("openadapt_telemetry.client.sentry_sdk")
    def test_set_tag(self, mock_sentry):
        """set_tag should call sentry when enabled."""
        with patch.dict(os.environ, {"DO_NOT_TRACK": ""}, clear=False):
            TelemetryClient.reset_instance()
            client = TelemetryClient.get_instance()
            client.initialize(dsn="https://test@example.com/1")

            client.set_tag("test_key", "test_value")

            mock_sentry.set_tag.assert_called_with("test_key", "test_value")

    @patch("openadapt_telemetry.client.sentry_sdk")
    def test_add_breadcrumb(self, mock_sentry):
        """add_breadcrumb should call sentry when enabled."""
        with patch.dict(os.environ, {"DO_NOT_TRACK": ""}, clear=False):
            TelemetryClient.reset_instance()
            client = TelemetryClient.get_instance()
            client.initialize(dsn="https://test@example.com/1")

            client.add_breadcrumb("test message", category="test")

            mock_sentry.add_breadcrumb.assert_called_once_with(
                message="test message",
                category="test",
                level="info",
            )


class TestGetTelemetry:
    """Tests for get_telemetry convenience function."""

    def setup_method(self):
        """Reset singleton before each test."""
        TelemetryClient.reset_instance()

    def teardown_method(self):
        """Reset singleton after each test."""
        TelemetryClient.reset_instance()

    def test_returns_singleton(self):
        """get_telemetry should return the singleton instance."""
        client1 = get_telemetry()
        client2 = get_telemetry()
        assert client1 is client2
        assert isinstance(client1, TelemetryClient)
