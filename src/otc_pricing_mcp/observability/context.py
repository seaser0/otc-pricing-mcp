"""Request context management for tracing requests through the MCP system.

Uses Python's contextvars to propagate request_id through async operations
and thread boundaries, enabling request correlation across logs and metrics.
"""

from __future__ import annotations

import contextvars
import uuid
from collections.abc import Generator
from contextlib import contextmanager

# Context variable for storing request_id across async operations
_request_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("request_id", default=None)


def generate_request_id() -> str:
    """Generate a unique request ID using UUIDv4.

    Returns:
        A new request ID string
    """
    return str(uuid.uuid4())


def set_request_id(request_id: str) -> None:
    """Set the request ID in the current context.

    Args:
        request_id: The request ID to set
    """
    _request_id.set(request_id)


def get_request_id() -> str | None:
    """Get the request ID from the current context.

    Returns:
        The current request ID, or None if not set
    """
    return _request_id.get()


@contextmanager
def request_scope(request_id: str | None = None) -> Generator[str, None, None]:
    """Context manager for request scope.

    Automatically generates a request ID if not provided,
    sets it for the duration of the context, and cleans up after.

    Args:
        request_id: Optional request ID. If not provided, generates one.

    Yields:
        The request ID being used
    """
    if request_id is None:
        request_id = generate_request_id()

    token = _request_id.set(request_id)
    try:
        yield request_id
    finally:
        _request_id.reset(token)


def clear_request_id() -> None:
    """Clear the request ID from the current context.

    Used for cleanup after request processing.
    """
    _request_id.set(None)
