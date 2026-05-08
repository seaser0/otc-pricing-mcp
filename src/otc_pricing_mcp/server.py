"""MCP server for the OTC Price Calculator API.

Exposes 7 MCP tools for service discovery, pricing queries, and estimation.
Includes comprehensive logging and metrics tracking for debugging and monitoring.
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any

from mcp.server import Server
from mcp.types import CallToolResult, TextContent, Tool

from . import observability
from .tools.discovery import get_service_schema, list_regions, list_services
from .tools.estimation import compare_billing_models, estimate_monthly_cost
from .tools.pricing import find_compute_flavor, query_pricing

logger = observability.get_logger(__name__)

# Initialize MCP server
server = Server("otc-pricing-mcp")


@server.list_tools()  # type: ignore[no-untyped-call,untyped-decorator]
async def list_tools() -> list[Tool]:
    """List all available MCP tools."""
    logger.debug("list_tools_called")
    tools: list[Tool] = [
        Tool(
            name="list_services",
            description="List all available OTC services with pricing data.",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": [],
            },
        ),
        Tool(
            name="list_regions",
            description="List available regions for OTC services.",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": [],
            },
        ),
        Tool(
            name="get_service_schema",
            description="Get the schema (filterable/returnable columns) for a service.",
            inputSchema={
                "type": "object",
                "properties": {
                    "service": {
                        "type": "string",
                        "description": "Service name (e.g., 'ecs', 'evs', 'obs')",
                    },
                },
                "required": ["service"],
            },
        ),
        Tool(
            name="query_pricing",
            description="Query pricing data with flexible filtering and column selection.",
            inputSchema={
                "type": "object",
                "properties": {
                    "services": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Service names (e.g., ['ecs', 'evs'])",
                    },
                    "region": {
                        "type": "string",
                        "description": "Filter by region (e.g., 'eu-de', 'eu-nl', 'eu-ch2')",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum number of results to return (default: 5000)",
                    },
                },
                "required": ["services"],
            },
        ),
        Tool(
            name="find_compute_flavor",
            description="Find compute (ECS) instances matching vCPU/RAM/OS criteria. Returns {matches: [...], warnings: [...]}.",
            inputSchema={
                "type": "object",
                "properties": {
                    "v_cpu": {"type": "integer", "description": "Virtual CPUs"},
                    "ram_gb": {"type": "number", "description": "RAM in GiB"},
                    "os": {"type": "string", "description": "OS (Linux, Windows, etc.)"},
                    "region": {"type": "string", "description": "Region (default: eu-de)"},
                },
                "required": ["v_cpu", "ram_gb"],
            },
        ),
        Tool(
            name="estimate_monthly_cost",
            description="Estimate monthly cost for a list of resources.",
            inputSchema={
                "type": "object",
                "properties": {
                    "items": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {
                                    "type": "string",
                                    "description": "Product ID (e.g., 'OTC_S3M1_LI')",
                                },
                                "quantity": {
                                    "type": "number",
                                    "description": "Quantity (default: 1)",
                                },
                                "hours_per_month": {
                                    "type": "number",
                                    "description": "Hours (default: 730)",
                                },
                            },
                            "required": ["id"],
                        },
                        "description": "List of resources with quantities",
                    },
                },
                "required": ["items"],
            },
        ),
        Tool(
            name="compare_billing_models",
            description="Compare PAYG vs. Reserved (12/24/36 month) billing for a product.",
            inputSchema={
                "type": "object",
                "properties": {
                    "product_id": {
                        "type": "string",
                        "description": "Product ID (e.g., 'OTC_S3M1_LI')",
                    },
                    "quantity": {
                        "type": "number",
                        "description": "Quantity (default: 1)",
                    },
                    "hours_per_month": {
                        "type": "number",
                        "description": "Hours per month (default: 730)",
                    },
                },
                "required": ["product_id"],
            },
        ),
    ]
    return tools


def _ok(text: str) -> CallToolResult:
    """Wrap a successful tool result as a CallToolResult with isError=false."""
    return CallToolResult(content=[TextContent(type="text", text=text)], isError=False)


def _err(text: str) -> CallToolResult:
    """Wrap a failed tool result as a CallToolResult with isError=true."""
    return CallToolResult(content=[TextContent(type="text", text=text)], isError=True)


@server.call_tool()  # type: ignore[untyped-decorator]
async def call_tool(name: str, arguments: dict[str, Any]) -> CallToolResult:
    """Route tool calls to their implementations with logging and metrics.

    Always returns a CallToolResult so callers (the MCP SDK and tests alike)
    see a single, consistent envelope. isError=true is reserved for upstream
    failures and uncaught exceptions; everything else returns isError=false.
    """
    # Generate request ID for this tool invocation if not already set
    request_id = observability.get_request_id()
    if request_id is None:
        request_id = observability.generate_request_id()
        observability.set_request_id(request_id)

    start_time = time.time()
    logger.info(
        "tool_invocation_start",
        tool=name,
        request_id=request_id,
        arguments=arguments,
    )

    # Annotate as Any so mypy does not pin the type to the first branch's
    # return value (list[str] from list_services); the actual shape varies
    # per tool and json.dumps handles all of them.
    result: Any
    try:
        # Route to tool implementation
        if name == "list_services":
            result = await asyncio.to_thread(list_services)
            text = json.dumps(result, ensure_ascii=False)
        elif name == "list_regions":
            result = await asyncio.to_thread(list_regions)
            text = json.dumps(result, ensure_ascii=False)
        elif name == "get_service_schema":
            service = arguments["service"]
            result = await asyncio.to_thread(get_service_schema, service)
            text = json.dumps(result, ensure_ascii=False)
        elif name == "query_pricing":
            result = await asyncio.to_thread(
                query_pricing,
                arguments["services"],
                arguments.get("region"),
                arguments.get("max_results"),
            )
            text = json.dumps(result, ensure_ascii=False)
            warnings = result.get("warnings", [])
            if warnings and result.get("total_items", 0) == 0:
                duration = time.time() - start_time
                observability.metrics.requests_total.labels(tool=name, status="error").inc()
                observability.metrics.request_duration_seconds.labels(tool=name).observe(duration)
                logger.warning(
                    "tool_invocation_upstream_error",
                    tool=name,
                    request_id=request_id,
                    warnings=warnings,
                    duration_seconds=duration,
                )
                return _err(text)
        elif name == "find_compute_flavor":
            result = await asyncio.to_thread(
                find_compute_flavor,
                arguments["v_cpu"],
                arguments["ram_gb"],
                arguments.get("os"),
                arguments.get("region", "eu-de"),
            )
            text = json.dumps(result, ensure_ascii=False)
            warnings = result.get("warnings", [])
            if warnings and not result.get("matches"):
                duration = time.time() - start_time
                observability.metrics.requests_total.labels(tool=name, status="error").inc()
                observability.metrics.request_duration_seconds.labels(tool=name).observe(duration)
                logger.warning(
                    "tool_invocation_upstream_error",
                    tool=name,
                    request_id=request_id,
                    warnings=warnings,
                    duration_seconds=duration,
                )
                return _err(text)
        elif name == "estimate_monthly_cost":
            result = await asyncio.to_thread(estimate_monthly_cost, arguments["items"])
            text = json.dumps(result, ensure_ascii=False)
        elif name == "compare_billing_models":
            result = await asyncio.to_thread(
                compare_billing_models,
                arguments["product_id"],
                arguments.get("quantity", 1.0),
                arguments.get("hours_per_month", 730.0),
            )
            text = json.dumps(result, ensure_ascii=False)
        else:
            text = f"Unknown tool: {name}"
            logger.warning("unknown_tool_requested", tool=name, request_id=request_id)
            observability.metrics.requests_total.labels(tool=name, status="error").inc()
            duration = time.time() - start_time
            observability.metrics.request_duration_seconds.labels(tool=name).observe(duration)
            return _err(text)

        # Record success metrics
        duration = time.time() - start_time
        observability.metrics.requests_total.labels(tool=name, status="success").inc()
        observability.metrics.request_duration_seconds.labels(tool=name).observe(duration)

        logger.info(
            "tool_invocation_success",
            tool=name,
            request_id=request_id,
            duration_seconds=duration,
        )

        return _ok(text)

    except Exception as e:
        # Record error metrics
        duration = time.time() - start_time
        observability.metrics.requests_total.labels(tool=name, status="error").inc()
        observability.metrics.request_duration_seconds.labels(tool=name).observe(duration)

        logger.error(
            "tool_invocation_error",
            tool=name,
            request_id=request_id,
            error=str(e),
            error_type=type(e).__name__,
            duration_seconds=duration,
            exc_info=True,
        )

        return _err(f"Error executing tool '{name}': {e!s}")
