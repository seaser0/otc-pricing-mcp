"""CLI entry point for the OTC Pricing MCP server."""

from __future__ import annotations

import asyncio
import sys

from .server import server


async def main() -> int:
    """Run the MCP server."""
    try:
        await server.wait()  # type: ignore[attr-defined]
        return 0
    except KeyboardInterrupt:
        return 130
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
