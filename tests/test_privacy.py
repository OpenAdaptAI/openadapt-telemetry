"""Tests for privacy filtering and PII scrubbing."""

import pytest

from openadapt_telemetry.privacy import (
    is_sensitive_key,
    sanitize_path,
    scrub_dict,
    scrub_exception_data,
    scrub_list,
    scrub_string,
)


class TestSanitizePath:
    """Tests for path sanitization."""

    def test_macos_path(self):
        """macOS paths should have username removed."""
        assert sanitize_path("/Users/john/code/file.py") == "/Users/<user>/code/file.py"
        assert sanitize_path("/Users/alice/Documents/project/main.py") == (
            "/Users/<user>/Documents/project/main.py"
        )

    def test_linux_path(self):
        """Linux paths should have username removed."""
        assert sanitize_path("/home/alice/app/main.py") == "/home/<user>/app/main.py"
        assert sanitize_path("/home/bob/.config/openadapt/telemetry.json") == (
            "/home/<user>/.config/openadapt/telemetry.json"
        )

    def test_windows_path_backslash(self):
        """Windows paths with backslashes should have username removed."""
        assert sanitize_path("C:\\Users\\bob\\code\\file.py") == "C:\\Users\\<user>\\code\\file.py"

    def test_windows_path_escaped(self):
        """Windows paths with escaped backslashes should have username removed."""
        assert sanitize_path("C:\\\\Users\\\\bob\\\\code\\\\file.py") == (
            "C:\\\\Users\\\\<user>\\\\code\\\\file.py"
        )

    def test_windows_path_forward_slash(self):
        """Windows paths with forward slashes (git bash) should have username removed."""
        assert sanitize_path("C:/Users/bob/code/file.py") == "C:/Users/<user>/code/file.py"

    def test_non_user_path(self):
        """Paths not in user directories should be unchanged."""
        assert sanitize_path("/usr/local/bin/python") == "/usr/local/bin/python"
        assert sanitize_path("/etc/hosts") == "/etc/hosts"
        assert sanitize_path("/var/log/app.log") == "/var/log/app.log"

    def test_multiple_user_paths(self):
        """Multiple user paths in a string should all be sanitized."""
        path = "/Users/john/code/file.py:/Users/jane/lib/module.py"
        expected = "/Users/<user>/code/file.py:/Users/<user>/lib/module.py"
        assert sanitize_path(path) == expected


class TestIsSensitiveKey:
    """Tests for sensitive key detection."""

    def test_password_variations(self):
        """Password-related keys should be detected."""
        assert is_sensitive_key("password")
        assert is_sensitive_key("PASSWORD")
        assert is_sensitive_key("user_password")
        assert is_sensitive_key("db_password")

    def test_token_variations(self):
        """Token-related keys should be detected."""
        assert is_sensitive_key("token")
        assert is_sensitive_key("access_token")
        assert is_sensitive_key("refresh_token")
        assert is_sensitive_key("api_token")

    def test_api_key_variations(self):
        """API key related keys should be detected."""
        assert is_sensitive_key("api_key")
        assert is_sensitive_key("apikey")
        assert is_sensitive_key("API_KEY")
        assert is_sensitive_key("openai_api_key")

    def test_email_variations(self):
        """Email related keys should be detected."""
        assert is_sensitive_key("email")
        assert is_sensitive_key("user_email")
        assert is_sensitive_key("e-mail")

    def test_non_sensitive_keys(self):
        """Non-sensitive keys should not be flagged."""
        assert not is_sensitive_key("name")
        assert not is_sensitive_key("count")
        assert not is_sensitive_key("status")
        assert not is_sensitive_key("version")
        assert not is_sensitive_key("debug")


class TestScrubString:
    """Tests for string content scrubbing."""

    def test_email_scrubbing(self):
        """Email addresses should be scrubbed."""
        result = scrub_string("Contact user@example.com for help")
        assert "[REDACTED]" in result
        assert "user@example.com" not in result

    def test_phone_scrubbing(self):
        """Phone numbers should be scrubbed."""
        result = scrub_string("Call 555-123-4567 for support")
        assert "[REDACTED]" in result
        assert "555-123-4567" not in result

    def test_credit_card_scrubbing(self):
        """Credit card numbers should be scrubbed."""
        result = scrub_string("Card: 4111-1111-1111-1111")
        assert "[REDACTED]" in result
        assert "4111" not in result

    def test_bearer_token_scrubbing(self):
        """Bearer tokens should be scrubbed."""
        result = scrub_string("Header: Bearer abc123xyz789")
        assert "[REDACTED]" in result
        assert "abc123xyz789" not in result

    def test_non_sensitive_string(self):
        """Non-sensitive strings should pass through."""
        original = "This is a normal log message"
        assert scrub_string(original) == original


class TestScrubDict:
    """Tests for dictionary scrubbing."""

    def test_sensitive_keys_scrubbed(self):
        """Dictionary with sensitive keys should have values redacted."""
        data = {
            "username": "john",
            "password": "secret123",
            "api_key": "sk-abc123",
        }
        result = scrub_dict(data)

        assert result["username"] == "john"
        assert result["password"] == "[REDACTED]"
        assert result["api_key"] == "[REDACTED]"

    def test_nested_dict_scrubbing(self):
        """Nested dictionaries should be scrubbed."""
        data = {
            "user": {
                "name": "john",
                "profile": {
                    "password": "secret",
                    "token": "abc123",
                    "status": "active",
                },
            },
        }
        result = scrub_dict(data, deep=True)

        assert result["user"]["name"] == "john"
        assert result["user"]["profile"]["password"] == "[REDACTED]"
        assert result["user"]["profile"]["token"] == "[REDACTED]"
        assert result["user"]["profile"]["status"] == "active"

    def test_sensitive_key_entire_value_redacted(self):
        """When a key is sensitive, the entire value should be redacted."""
        data = {
            "credentials": {
                "password": "secret",
                "token": "abc123",
            },
        }
        result = scrub_dict(data, deep=True)

        # The entire credentials dict is redacted because the key is sensitive
        assert result["credentials"] == "[REDACTED]"

    def test_scrub_values_option(self):
        """When scrub_values=True, string values should also be scrubbed."""
        data = {
            "log": "User email is user@example.com",
        }
        result = scrub_dict(data, scrub_values=True)
        assert "user@example.com" not in result["log"]


class TestScrubList:
    """Tests for list scrubbing."""

    def test_list_of_dicts_scrubbed(self):
        """List of dictionaries should have sensitive data scrubbed."""
        data = [
            {"name": "john", "password": "secret1"},
            {"name": "jane", "password": "secret2"},
        ]
        result = scrub_list(data)

        assert result[0]["name"] == "john"
        assert result[0]["password"] == "[REDACTED]"
        assert result[1]["name"] == "jane"
        assert result[1]["password"] == "[REDACTED]"

    def test_nested_lists(self):
        """Nested lists should be handled."""
        data = [[{"token": "abc"}], [{"key": "value"}]]
        result = scrub_list(data)

        assert result[0][0]["token"] == "[REDACTED]"
        assert result[1][0]["key"] == "value"


class TestScrubExceptionData:
    """Tests for Sentry exception data scrubbing."""

    def test_stacktrace_path_sanitization(self):
        """Stack trace file paths should be sanitized."""
        exception_data = {
            "values": [
                {
                    "stacktrace": {
                        "frames": [
                            {
                                "filename": "/Users/john/code/app.py",
                                "abs_path": "/Users/john/code/app.py",
                                "lineno": 42,
                            },
                        ],
                    },
                },
            ],
        }
        scrub_exception_data(exception_data)

        frame = exception_data["values"][0]["stacktrace"]["frames"][0]
        assert frame["filename"] == "/Users/<user>/code/app.py"
        assert frame["abs_path"] == "/Users/<user>/code/app.py"

    def test_exception_message_scrubbing(self):
        """Exception messages should have sensitive data scrubbed."""
        exception_data = {
            "values": [
                {
                    "type": "ValueError",
                    "value": "Invalid email: user@example.com",
                },
            ],
        }
        scrub_exception_data(exception_data)

        assert "user@example.com" not in exception_data["values"][0]["value"]

    def test_local_variables_scrubbing(self):
        """Local variables in stack frames should be scrubbed."""
        exception_data = {
            "values": [
                {
                    "stacktrace": {
                        "frames": [
                            {
                                "filename": "app.py",
                                "vars": {
                                    "password": "secret123",
                                    "username": "john",
                                },
                            },
                        ],
                    },
                },
            ],
        }
        scrub_exception_data(exception_data)

        frame = exception_data["values"][0]["stacktrace"]["frames"][0]
        assert frame["vars"]["password"] == "[REDACTED]"
        assert frame["vars"]["username"] == "john"
