"""CLI entry point for the OTC Pricing MCP server.

Starts both MCP transports concurrently in the same asyncio event loop:
- STDIO transport  — for local MCP clients (Claude Desktop, CLI tools)
- SSE transport    — for remote/web MCP clients via HTTP on port 8080

The SSE endpoint is available at http://<host>:8080/sse.
Health and metrics endpoints (/healthz, /readyz, /metrics) are served on the
same port by the same uvicorn server.
"""

from __future__ import annotations

import asyncio
import os
import sys

import uvicorn
from mcp.server.stdio import stdio_server

from . import observability
from .observability import http_server
from .server import server

# Configure logging first so everything can be logged
observability.configure_logging(log_level=os.getenv("LOG_LEVEL", "INFO"))
logger = observability.get_logger(__name__)


async def main() -> int:
    """Run the MCP server with STDIO and SSE transports concurrently."""
    try:
        port = int(os.getenv("METRICS_PORT", "8080"))
        # Default 0.0.0.0 so the container can be reached from outside the pod
        # (k8s service exposure, /healthz, /readyz, /metrics). Override with
        # METRICS_HOST=127.0.0.1 to lock down to loopback in non-container runs.
        host = os.getenv("METRICS_HOST", "0.0.0.0")  # nosec B104 — see comment above

        # Build Starlette app: SSE transport + health/metrics routes
        app = http_server.create_app(server)
        config = uvicorn.Config(
            app,
            host=host,
            port=port,
            log_config=None,  # don't override our structlog setup
            access_log=False,  # silence uvicorn access logs (structlog handles this)
        )
        uv_server = uvicorn.Server(config)

        logger.info("mcp_server_starting", transports=["stdio", "sse"], port=port)

        # Start uvicorn as a background asyncio task so it keeps running
        # even after STDIO exits (e.g. when K8s stdin is /dev/null)
        uvicorn_task = asyncio.create_task(uv_server.serve(), name="uvicorn")

        # Run STDIO transport — exits immediately in K8s (stdin = /dev/null)
        async with stdio_server() as (read_stream, write_stream):
            logger.info("mcp_server_ready", status="accepting_connections")
            await server.run(
                read_stream,
                write_stream,
                server.create_initialization_options(),
            )

        # STDIO has exited.  Uvicorn keeps the process alive so SSE clients and
        # Kubernetes liveness/readiness probes continue to work.
        await uvicorn_task
        return 0
    except KeyboardInterrupt:
        logger.info("mcp_server_shutdown", reason="keyboard_interrupt")
        return 130
    except Exception as e:
        logger.error("mcp_server_error", error=str(e), exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
