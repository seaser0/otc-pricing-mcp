"""MCP server for the OTC Price Calculator API.

Exposes 7 MCP tools for service discovery, pricing queries, and estimation.
"""

from __future__ import annotations

import logging
from typing import Any

from mcp.server import Server
from mcp.types import TextContent, Tool

logger = logging.getLogger(__name__)

# Initialize MCP server
server = Server("otc-pricing-mcp")


@server.list_tools()  # type: ignore[no-untyped-call,untyped-decorator]
async def list_tools() -> list[Tool]:
    """List all available MCP tools."""
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
            description="Find compute (ECS) instances matching vCPU/RAM/OS criteria.",
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


@server.call_tool()  # type: ignore[untyped-decorator]
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Route tool calls to their implementations."""
    if name == "list_services":
        return [TextContent(type="text", text="Not yet implemented")]
    elif name == "list_regions":
        return [TextContent(type="text", text="Not yet implemented")]
    elif name == "get_service_schema":
        return [TextContent(type="text", text="Not yet implemented")]
    elif name == "query_pricing":
        return [TextContent(type="text", text="Not yet implemented")]
    elif name == "find_compute_flavor":
        return [TextContent(type="text", text="Not yet implemented")]
    elif name == "estimate_monthly_cost":
        return [TextContent(type="text", text="Not yet implemented")]
    elif name == "compare_billing_models":
        return [TextContent(type="text", text="Not yet implemented")]
    else:
        return [TextContent(type="text", text=f"Unknown tool: {name}")]
