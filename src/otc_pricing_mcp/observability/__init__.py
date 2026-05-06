"""Observability module for OTC Pricing MCP.

Provides structured logging, metrics collection, and health checks
for operational visibility and debugging.

Public API:
- configure_logging(log_level) - Set up structured JSON logging
- get_logger(name) - Get a configured logger
- request_scope(request_id) - Context manager for request tracking
- generate_request_id() - Create a new request ID
- (metrics) - Prometheus counter/histogram objects
- (http_server) - Start HTTP server for health/metrics
"""

from __future__ import annotations

from . import http_server, metrics
from .context import (
    clear_request_id,
    generate_request_id,
    get_request_id,
    request_scope,
    set_request_id,
)
from .logging import configure_logging, get_logger

__all__ = [
    "configure_logging",
    "get_logger",
    "request_scope",
    "generate_request_id",
    "set_request_id",
    "get_request_id",
    "clear_request_id",
    "metrics",
    "http_server",
]
