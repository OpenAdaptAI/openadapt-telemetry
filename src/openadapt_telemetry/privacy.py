"""Privacy filtering and PII scrubbing for telemetry data.

This module provides utilities for sanitizing sensitive information
before sending telemetry data. It includes:
- Path sanitization (remove usernames from file paths)
- PII scrubbing (remove sensitive field values)
- Content filtering (redact sensitive strings)
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Set


# Sensitive field names that should have their values redacted
PII_DENYLIST: Set[str] = {
    # Authentication
    "password",
    "passwd",
    "pwd",
    "secret",
    "token",
    "api_key",
    "apikey",
    "api-key",
    "access_token",
    "refresh_token",
    "auth",
    "authorization",
    "bearer",
    "credential",
    "credentials",
    # Session/cookies
    "cookie",
    "session",
    "session_id",
    "sessionid",
    "csrf",
    "csrf_token",
    # Personal information
    "email",
    "e-mail",
    "mail",
    "phone",
    "telephone",
    "mobile",
    "address",
    "street",
    "city",
    "zip",
    "zipcode",
    "postal",
    "ssn",
    "social_security",
    "tax_id",
    # Financial
    "credit_card",
    "creditcard",
    "card_number",
    "cvv",
    "cvc",
    "expiry",
    "bank_account",
    "routing_number",
    # Database
    "database_url",
    "db_password",
    "connection_string",
    # Cloud/API
    "aws_secret",
    "aws_access_key",
    "private_key",
    "public_key",
    "encryption_key",
    "signing_key",
}

# Patterns for detecting sensitive data in string values
SENSITIVE_PATTERNS = [
    # Email addresses
    re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"),
    # Phone numbers (various formats)
    re.compile(r"\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b"),
    re.compile(r"\+\d{1,3}[-.\s]?\d{3,14}"),
    # Credit card numbers (basic pattern)
    re.compile(r"\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b"),
    # SSN
    re.compile(r"\b\d{3}[-\s]?\d{2}[-\s]?\d{4}\b"),
    # API keys (common formats)
    re.compile(r"\b[A-Za-z0-9]{32,}\b"),
    # Bearer tokens
    re.compile(r"Bearer\s+[A-Za-z0-9._-]+"),
    # Base64 encoded secrets (heuristic: long base64 strings)
    re.compile(r"[A-Za-z0-9+/]{40,}={0,2}"),
]


def sanitize_path(path: str) -> str:
    """Remove username from file paths.

    Replaces platform-specific user directory patterns with <user> placeholder.

    Args:
        path: The file path to sanitize.

    Returns:
        The sanitized path with username replaced.

    Examples:
        >>> sanitize_path("/Users/john/code/file.py")
        '/Users/<user>/code/file.py'
        >>> sanitize_path("/home/alice/app/main.py")
        '/home/<user>/app/main.py'
        >>> sanitize_path("C:\\\\Users\\\\bob\\\\code\\\\file.py")
        'C:\\\\Users\\\\<user>\\\\code\\\\file.py'
    """
    # macOS: /Users/username/
    path = re.sub(r"/Users/[^/]+/", "/Users/<user>/", path)

    # Linux: /home/username/
    path = re.sub(r"/home/[^/]+/", "/home/<user>/", path)

    # Windows: C:\Users\username\ (handle both escaped and unescaped)
    path = re.sub(r"C:\\Users\\[^\\]+\\", r"C:\\Users\\<user>\\", path)
    path = re.sub(r"C:\\\\Users\\\\[^\\\\]+\\\\", r"C:\\\\Users\\\\<user>\\\\", path)

    # Also handle forward slashes on Windows (git bash, etc.)
    path = re.sub(r"C:/Users/[^/]+/", "C:/Users/<user>/", path)

    return path


def is_sensitive_key(key: str) -> bool:
    """Check if a key name indicates sensitive data.

    Args:
        key: The key/field name to check.

    Returns:
        True if the key suggests sensitive data.
    """
    key_lower = key.lower().replace("-", "_")
    return any(denylist_key in key_lower for denylist_key in PII_DENYLIST)


def scrub_string(value: str) -> str:
    """Scrub sensitive patterns from a string value.

    Args:
        value: The string to scrub.

    Returns:
        The scrubbed string with sensitive patterns replaced.
    """
    for pattern in SENSITIVE_PATTERNS:
        value = pattern.sub("[REDACTED]", value)
    return value


def scrub_dict(
    data: Dict[str, Any],
    deep: bool = True,
    scrub_values: bool = False,
) -> Dict[str, Any]:
    """Scrub sensitive data from a dictionary.

    Args:
        data: The dictionary to scrub.
        deep: Whether to recursively scrub nested dictionaries.
        scrub_values: Whether to also scan string values for sensitive patterns.

    Returns:
        A new dictionary with sensitive data redacted.
    """
    result = {}

    for key, value in data.items():
        if is_sensitive_key(key):
            result[key] = "[REDACTED]"
        elif isinstance(value, dict) and deep:
            result[key] = scrub_dict(value, deep=True, scrub_values=scrub_values)
        elif isinstance(value, list) and deep:
            result[key] = scrub_list(value, scrub_values=scrub_values)
        elif isinstance(value, str):
            if scrub_values:
                result[key] = scrub_string(value)
            else:
                result[key] = value
        else:
            result[key] = value

    return result


def scrub_list(data: List[Any], scrub_values: bool = False) -> List[Any]:
    """Scrub sensitive data from a list.

    Args:
        data: The list to scrub.
        scrub_values: Whether to also scan string values for sensitive patterns.

    Returns:
        A new list with sensitive data redacted.
    """
    result = []

    for item in data:
        if isinstance(item, dict):
            result.append(scrub_dict(item, deep=True, scrub_values=scrub_values))
        elif isinstance(item, list):
            result.append(scrub_list(item, scrub_values=scrub_values))
        elif isinstance(item, str) and scrub_values:
            result.append(scrub_string(item))
        else:
            result.append(item)

    return result


def scrub_exception_data(exception_data: Dict[str, Any]) -> None:
    """Scrub PII from Sentry exception data in place.

    This modifies the exception data dictionary to sanitize:
    - File paths in stack traces
    - Variable values that may contain PII

    Args:
        exception_data: The Sentry exception data dictionary.
    """
    if "values" not in exception_data:
        return

    for value in exception_data["values"]:
        # Sanitize stack trace file paths
        if "stacktrace" in value and "frames" in value["stacktrace"]:
            for frame in value["stacktrace"]["frames"]:
                if "filename" in frame:
                    frame["filename"] = sanitize_path(frame["filename"])
                if "abs_path" in frame:
                    frame["abs_path"] = sanitize_path(frame["abs_path"])

                # Scrub local variables if present
                if "vars" in frame and isinstance(frame["vars"], dict):
                    frame["vars"] = scrub_dict(frame["vars"], deep=True, scrub_values=True)

        # Scrub exception message for sensitive patterns
        if "value" in value and isinstance(value["value"], str):
            value["value"] = scrub_string(value["value"])


def create_before_send_filter():
    """Create a before_send filter function for Sentry.

    Returns:
        A function suitable for use as Sentry's before_send callback.
    """
    from sentry_sdk.types import Event, Hint

    def before_send(event: Event, hint: Hint) -> Optional[Event]:
        """Filter and sanitize events before sending to Sentry/GlitchTip."""
        # Scrub exception data
        if "exception" in event:
            scrub_exception_data(event["exception"])

        # Scrub breadcrumbs
        if "breadcrumbs" in event and "values" in event["breadcrumbs"]:
            for breadcrumb in event["breadcrumbs"]["values"]:
                if "message" in breadcrumb and isinstance(breadcrumb["message"], str):
                    breadcrumb["message"] = scrub_string(breadcrumb["message"])
                if "data" in breadcrumb and isinstance(breadcrumb["data"], dict):
                    breadcrumb["data"] = scrub_dict(
                        breadcrumb["data"], deep=True, scrub_values=True
                    )

        # Scrub extra data
        if "extra" in event and isinstance(event["extra"], dict):
            event["extra"] = scrub_dict(event["extra"], deep=True, scrub_values=True)

        # Scrub contexts
        if "contexts" in event and isinstance(event["contexts"], dict):
            event["contexts"] = scrub_dict(event["contexts"], deep=True, scrub_values=False)

        # Scrub tags
        if "tags" in event and isinstance(event["tags"], dict):
            event["tags"] = scrub_dict(event["tags"], deep=False, scrub_values=False)

        # Scrub request data (if present)
        if "request" in event:
            request = event["request"]
            if "headers" in request:
                request["headers"] = scrub_dict(request["headers"], deep=False, scrub_values=False)
            if "data" in request:
                if isinstance(request["data"], dict):
                    request["data"] = scrub_dict(request["data"], deep=True, scrub_values=True)
                elif isinstance(request["data"], str):
                    request["data"] = scrub_string(request["data"])

        return event

    return before_send
