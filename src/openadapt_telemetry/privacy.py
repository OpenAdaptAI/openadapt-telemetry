"""Privacy filtering and PII scrubbing for telemetry data.

This module provides utilities for sanitizing sensitive information
before sending telemetry data. It includes:
- Path sanitization (remove usernames from file paths)
- PII scrubbing (remove sensitive field values)
- Content filtering (redact sensitive strings)
"""

from __future__ import annotations

import hashlib
import hmac
import re
from functools import lru_cache
from typing import Any, Dict, List, Optional, Set

from .config import get_or_create_anon_salt

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

# Whitelisted tags that retain observability value and are safe to keep.
ALLOWED_OBSERVABILITY_KEYS: Set[str] = {
    "package",
    "package_version",
    "python_version",
    "os",
    "os_version",
    "ci",
    "internal",
}

ANON_VERSION = "v2"
TAG_KEY_PATTERN = re.compile(r"^[a-zA-Z0-9._:-]{1,64}$")
MAX_TAGS = 64
MAX_TAG_VALUE_CHARS = 256


@lru_cache(maxsize=1)
def _get_anon_salt_cached() -> str:
    """Memoize anon salt lookup to avoid repeated filesystem reads."""
    return get_or_create_anon_salt()


def _is_already_anonymized(value: str, prefix: str = "anon") -> bool:
    """Return True only for canonical anonymous ID formats."""
    escaped_prefix = re.escape(prefix)
    patterns = (
        rf"^{escaped_prefix}:v2:[0-9a-f]{{16}}$",
        rf"^{escaped_prefix}:v1:[0-9a-f]{{16}}$",
        rf"^{escaped_prefix}:[0-9a-f]{{16}}$",
        rf"^{escaped_prefix}:v2:unknown$",
    )
    return any(re.match(pattern, value) for pattern in patterns)


def _scrub_top_level_messages(event: Dict[str, Any]) -> None:
    """Scrub top-level message fields that may contain free-form text."""
    if isinstance(event.get("message"), str):
        event["message"] = scrub_string(event["message"])
    if isinstance(event.get("logentry"), dict):
        logentry = event["logentry"]
        if isinstance(logentry.get("message"), str):
            logentry["message"] = scrub_string(logentry["message"])
        if isinstance(logentry.get("formatted"), str):
            logentry["formatted"] = scrub_string(logentry["formatted"])
        # Arguments of a log call such as logging.error("failed for %s", path).
        params = logentry.get("params")
        if isinstance(params, (list, tuple)):
            logentry["params"] = scrub_list(list(params), scrub_values=True)
        elif isinstance(params, dict):
            logentry["params"] = scrub_dict(params, deep=True, scrub_values=True)


def _is_safe_tag_key(key: Any) -> bool:
    """Return True when a tag key is safe to keep."""
    if not isinstance(key, str):
        return False
    if not TAG_KEY_PATTERN.match(key):
        return False
    if is_sensitive_key(key):
        return False
    return True


def _normalize_tag_value(value: Any) -> str:
    """Convert a tag value to a scrubbed bounded string."""
    scrubbed = scrub_string(str(value))
    return scrubbed[:MAX_TAG_VALUE_CHARS]


def _scrub_tags(tags: Dict[str, Any]) -> Dict[str, Any]:
    """Keep safe tags, scrub values, and bound payload size."""
    sanitized: Dict[str, Any] = {}
    dropped_count = 0

    # Preserve explicitly listed observability keys first so they survive capping.
    for key in ALLOWED_OBSERVABILITY_KEYS:
        if key in tags and _is_safe_tag_key(key):
            sanitized[key] = _normalize_tag_value(tags[key])

    for key, value in tags.items():
        if key in sanitized:
            continue
        if len(sanitized) >= MAX_TAGS:
            dropped_count += 1
            continue
        if not _is_safe_tag_key(key):
            dropped_count += 1
            continue
        sanitized[key] = _normalize_tag_value(value)

    # Keep hard cap strict, including metadata markers.
    if dropped_count > 0 and len(sanitized) < MAX_TAGS:
        sanitized["_dropped_tag_count"] = str(dropped_count)

    return sanitized


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

    Removes the user name from home-directory paths, then replaces emails,
    phone numbers, card numbers, SSNs, bearer tokens and long key-like strings
    with ``[REDACTED]``.

    Args:
        value: The string to scrub.

    Returns:
        The scrubbed string with sensitive patterns replaced.
    """
    value = sanitize_path(value)
    for pattern in SENSITIVE_PATTERNS:
        value = pattern.sub("[REDACTED]", value)
    return value


def anonymize_identifier(value: str, prefix: str = "anon") -> str:
    """Deterministically anonymize an identifier using versioned HMAC-SHA256."""
    normalized = str(value or "").strip()
    if not normalized:
        return f"{prefix}:{ANON_VERSION}:unknown"
    if _is_already_anonymized(normalized, prefix=prefix):
        return normalized

    salt = _get_anon_salt_cached()
    digest = hmac.new(
        salt.encode("utf-8"),
        normalized.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()[:16]
    return f"{prefix}:{ANON_VERSION}:{digest}"


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
        elif isinstance(value, tuple) and deep:
            result[key] = tuple(scrub_list(list(value), scrub_values=scrub_values))
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
        elif isinstance(item, tuple):
            result.append(tuple(scrub_list(list(item), scrub_values=scrub_values)))
        elif isinstance(item, str) and scrub_values:
            result.append(scrub_string(item))
        else:
            result.append(item)

    return result


# Stack-frame fields that can carry application data rather than code location:
# local variable values and the source lines around each frame.
FRAME_CONTENT_KEYS = ("vars", "pre_context", "context_line", "post_context")


def _scrub_stacktrace(stacktrace: Any) -> None:
    """Keep only code locations in stack frames, with user names removed."""
    if not isinstance(stacktrace, dict) or not isinstance(stacktrace.get("frames"), list):
        return
    for frame in stacktrace["frames"]:
        if not isinstance(frame, dict):
            continue
        for key in FRAME_CONTENT_KEYS:
            frame.pop(key, None)
        if isinstance(frame.get("filename"), str):
            frame["filename"] = sanitize_path(frame["filename"])
        if isinstance(frame.get("abs_path"), str):
            frame["abs_path"] = sanitize_path(frame["abs_path"])


def scrub_exception_data(exception_data: Dict[str, Any]) -> None:
    """Scrub PII from Sentry exception data in place.

    This modifies the exception data dictionary to:
    - Remove user names from file paths in stack traces
    - Drop local variable values and source lines from stack frames
    - Scrub sensitive patterns from exception messages

    Args:
        exception_data: The Sentry exception data dictionary.
    """
    if "values" not in exception_data:
        return

    for value in exception_data["values"]:
        _scrub_stacktrace(value.get("stacktrace"))

        # Scrub exception message for sensitive patterns
        if "value" in value and isinstance(value["value"], str):
            value["value"] = scrub_string(value["value"])


# HTTP breadcrumb fields that hold the query string or fragment of a URL.
URL_DETAIL_KEYS = ("http.query", "http.fragment")


# Trace identifiers are random hex. The key-like pattern in SENSITIVE_PATTERNS
# would replace them, which breaks the link between errors and traces.
TRACE_CONTEXT_KEYS = ("trace_id", "span_id", "parent_span_id", "dynamic_sampling_context")


def _scrub_contexts(contexts: Dict[str, Any]) -> Dict[str, Any]:
    """Scrub event contexts but keep trace identifiers intact."""
    scrubbed = scrub_dict(contexts, deep=True, scrub_values=True)
    trace = contexts.get("trace")
    if isinstance(trace, dict) and isinstance(scrubbed.get("trace"), dict):
        for key in TRACE_CONTEXT_KEYS:
            if key in trace:
                scrubbed["trace"][key] = trace[key]
    return scrubbed


def _scrub_spans(spans: List[Any]) -> None:
    """Scrub span descriptions, data and tags in a transaction in place."""
    for span in spans:
        if not isinstance(span, dict):
            continue
        if isinstance(span.get("description"), str):
            span["description"] = scrub_string(span["description"])
        if isinstance(span.get("data"), dict):
            span["data"] = scrub_dict(span["data"], deep=True, scrub_values=True)
        if isinstance(span.get("tags"), dict):
            span["tags"] = _scrub_tags(span["tags"])


def create_before_send_filter():
    """Create a before_send filter function for Sentry.

    The same function also serves as ``before_send_transaction``.

    Returns:
        A function suitable for use as Sentry's before_send callback.
    """
    from sentry_sdk.types import Event, Hint

    def before_send(event: Event, hint: Hint) -> Optional[Event]:
        """Filter and sanitize events before sending to Sentry/GlitchTip."""
        try:
            # The host name often contains the user's name (for example
            # "alices-macbook"), so it is never sent.
            event.pop("server_name", None)

            _scrub_top_level_messages(event)

            # Scrub exception data
            if "exception" in event:
                scrub_exception_data(event["exception"])

            # Thread stack traces (attach_stacktrace) get the same treatment.
            threads = event.get("threads")
            if isinstance(threads, dict) and isinstance(threads.get("values"), list):
                for thread in threads["values"]:
                    if isinstance(thread, dict):
                        _scrub_stacktrace(thread.get("stacktrace"))

            # Scrub breadcrumbs. Query strings and fragments of HTTP requests
            # often carry tokens or record IDs, so they are dropped.
            if "breadcrumbs" in event and "values" in event["breadcrumbs"]:
                for breadcrumb in event["breadcrumbs"]["values"]:
                    if "message" in breadcrumb and isinstance(breadcrumb["message"], str):
                        breadcrumb["message"] = scrub_string(breadcrumb["message"])
                    if "data" in breadcrumb and isinstance(breadcrumb["data"], dict):
                        data = {
                            k: v
                            for k, v in breadcrumb["data"].items()
                            if k not in URL_DETAIL_KEYS
                        }
                        breadcrumb["data"] = scrub_dict(data, deep=True, scrub_values=True)

            # Scrub extra data. Command-line arguments can name files or carry
            # user text, so the SDK's sys.argv entry is dropped.
            if "extra" in event and isinstance(event["extra"], dict):
                extra = {k: v for k, v in event["extra"].items() if k != "sys.argv"}
                event["extra"] = scrub_dict(extra, deep=True, scrub_values=True)

            # Scrub contexts
            if "contexts" in event and isinstance(event["contexts"], dict):
                event["contexts"] = _scrub_contexts(event["contexts"])

            # Scrub transaction spans
            if isinstance(event.get("spans"), list):
                _scrub_spans(event["spans"])

            # Scrub tags (allowlist + scrub values)
            if "tags" in event and isinstance(event["tags"], dict):
                event["tags"] = _scrub_tags(event["tags"])

            # Scrub request data (if present)
            if "request" in event and isinstance(event["request"], dict):
                request = event["request"]
                request.pop("query_string", None)
                request.pop("cookies", None)
                if "headers" in request:
                    if isinstance(request["headers"], dict):
                        request["headers"] = scrub_dict(
                            request["headers"], deep=False, scrub_values=True
                        )
                    elif isinstance(request["headers"], list):
                        request["headers"] = scrub_list(request["headers"], scrub_values=True)
                    elif isinstance(request["headers"], str):
                        request["headers"] = scrub_string(request["headers"])
                if "data" in request:
                    if isinstance(request["data"], dict):
                        request["data"] = scrub_dict(request["data"], deep=True, scrub_values=True)
                    elif isinstance(request["data"], list):
                        request["data"] = scrub_list(request["data"], scrub_values=True)
                    elif isinstance(request["data"], str):
                        request["data"] = scrub_string(request["data"])

            # Keep only anonymous user IDs (drop all other user attributes).
            if "user" in event and isinstance(event["user"], dict):
                user_id = event["user"].get("id")
                event["user"] = {"id": anonymize_identifier(str(user_id))} if user_id else {}

            return event
        except Exception:
            # Fail closed on privacy filter errors.
            return None

    return before_send
