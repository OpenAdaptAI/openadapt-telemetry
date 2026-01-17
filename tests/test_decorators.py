"""Tests for telemetry decorators."""

import os
from unittest.mock import MagicMock, patch

import pytest

from openadapt_telemetry.client import TelemetryClient
from openadapt_telemetry.decorators import (
    TelemetrySpan,
    track_errors,
    track_feature,
    track_performance,
)


class TestTrackErrors:
    """Tests for track_errors decorator."""

    def setup_method(self):
        """Reset singleton before each test."""
        TelemetryClient.reset_instance()

    def teardown_method(self):
        """Reset singleton after each test."""
        TelemetryClient.reset_instance()

    def test_reraises_by_default(self):
        """Exceptions should be re-raised by default."""

        @track_errors()
        def failing_function():
            raise ValueError("test error")

        with pytest.raises(ValueError, match="test error"):
            failing_function()

    def test_no_reraise_option(self):
        """Exceptions should not be re-raised when reraise=False."""

        @track_errors(reraise=False)
        def failing_function():
            raise ValueError("test error")

        # Should not raise
        result = failing_function()
        assert result is None

    def test_successful_function(self):
        """Successful functions should work normally."""

        @track_errors()
        def successful_function(x, y):
            return x + y

        result = successful_function(2, 3)
        assert result == 5

    @patch("openadapt_telemetry.decorators.get_telemetry")
    def test_captures_exception_when_enabled(self, mock_get_telemetry):
        """Exceptions should be captured to telemetry."""
        mock_client = MagicMock()
        mock_client.enabled = True
        mock_client.initialized = True
        mock_get_telemetry.return_value = mock_client

        @track_errors()
        def failing_function():
            raise ValueError("test error")

        with pytest.raises(ValueError):
            failing_function()

        mock_client.capture_exception.assert_called_once()


class TestTrackPerformance:
    """Tests for track_performance decorator."""

    def setup_method(self):
        """Reset singleton before each test."""
        TelemetryClient.reset_instance()

    def teardown_method(self):
        """Reset singleton after each test."""
        TelemetryClient.reset_instance()

    def test_returns_function_result(self):
        """Decorated function should return its result."""

        @track_performance()
        def compute(x, y):
            return x * y

        result = compute(3, 4)
        assert result == 12

    def test_custom_name(self):
        """Custom operation name should be usable."""

        @track_performance("custom.operation.name")
        def my_function():
            return "done"

        result = my_function()
        assert result == "done"

    def test_preserves_exceptions(self):
        """Exceptions should propagate through the decorator."""

        @track_performance()
        def failing_function():
            raise RuntimeError("oops")

        with pytest.raises(RuntimeError, match="oops"):
            failing_function()


class TestTrackFeature:
    """Tests for track_feature decorator."""

    def setup_method(self):
        """Reset singleton before each test."""
        TelemetryClient.reset_instance()

    def teardown_method(self):
        """Reset singleton after each test."""
        TelemetryClient.reset_instance()

    def test_returns_function_result(self):
        """Decorated function should return its result."""

        @track_feature("test.feature")
        def get_data():
            return {"key": "value"}

        result = get_data()
        assert result == {"key": "value"}

    @patch("openadapt_telemetry.decorators.get_telemetry")
    def test_captures_event_when_enabled(self, mock_get_telemetry):
        """Feature usage should be captured when telemetry is enabled."""
        mock_client = MagicMock()
        mock_client.enabled = True
        mock_client.initialized = True
        mock_get_telemetry.return_value = mock_client

        @track_feature("test.feature")
        def my_function():
            return "result"

        result = my_function()
        assert result == "result"

        # Check that capture_event was called with the feature name
        mock_client.capture_event.assert_called()
        call_args = mock_client.capture_event.call_args
        assert "feature:test.feature" in call_args[0]


class TestTelemetrySpan:
    """Tests for TelemetrySpan context manager."""

    def setup_method(self):
        """Reset singleton before each test."""
        TelemetryClient.reset_instance()

    def teardown_method(self):
        """Reset singleton after each test."""
        TelemetryClient.reset_instance()

    def test_basic_usage(self):
        """Basic span usage should work."""
        with TelemetrySpan("test_op", "test_span") as span:
            result = 1 + 1

        assert result == 2

    def test_with_description(self):
        """Span with description should work."""
        with TelemetrySpan("op", "name", description="Test description") as span:
            pass

    def test_exception_handling(self):
        """Exceptions should propagate through span."""
        with pytest.raises(ValueError, match="test"):
            with TelemetrySpan("op", "name") as span:
                raise ValueError("test")

    def test_set_tag(self):
        """set_tag should not raise when span is not active."""
        # When telemetry is disabled, _span will be None
        with TelemetrySpan("op", "name") as span:
            span.set_tag("key", "value")  # Should not raise

    def test_set_data(self):
        """set_data should not raise when span is not active."""
        with TelemetrySpan("op", "name") as span:
            span.set_data("key", {"nested": "data"})  # Should not raise
