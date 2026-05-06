"""Structured logging configuration for OTC Pricing MCP.

Uses structlog for JSON output, enabling machine-readable logs
for debugging, monitoring, and continuous improvement.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

import structlog

from .context import get_request_id


def add_request_id(logger: Any, method_name: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    """Add request_id from context to every log message."""
    request_id = get_request_id()
    if request_id:
        event_dict["request_id"] = request_id
    return event_dict


def configure_logging(log_level: str = "INFO") -> None:
    """Configure structlog for JSON output with context propagation.

    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR)
    """
    # Configure standard library logging to use structlog
    timestamper = structlog.processors.TimeStamper(fmt="iso")

    shared_processors = [
        add_request_id,  # Add request_id from context
        structlog.contextvars.merge_contextvars,  # Merge context vars
        structlog.processors.add_log_level,  # Add log level
        structlog.processors.StackInfoRenderer(),  # Add stack info if present
        structlog.processors.format_exc_info,  # Format exceptions
        timestamper,  # Add timestamp
    ]

    structlog.configure(
        processors=shared_processors  # type: ignore[arg-type]
        + [
            structlog.processors.JSONRenderer(),  # JSON output
        ],
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=False,
        wrapper_class=structlog.make_filtering_bound_logger(int(getattr(logging, log_level))),
    )

    # Configure standard library logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stderr,
        level=getattr(logging, log_level),
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Get a logger instance for the given module name.

    Args:
        name: Module name (typically __name__)

    Returns:
        Configured structlog logger
    """
    return structlog.get_logger(name)  # type: ignore[no-any-return]
