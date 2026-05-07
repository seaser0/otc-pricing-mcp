"""HTTP server for MCP SSE transport, health checks, and Prometheus metrics.

Provides:
- GET  /sse        - MCP Server-Sent Events transport (connect an MCP client here)
- POST /messages/  - MCP SSE message handler (used by the SSE client internally)
- GET  /healthz    - Liveness check (always 200 if process is up)
- GET  /readyz     - Readiness check (verifies upstream OTC API connectivity)
- GET  /metrics    - Prometheus metrics endpoint

All endpoints are served by a single uvicorn/Starlette ASGI server on port 8080,
running alongside the STDIO MCP transport in the same asyncio event loop.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx
from mcp.server.lowlevel import Server
from mcp.server.sse import SseServerTransport
from prometheus_client import REGISTRY, generate_latest
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Mount, Route

from .logging import get_logger

logger = get_logger(__name__)

# Readiness check cache — avoids hammering the OTC API on every probe
_last_api_check: dict[str, Any] | None = None
_api_check_cache_ttl = 30  # seconds
_readyz_lock = asyncio.Lock()


async def healthz(request: Request) -> Response:
    """Liveness check — always 200 if the process is running."""
    return JSONResponse({"status": "ok", "service": "otc-pricing-mcp"})


async def readyz(request: Request) -> Response:
    """Readiness check — verifies the OTC API is reachable.

    Uses a 30-second cache so Kubernetes probes don't hammer the upstream API.
    Returns 200 when ready, 503 when the API is unreachable.
    """
    global _last_api_check

    now = time.time()

    async with _readyz_lock:
        # Return cached result if still fresh
        if _last_api_check and (now - _last_api_check["timestamp"]) < _api_check_cache_ttl:
            return JSONResponse(
                _last_api_check["response"], status_code=_last_api_check["status"]
            )

        # Probe the OTC API
        try:
            api_base = "https://calculator.otc-service.com/en/open-telekom-price-api/"
            async with httpx.AsyncClient() as client:
                r = await client.head(api_base, timeout=5.0)
            r.raise_for_status()

            result: dict[str, Any] = {
                "status": "ready",
                "upstream": "ok",
                "api_response_time": r.elapsed.total_seconds(),
            }
            status = 200
            logger.debug("readiness_check_success", api_status=r.status_code)
        except Exception as e:
            result = {
                "status": "not_ready",
                "upstream": "unreachable",
                "error": str(e),
            }
            status = 503
            logger.warning("readiness_check_failed", error=str(e))

        _last_api_check = {"timestamp": now, "response": result, "status": status}
        return JSONResponse(result, status_code=status)


async def metrics_endpoint(request: Request) -> Response:
    """Prometheus metrics in text exposition format."""
    data = generate_latest(REGISTRY)
    return Response(content=data, media_type="text/plain; version=0.0.4")


def create_app(mcp_server: Server) -> Starlette:
    """Build the Starlette ASGI app wiring together SSE transport and observability routes.

    Args:
        mcp_server: The MCP low-level Server instance (shared with the STDIO transport).

    Returns:
        A configured Starlette application ready to be served by uvicorn.
    """
    sse_transport = SseServerTransport("/messages/")

    async def handle_sse(request: Request) -> Response:
        """Accept an SSE connection and run the MCP server over it."""
        logger.info("sse_client_connected", client=request.client)
        async with sse_transport.connect_sse(
            request.scope, request.receive, request._send  # type: ignore[attr-defined]
        ) as (read_stream, write_stream):
            await mcp_server.run(
                read_stream,
                write_stream,
                mcp_server.create_initialization_options(),
            )
        logger.info("sse_client_disconnected", client=request.client)
        return Response()

    routes = [
        Route("/sse", endpoint=handle_sse, methods=["GET"]),
        Mount("/messages/", app=sse_transport.handle_post_message),
        Route("/healthz", endpoint=healthz),
        Route("/readyz", endpoint=readyz),
        Route("/metrics", endpoint=metrics_endpoint),
    ]

    return Starlette(routes=routes)
