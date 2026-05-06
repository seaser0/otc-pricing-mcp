"""HTTP server for health checks and metrics endpoints.

Provides:
- /healthz - Liveness check (always 200)
- /readyz - Readiness check (verifies upstream API connectivity)
- /metrics - Prometheus metrics endpoint

Runs in a background thread to avoid blocking MCP STDIO communication.
"""

from __future__ import annotations

import json
import time
from collections.abc import Iterable
from typing import Any

import httpx
from prometheus_client import REGISTRY, generate_latest
from werkzeug.routing import Map, Rule
from werkzeug.serving import run_simple

from .logging import get_logger

logger = get_logger(__name__)

# Readiness check cache
_last_api_check: dict[str, Any] | None = None
_api_check_cache_ttl = 30  # seconds


def healthz() -> tuple[dict[str, str], int]:
    """Liveness check - always returns OK if process is up.

    Returns:
        Tuple of (response_body, http_status_code)
    """
    return {"status": "ok", "service": "otc-pricing-mcp"}, 200


def readyz() -> tuple[dict[str, Any], int]:
    """Readiness check - verifies OTC API is reachable.

    Uses cached result to reduce API load (30s TTL).

    Returns:
        Tuple of (response_body, http_status_code)
        - 200 if API is reachable
        - 503 if API is unreachable or check fails
    """
    global _last_api_check

    now = time.time()

    # Return cached result if still fresh
    if _last_api_check and (now - _last_api_check["timestamp"]) < _api_check_cache_ttl:
        return _last_api_check["response"], _last_api_check["status"]

    # Check API connectivity
    try:
        api_base = "https://calculator.otc-service.com/en/open-telekom-price-api/"
        response = httpx.head(api_base, timeout=5.0)
        response.raise_for_status()

        result = {
            "status": "ready",
            "upstream": "ok",
            "api_response_time": response.elapsed.total_seconds(),
        }
        status = 200
        logger.debug("readiness_check_success", api_status=response.status_code)
    except Exception as e:
        result = {
            "status": "not_ready",
            "upstream": "unreachable",
            "error": str(e),
        }
        status = 503
        logger.warning("readiness_check_failed", error=str(e))

    _last_api_check = {"timestamp": now, "response": result, "status": status}
    return result, status


def metrics() -> tuple[bytes, int]:
    """Prometheus metrics endpoint.

    Returns:
        Tuple of (prometheus_metrics_bytes, http_status_code)
    """
    return generate_latest(REGISTRY), 200


# URL routing for HTTP endpoints
url_map = Map(
    [
        Rule("/healthz", endpoint="healthz"),
        Rule("/readyz", endpoint="readyz"),
        Rule("/metrics", endpoint="metrics"),
    ]
)


def application(
    environ: dict[str, Any],
    start_response: Any,
) -> Iterable[bytes]:
    """WSGI application for health checks and metrics endpoints.

    Args:
        environ: WSGI environment dict
        start_response: WSGI start_response callable

    Returns:
        Response body as iterable of bytes
    """
    try:
        adapter = url_map.bind_to_environ(environ)
        endpoint, values = adapter.match()

        if endpoint == "healthz":
            body_dict, status_code = healthz()
            body = json.dumps(body_dict).encode("utf-8")
            content_type = "application/json"
        elif endpoint == "readyz":
            body_dict, status_code = readyz()
            body = json.dumps(body_dict).encode("utf-8")
            content_type = "application/json"
        elif endpoint == "metrics":
            body, status_code = metrics()
            content_type = "text/plain; version=0.0.4"
        else:
            body = b"Not Found"
            status_code = 404
            content_type = "text/plain"
    except Exception as e:
        logger.error("http_endpoint_error", error=str(e), endpoint=environ.get("PATH_INFO"))
        body = b"Internal Server Error"
        status_code = 500
        content_type = "text/plain"

    status = f"{status_code} {'OK' if status_code == 200 else 'Error'}"
    response_headers = [
        ("Content-Type", content_type),
        ("Content-Length", str(len(body))),
    ]
    start_response(status, response_headers)
    return [body]


def start(port: int = 8080, threaded: bool = True) -> None:
    """Start the HTTP metrics server.

    Runs in a background thread, listening on 0.0.0.0:port.

    Args:
        port: Port to listen on (default 8080)
        threaded: Whether to use threaded mode (default True)
    """
    try:
        logger.info("metrics_server_starting", port=port, threaded=threaded)
        run_simple(
            "0.0.0.0",
            port,
            application,
            threaded=threaded,
            use_reloader=False,
            use_debugger=False,
        )
    except Exception as e:
        logger.error("metrics_server_error", error=str(e), port=port)
        raise
