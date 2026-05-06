"""CLI entry point for the OTC Pricing MCP server."""

from __future__ import annotations

import asyncio
import sys

from mcp.server.stdio import stdio_server

from .server import server


async def main() -> int:
    """Run the MCP server via STDIO transport."""
    try:
        async with stdio_server() as (read_stream, write_stream):
            await server.run(
                read_stream,
                write_stream,
                server.create_initialization_options(),
            )
        return 0
    except KeyboardInterrupt:
        return 130
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
