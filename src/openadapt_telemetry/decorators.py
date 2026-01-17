"""Convenience decorators for telemetry tracking.

This module provides decorators for easily adding telemetry to functions:
- track_performance: Track function execution time
- track_errors: Automatically capture exceptions
- track_feature: Track feature usage
"""

from __future__ import annotations

import functools
import time
from typing import Any, Callable, Optional, TypeVar, Union

import sentry_sdk

from .client import get_telemetry

F = TypeVar("F", bound=Callable[..., Any])


def track_performance(
    name: Optional[str] = None,
    op: str = "function",
) -> Callable[[F], F]:
    """Decorator to track function performance.

    Wraps the function in a Sentry transaction to measure execution time.

    Args:
        name: Transaction name. Defaults to function name.
        op: Operation type for grouping in Sentry.

    Returns:
        Decorated function.

    Example:
        @track_performance("retrieval.build_index")
        def build_index(self):
            ...
    """

    def decorator(func: F) -> F:
        operation_name = name or func.__name__

        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            telemetry = get_telemetry()

            # If telemetry is disabled, just run the function
            if not telemetry.enabled or not telemetry.initialized:
                return func(*args, **kwargs)

            with sentry_sdk.start_transaction(op=op, name=operation_name) as transaction:
                start = time.perf_counter()
                try:
                    result = func(*args, **kwargs)
                    transaction.set_status("ok")
                    return result
                except Exception as e:
                    transaction.set_status("internal_error")
                    raise
                finally:
                    duration = time.perf_counter() - start
                    sentry_sdk.set_measurement("duration_ms", duration * 1000, "millisecond")

        return wrapper  # type: ignore

    return decorator


def track_errors(
    reraise: bool = True,
    capture_args: bool = False,
) -> Callable[[F], F]:
    """Decorator to automatically capture exceptions.

    Wraps the function to capture any exceptions to telemetry.

    Args:
        reraise: Whether to re-raise the exception after capturing.
        capture_args: Whether to include function arguments in error context.
            Warning: May expose sensitive data if enabled.

    Returns:
        Decorated function.

    Example:
        @track_errors(reraise=True)
        def process_data(data):
            ...
    """

    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            telemetry = get_telemetry()

            try:
                return func(*args, **kwargs)
            except Exception as e:
                if telemetry.enabled and telemetry.initialized:
                    scope = sentry_sdk.get_current_scope()
                    scope.set_tag("function", func.__name__)
                    scope.set_tag("module", func.__module__)

                    if capture_args:
                        # Warning: may expose sensitive data
                        scope.set_extra("args", repr(args)[:500])
                        scope.set_extra("kwargs", repr(kwargs)[:500])

                    telemetry.capture_exception(e)

                if reraise:
                    raise

        return wrapper  # type: ignore

    return decorator


def track_feature(
    feature_name: str,
    include_result: bool = False,
) -> Callable[[F], F]:
    """Decorator to track feature usage.

    Records when a feature/function is used for analytics.

    Args:
        feature_name: Name of the feature being tracked.
        include_result: Whether to include (sanitized) result info.

    Returns:
        Decorated function.

    Example:
        @track_feature("retrieval.add_demo")
        def add_demo(self, demo_id, task, screenshot=None):
            ...
    """

    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            telemetry = get_telemetry()

            # Track feature usage
            if telemetry.enabled and telemetry.initialized:
                properties = {
                    "function": func.__name__,
                    "module": func.__module__,
                }

                telemetry.capture_event(
                    f"feature:{feature_name}",
                    properties,
                )

            # Execute the function
            result = func(*args, **kwargs)

            # Optionally track result info
            if include_result and telemetry.enabled and telemetry.initialized:
                result_info = {}
                if result is not None:
                    result_info["result_type"] = type(result).__name__
                    if hasattr(result, "__len__"):
                        result_info["result_length"] = len(result)

                telemetry.capture_event(
                    f"feature:{feature_name}:completed",
                    result_info,
                )

            return result

        return wrapper  # type: ignore

    return decorator


class TelemetrySpan:
    """Context manager for tracking a span of operations.

    Example:
        with TelemetrySpan("indexing", "build_faiss_index") as span:
            span.set_tag("num_vectors", 1000)
            # ... indexing operations ...
    """

    def __init__(
        self,
        op: str,
        name: str,
        description: Optional[str] = None,
    ) -> None:
        """Initialize the telemetry span.

        Args:
            op: Operation type.
            name: Span name.
            description: Optional description.
        """
        self.op = op
        self.name = name
        self.description = description
        self._span: Optional[Any] = None
        self._start_time: float = 0

    def __enter__(self) -> "TelemetrySpan":
        """Enter the span context."""
        telemetry = get_telemetry()

        self._start_time = time.perf_counter()

        if telemetry.enabled and telemetry.initialized:
            self._span = sentry_sdk.start_span(
                op=self.op,
                name=self.name,
                description=self.description,
            )
            self._span.__enter__()

        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Exit the span context."""
        duration = time.perf_counter() - self._start_time

        if self._span is not None:
            if exc_type is not None:
                self._span.set_status("internal_error")
            else:
                self._span.set_status("ok")

            self._span.set_measurement("duration_ms", duration * 1000, "millisecond")
            self._span.__exit__(exc_type, exc_val, exc_tb)

    def set_tag(self, key: str, value: str) -> None:
        """Set a tag on the span."""
        if self._span is not None:
            self._span.set_tag(key, value)

    def set_data(self, key: str, value: Any) -> None:
        """Set data on the span."""
        if self._span is not None:
            self._span.set_data(key, value)
