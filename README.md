# OTC Pricing MCP Server

[![CI](https://github.com/seaser0/otc-pricing-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/seaser0/otc-pricing-mcp/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/seaser0/otc-pricing-mcp)](https://github.com/seaser0/otc-pricing-mcp/releases/latest)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.12%2B-blue.svg)](https://www.python.org/downloads/)

An open-source **Model Context Protocol (MCP)** server for the **Open Telekom Cloud (OTC) Price Calculator API**.

Expose OTC pricing data to Claude and other LLM clients with full observability (structured logging, Prometheus metrics, health checks).

**Status**: v0.1.3 — STDIO + SSE transports, Kubernetes deployment, full observability

---

## What is MCP?

**Model Context Protocol** is a standard that enables LLM applications (like Claude) to interact with external tools and data sources. This server supports two transports:

| Transport | How it works | Best for |
|-----------|-------------|----------|
| **STDIO** | Claude launches the server as a subprocess; communication is over stdin/stdout | Local Claude Desktop, CLI tools |
| **SSE** | Server-Sent Events over HTTP — Claude connects to a URL | Remote/hosted deployments, web clients |

This server gives Claude access to OTC pricing data and the user-manual / API-reference documentation through 9 specialized tools, on whichever transport you prefer.

---

## What Can You Do With This?

**Example Use Cases:**
- Ask Claude: _"Find the cheapest ECS instance with 4 CPUs and 8GB RAM in eu-de"_
- Claude calls `find_compute_flavor` tool → gets pricing data → answers you
- Ask: _"Compare PAYG vs 12-month reserved pricing for S3 storage"_
- Claude calls `compare_billing_models` tool → does the analysis → shows savings

---

## Quick Start

### 1. Install

**Requirements**: Python 3.12+

```bash
# Clone the repository
git clone https://github.com/seaser0/otc-pricing-mcp.git
cd otc-pricing-mcp

# Install dependencies
uv sync

# Run the server
python -m otc_pricing_mcp
```

**What You'll See:**
```
{"event": "mcp_server_starting", "transports": ["stdio", "sse"], "port": 8080, ...}
{"event": "mcp_server_ready", "status": "accepting_connections", ...}
```

The server now listens for MCP connections on **both** stdin/stdout and `http://localhost:8080/sse`.

### 2. Connect Your MCP Client

**Option A — STDIO (local, Claude Desktop)**

```json
{
  "mcpServers": {
    "otc-pricing": {
      "command": "python",
      "args": ["-m", "otc_pricing_mcp"],
      "env": {
        "LOG_LEVEL": "INFO",
        "METRICS_PORT": "8080"
      }
    }
  }
}
```

**Option B — SSE (remote, Kubernetes)**

Point any MCP client that supports SSE transport at the hosted endpoint:

```json
{
  "mcpServers": {
    "otc-pricing": {
      "url": "https://mcp-otc-pricing.example.com/sse"
    }
  }
}
```

Or test locally while running the server:

```bash
# In a second terminal:
curl -N http://localhost:8080/sse
# event: endpoint
# data: /messages/?session_id=<uuid>
```

### 3. Start Using Tools

Once connected, Claude can call any of the 7 available tools. See the **Tools Reference** section below.

---

## Tools Reference

The server exposes **7 MCP tools** for different pricing queries:

### 1. `list_services`
**Purpose**: Get all available OTC services

**Input**: None

**Output**: List of service names and metadata

**Example Claude usage:**
```
"What OTC services are available for pricing?"
```

---

### 2. `list_regions`
**Purpose**: Get available OTC regions

**Input**: None

**Output**: List of region codes (eu-de, eu-nl, eu-ch2, etc.)

**Example Claude usage:**
```
"What regions does OTC support?"
```

---

### 3. `get_service_schema`
**Purpose**: Get filterable/returnable columns for a service

**Input**:
- `service` (string): Service name (e.g., "ecs", "evs", "obs", "s3", "rds")

**Output**: Schema with filterable and returnable column names

**Example Claude usage:**
```
"What columns can I filter on for ECS pricing?"
```

---

### 4. `query_pricing`
**Purpose**: Query pricing data with flexible filtering

**Input**:
- `services` (array): List of service names (e.g., ["ecs", "evs"])
- `region` (string, optional): Filter by region (e.g., "eu-de")
- `max_results` (integer, optional): Max results to return (default: 5000)

**Output**: Pricing rows matching the filter

**Example Claude usage:**
```
"Show me ECS and EVS pricing in the eu-de region"
```

---

### 5. `find_compute_flavor`
**Purpose**: Find compute (ECS) instances by vCPU/RAM/OS

**Input**:
- `v_cpu` (integer): Number of virtual CPUs
- `ram_gb` (number): RAM in GiB
- `os` (string, optional): Operating system (Linux, Windows, etc.)
- `region` (string, optional): Region (default: eu-de)

**Output**: Matching ECS instance types with pricing

**Example Claude usage:**
```
"Find a Linux ECS instance with 4 CPUs and 16GB RAM in eu-nl"
```

---

### 6. `estimate_monthly_cost`
**Purpose**: Calculate monthly cost for multiple resources

**Input**:
- `items` (array): Resources with:
  - `id` (string): Product ID (e.g., "OTC_S3M1_LI")
  - `quantity` (number, optional): How many units (default: 1)
  - `hours_per_month` (number, optional): Usage hours (default: 730)

**Output**: Itemized costs with monthly total

**Example Claude usage:**
```
"Calculate monthly cost for 100GB S3 storage and an ECS instance"
```

---

### 7. `compare_billing_models`
**Purpose**: Compare PAYG vs Reserved Instance pricing

**Input**:
- `product_id` (string): Product ID (e.g., "OTC_S3M1_LI")
- `quantity` (number, optional): Quantity (default: 1)
- `hours_per_month` (number, optional): Usage hours (default: 730)

**Output**: Cost comparison for PAYG, 12mo, 24mo, 36mo reserved

**Example Claude usage:**
```
"Compare PAYG vs 12/24/36 month reserved pricing for ECS"
```

### 8. `search_otc_docs`
**Purpose**: Full-text search across the indexed OTC user manual and API reference

**Input**:
- `query` (string): Search terms (BM25-ranked, AND of tokens)
- `scope` (string, optional): `public` | `swiss` | `both` (default: `both`)
- `service` (string, optional): Restrict to one service repo (e.g. `elastic-cloud-server`)
- `top_k` (integer, optional): 1-50, default 5

**Output**: Ranked list of `{url, title, h2, h3, snippet, service, cloud, upstream_commit}` hits.
The index ships with the package and is rebuilt weekly from the upstream
`opentelekomcloud-docs/<service>` Sphinx/RST repos (Apache-2.0); the runtime
never touches the Anubis-gated docs.otc.t-systems.com HTML.

**Example Claude usage:**
```
"Find the OTC docs page that explains S3-flavor ECS specifications"
```

### 9. `get_otc_doc_section`
**Purpose**: Fetch the body of one indexed documentation page (or one of its sections) as Markdown

**Input**:
- `url` (string): Canonical URL as returned by `search_otc_docs` (with or without `#anchor`)
- `section` (string, optional): H2/H3 heading filter (case-insensitive substring)

**Output**: `{url, title, sections: [{h2, h3, anchor, body}, ...], matched, ...}`

**Example Claude usage:**
```
"Show me the EVS Disk Types and Performance section"
```

---

## Configuration

### Environment Variables

Control the server behavior with environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `LOG_LEVEL` | `INFO` | Logging level: `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `METRICS_PORT` | `8080` | Port for metrics/health endpoints |
| `METRICS_HOST` | `0.0.0.0` | Bind address for the HTTP server (set to `127.0.0.1` for non-container runs) |
| `OTC_PRICING_API_BASE` | `https://calculator.otc-service.com/en/open-telekom-price-api/` | OTC API endpoint |
| `OTC_DOCS_DB` | (auto) | Override path to the docs FTS5 index (default: bundled `data/otc_docs.sqlite3`) |

**Example**:
```bash
LOG_LEVEL=DEBUG METRICS_PORT=9090 python -m otc_pricing_mcp
```

---

## Observability: Metrics & Logs

This server is built with **production-grade observability** so you can debug issues and monitor performance.

### Structured Logging (JSON)

Every action is logged as JSON, making logs machine-readable for aggregation and analysis.

**Start the server with DEBUG logging:**
```bash
LOG_LEVEL=DEBUG python -m otc_pricing_mcp 2>&1
```

**You'll see JSON logs like:**
```json
{"timestamp": "2026-05-06T18:00:00.123456Z", "event": "tool_invocation_start", "tool": "query_pricing", "request_id": "550e8400-e29b-41d4-a716-446655440000", "arguments": {"services": ["ecs"]}}

{"timestamp": "2026-05-06T18:00:00.234567Z", "event": "upstream_request_start", "service": "ecs", "request_id": "550e8400-e29b-41d4-a716-446655440000"}

{"timestamp": "2026-05-06T18:00:00.345678Z", "event": "upstream_request_success", "service": "ecs", "request_id": "550e8400-e29b-41d4-a716-446655440000", "status_code": 200, "duration_seconds": 0.111, "attempt": 1, "items_returned": 42}

{"timestamp": "2026-05-06T18:00:00.456789Z", "event": "tool_invocation_success", "tool": "query_pricing", "request_id": "550e8400-e29b-41d4-a716-446655440000", "duration_seconds": 0.333}
```

**Key fields in every log:**
- `timestamp`: When the event happened (ISO 8601)
- `event`: What happened (tool_invocation_start, upstream_request_success, etc.)
- `request_id`: Unique ID for this request (same across all related logs)
- Custom fields depending on the event

**Logs are printed to stderr**, so redirect to a file or log aggregator:
```bash
python -m otc_pricing_mcp 2>/var/log/otc-pricing-mcp.log
```

**Pipe to `jq` for pretty printing:**
```bash
python -m otc_pricing_mcp 2>&1 | jq .
```

### HTTP Endpoints (port 8080)

The uvicorn server exposes all endpoints on port 8080:

| Path | Method | Description |
|------|--------|-------------|
| `/sse` | GET | MCP SSE transport — connect your MCP client here |
| `/messages/` | POST | MCP SSE message handler (used internally by the client) |
| `/healthz` | GET | Liveness probe — always 200 if the process is up |
| `/readyz` | GET | Readiness probe — 200 when OTC API is reachable, 503 otherwise |
| `/metrics` | GET | Prometheus metrics in text exposition format |

**Health Checks:**
```bash
# Liveness check (always 200 if process is up)
curl http://localhost:8080/healthz
# {"status": "ok", "service": "otc-pricing-mcp"}

# Readiness check (verifies OTC API is reachable)
curl http://localhost:8080/readyz
# {"status": "ready", "upstream": "ok", "api_response_time": 0.042}
```

**Prometheus Metrics:**
```bash
curl http://localhost:8080/metrics
```

Returns Prometheus format metrics:
```
# HELP otc_pricing_mcp_requests_total Total MCP tool requests (success and failure)
# TYPE otc_pricing_mcp_requests_total counter
otc_pricing_mcp_requests_total{status="success",tool="query_pricing"} 5.0
otc_pricing_mcp_requests_total{status="error",tool="query_pricing"} 1.0

# HELP otc_pricing_mcp_request_duration_seconds MCP tool request duration in seconds
# TYPE otc_pricing_mcp_request_duration_seconds histogram
otc_pricing_mcp_request_duration_seconds_bucket{le="0.005",tool="query_pricing"} 0.0
otc_pricing_mcp_request_duration_seconds_bucket{le="0.01",tool="query_pricing"} 1.0
...

# HELP otc_pricing_mcp_upstream_requests_total Total upstream OTC API requests (success and failure)
# TYPE otc_pricing_mcp_upstream_requests_total counter
otc_pricing_mcp_upstream_requests_total{service="ecs",status="success"} 10.0
otc_pricing_mcp_upstream_requests_total{service="ecs",status="error"} 2.0
...
```

**Available Metrics:**
- `otc_pricing_mcp_requests_total{tool, status}`: Count of tool invocations
- `otc_pricing_mcp_request_duration_seconds{tool}`: Tool execution time
- `otc_pricing_mcp_upstream_requests_total{service, status}`: Count of API calls
- `otc_pricing_mcp_upstream_duration_seconds{service}`: API call latency

**Using Prometheus:**

Add to your `prometheus.yml`:
```yaml
scrape_configs:
  - job_name: 'otc-pricing-mcp'
    static_configs:
      - targets: ['localhost:8080']
```

Then query in Prometheus:
```
rate(otc_pricing_mcp_requests_total[5m])  # Requests per second
histogram_quantile(0.95, otc_pricing_mcp_request_duration_seconds_bucket)  # p95 latency
```

---

## Debugging Guide

### Problem: Slow API Calls

**Check the logs:**
```bash
LOG_LEVEL=DEBUG python -m otc_pricing_mcp 2>&1 | jq 'select(.event == "upstream_request_success") | {service, duration_seconds}'
```

**Check metrics:**
```bash
curl http://localhost:8080/metrics | grep upstream_duration_seconds
```

### Problem: Tool Fails

**Look for error logs:**
```bash
LOG_LEVEL=DEBUG python -m otc_pricing_mcp 2>&1 | jq 'select(.event == "tool_invocation_error")'
```

**Example error log:**
```json
{
  "event": "tool_invocation_error",
  "tool": "query_pricing",
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "error": "list index out of range",
  "error_type": "IndexError",
  "duration_seconds": 0.001,
  "exc_info": true
}
```

### Problem: OTC API Unreachable

**Check readiness endpoint:**
```bash
curl -v http://localhost:8080/readyz
# HTTP/1.1 503 Service Unavailable
# {"status": "not_ready", "upstream": "unreachable", "error": "..."}
```

**Check metrics:**
```bash
curl http://localhost:8080/metrics | grep upstream_requests_total
# Will show increased error counts
```

### Problem: Need Full Request Trace

**Use request_id to trace a request:**
```bash
# Get the request_id from any log
LOG_LEVEL=DEBUG python -m otc_pricing_mcp 2>&1 | jq 'select(.request_id == "550e8400-e29b-41d4-a716-446655440000")'
```

This shows all logs for that request in order:
1. tool_invocation_start
2. upstream_request_start
3. upstream_request_success (with items_returned)
4. tool_invocation_success

---

## Running Locally (Development)

### Setup

```bash
# Clone repo
git clone https://github.com/seaser0/otc-pricing-mcp.git
cd otc-pricing-mcp

# Install with dev dependencies
uv sync

# Run tests
uv run pytest tests/ -v

# Check code quality
uv run ruff check src/
uv run mypy src/ --strict
```

### Run in Development Mode

```bash
# With debug logging
LOG_LEVEL=DEBUG python -m otc_pricing_mcp

# In another terminal, test the endpoints
curl http://localhost:8080/healthz | jq .
curl http://localhost:8080/metrics
```

---

## Running in Production (Docker)

### Build Image

```bash
docker build -t otc-pricing-mcp:latest .
```

### Run Container

```bash
docker run \
  --name otc-pricing-mcp \
  -e LOG_LEVEL=INFO \
  -e METRICS_PORT=8080 \
  -p 8080:8080 \
  otc-pricing-mcp:latest
```

### Kubernetes Deployment

See `deploy/kubernetes/` for the full manifest set (Deployment, Service, Ingress, NetworkPolicy, ServiceMonitor, PodDisruptionBudget).

When self-hosting on Kubernetes, connect remote clients to your ingress hostname:
```
https://mcp-otc-pricing.example.com/sse
```

Key features:
- Non-root user, read-only root filesystem
- Resource limits (100m–500m CPU, 128Mi–512Mi RAM)
- Liveness probe: GET /healthz on port 8080
- Readiness probe: GET /readyz on port 8080
- NetworkPolicy: ingress from nginx controller only, egress to DNS + OTC API
- ServiceMonitor for Prometheus scraping
- Managed by ArgoCD with `selfHeal: true` and `prune: true`

---

## Architecture

### Request Flow

```
Claude Client
    │
    ├─ STDIO transport (local)      ──┐
    │  stdin/stdout                   │
    │                                 ▼
    └─ SSE transport (remote)      MCP Server (server.py)
       GET  /sse                     - List tools
       POST /messages/               - Route tool calls
                                     - Log invocations
                                     - Record metrics
                                         │
                                         ▼
                                   HTTP Client (client.py)
                                     - Build request
                                     - Retry logic
                                     - Parse response
                                         │
                                         ▼
                                   OTC Price Calculator API
```

Both transports share the same MCP Server instance and run concurrently in the same asyncio event loop.

### Component Overview

| Component | Purpose |
|-----------|---------|
| `__main__.py` | Entry point — runs STDIO + uvicorn SSE concurrently |
| `server.py` | MCP server, routes tool calls, logs invocations |
| `client.py` | HTTP client for OTC API, retry logic, API logging |
| `tools/` | Tool implementations (discovery, pricing, estimation) |
| `observability/http_server.py` | Starlette app — SSE transport + health/metrics routes |
| `observability/` | Logging, Prometheus metrics, request context |
| `models.py` | Data models (validated with Pydantic) |
| `normalize.py` | Price parsing and formatting |

---

## Enhancement Ideas (Future Development)

Stories 0–9 are complete. The following are post-v1.0 enhancements:

### Enhancement Ideas

**Caching**
- Cache pricing data for N seconds to reduce API load
- Redis or in-memory cache option
- Cache invalidation strategy

**Advanced Querying**
- More filtering options (e.g., price range, commitment period)
- Sorting by price, CPU, RAM
- Aggregations (min/max/avg pricing per service)

**Cost Analysis Tools**
- Historical pricing trends
- Cost anomaly detection
- Recommendation engine (right-sizing)

**Multi-Cloud Support**
- AWS pricing API integration
- Azure pricing API integration
- Cost comparison across clouds

**User Preferences**
- Save favorite services/regions
- Custom pricing alerts
- Budget tracking per project

**Better Error Recovery**
- Exponential backoff with jitter (vs fixed exponential)
- Circuit breaker pattern
- Fallback to cached data on API failure

**Performance Optimizations**
- Query result pagination
- Database caching layer
- Streaming responses for large datasets

**Observability Enhancements**
- Distributed tracing (OpenTelemetry)
- Custom business metrics (cost calculated, queries per service)
- Log aggregation integration (Loki, ELK)
- Alert rules (Prometheus Alertmanager)

**Testing Improvements**
- Load testing (k6, Locust)
- Chaos testing (failure scenarios)
- Contract testing with OTC API

**API Stability**
- API versioning (v1, v2)
- Deprecation policies
- Backward compatibility guarantees

---

## Contributing

We welcome contributions! See [CONTRIBUTING.md](CONTRIBUTING.md) for:
- Development setup
- Code style (ruff, mypy --strict)
- Testing requirements (53+ tests with coverage)
- Security scanning (bandit, cyclonedx-bom)
- Commit message conventions

**Quick PR Checklist:**
- [ ] Tests pass: `uv run pytest tests/`
- [ ] Linting passes: `uv run ruff check src/`
- [ ] Type checking passes: `uv run mypy src/ --strict`
- [ ] Security scan passes: `uv run bandit -r src/`
- [ ] Meaningful commit message

---

## License

Apache License 2.0 — see [LICENSE](LICENSE) file.

**Copyright**: seaser0 (s34s3r@gmail.com)

---

## Getting Help

**Questions or Issues?**
1. Check the [Debugging Guide](#debugging-guide) above
2. Open a GitHub Issue: https://github.com/seaser0/otc-pricing-mcp/issues
3. Check logs with: `LOG_LEVEL=DEBUG python -m otc_pricing_mcp 2>&1 | jq .`

**Want to Report a Security Issue?**
See [SECURITY.md](SECURITY.md) for responsible disclosure.

---

## Project Status

| Story | Feature | Status |
|-------|---------|--------|
| 0 | Project setup, API client, data models | ✅ Done |
| 1 | Catalog discovery tools | ✅ Done |
| 2 | Pricing query tools | ✅ Done |
| 3 | Multi-service fan-out | ✅ Done |
| 4 | Comprehensive testing | ✅ Done |
| 5 | Security & container hardening | ✅ Done |
| 6 | CI/CD pipeline (GHCR image, PyPI, SBOM, GitHub Release) | ✅ Done |
| 7 | Observability (structured logging, Prometheus metrics, health probes) | ✅ Done |
| 8 | ArgoCD deployment (Kubernetes, SSE transport, remote endpoint) | ✅ Done |
| 9 | Open source documentation (README, server.json, community docs) | ✅ Done |

---

## Architecture Decisions

See [docs/](docs/) directory for detailed documentation:
- `docs/ci-cd.md` — CI/CD workflow details
- `docs/deployment.md` — Deployment guide
- `docs/security.md` — Security features and considerations

---
<!-- mcp-name: io.github.seaser0/otc-pricing-mcp -->
**Built with ❤️ by seaser0**

*Last updated: 2026-05-07*
