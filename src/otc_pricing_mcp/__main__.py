"""CLI entry point for the OTC Pricing MCP server.

Starts both the MCP STDIO server and the HTTP metrics/health server concurrently.
The STDIO server handles MCP protocol communication.
The HTTP server (port 8080) exposes /healthz, /readyz, and /metrics endpoints.
"""

from __future__ import annotations

import asyncio
import os
import sys
from threading import Thread

from mcp.server.stdio import stdio_server

from . import observability
from .server import server

# Configure logging first so everything can be logged
observability.configure_logging(log_level=os.getenv("LOG_LEVEL", "INFO"))
logger = observability.get_logger(__name__)


async def main() -> int:
    """Run the MCP server with metrics/health HTTP server in background."""
    try:
        # Start HTTP metrics/health server in background thread
        metrics_port = int(os.getenv("METRICS_PORT", "8080"))
        metrics_thread = Thread(
            target=observability.http_server.start,
            args=(metrics_port,),
            daemon=True,
            name="metrics-server",
        )
        metrics_thread.start()
        logger.info("metrics_server_started", port=metrics_port, thread=metrics_thread.name)

        # Run MCP STDIO server (main loop)
        logger.info("mcp_server_starting", transport="stdio")
        async with stdio_server() as (read_stream, write_stream):
            logger.info("mcp_server_ready", status="accepting_connections")
            await server.run(
                read_stream,
                write_stream,
                server.create_initialization_options(),
            )

        # stdio_server() closes stdout on exit, so no logging is possible here.
        # Block indefinitely so the HTTP metrics/health server stays alive
        # for Kubernetes liveness and readiness probes (K8s idle mode).
        await asyncio.sleep(float("inf"))
        return 0
    except KeyboardInterrupt:
        logger.info("mcp_server_shutdown", reason="keyboard_interrupt")
        return 130
    except Exception as e:
        logger.error("mcp_server_error", error=str(e), exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
