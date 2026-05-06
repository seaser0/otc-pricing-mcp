"""Prometheus metrics for monitoring OTC Pricing MCP server.

Tracks tool execution metrics and upstream API call metrics
for operational visibility and performance monitoring.
"""

from __future__ import annotations

from prometheus_client import Counter, Histogram

# Buckets for request duration histogram (in seconds)
# Optimized for typical API call patterns (5ms to 10s)
_duration_buckets = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)

# Tool execution metrics
requests_total = Counter(
    "otc_pricing_mcp_requests_total",
    "Total MCP tool requests (success and failure)",
    ["tool", "status"],
)

request_duration_seconds = Histogram(
    "otc_pricing_mcp_request_duration_seconds",
    "MCP tool request duration in seconds",
    ["tool"],
    buckets=_duration_buckets,
)

# Upstream API metrics
upstream_requests_total = Counter(
    "otc_pricing_mcp_upstream_requests_total",
    "Total upstream OTC API requests (success and failure)",
    ["service", "status"],
)

upstream_duration_seconds = Histogram(
    "otc_pricing_mcp_upstream_duration_seconds",
    "Upstream OTC API request duration in seconds",
    ["service"],
    buckets=_duration_buckets,
)

# Connection tracking metrics
multi_service_requests_total = Counter(
    "otc_pricing_mcp_multi_service_requests_total",
    "Total multi-service pricing queries",
)

concurrent_requests_gauge = Histogram(
    "otc_pricing_mcp_concurrent_requests",
    "Number of concurrent service requests in a multi-service query",
    buckets=(1, 2, 3, 4, 5, 10),
)
