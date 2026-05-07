# OTC Pricing MCP Server

[![CI](https://github.com/seaser0/otc-pricing-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/seaser0/otc-pricing-mcp/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/seaser0/otc-pricing-mcp)](https://github.com/seaser0/otc-pricing-mcp/releases/latest)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.12%2B-blue.svg)](https://www.python.org/downloads/)

An open-source **Model Context Protocol (MCP)** server for the **Open Telekom Cloud (OTC) Price Calculator API**.

Expose OTC pricing data to Claude and other LLM clients with full observability (structured logging, Prometheus metrics, health checks).

**Status**: v0.1.0 (Core functionality complete, Stories 0-7)

---

## What is MCP?

**Model Context Protocol** is a standard that enables LLM applications (like Claude) to interact with external tools via a protocol called **STDIO transport**.

In simple terms:
- Your MCP server runs as a process
- Claude connects to it via stdin/stdout
- Claude can call your tools with parameters
- Your server returns results back to Claude

This server gives Claude access to OTC pricing data through 7 specialized tools.

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
{"timestamp": "2026-05-06T18:00:00.123456Z", "event": "metrics_server_started", "port": 8080, "thread": "metrics-server"}
{"timestamp": "2026-05-06T18:00:00.456789Z", "event": "mcp_server_ready", "status": "accepting_connections"}
```

The server is now listening for MCP connections on stdin/stdout.

### 2. Connect Your MCP Client

If you're using Claude desktop or another MCP client, configure it to connect:

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

---

## Configuration

### Environment Variables

Control the server behavior with environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `LOG_LEVEL` | `INFO` | Logging level: `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `METRICS_PORT` | `8080` | Port for metrics/health endpoints |
| `OTC_PRICING_API_BASE` | `https://calculator.otc-service.com/en/open-telekom-price-api/` | OTC API endpoint |

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

### Prometheus Metrics

HTTP server on port 8080 exposes Prometheus metrics and health checks.

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

See `deploy/kubernetes/deployment.yaml` for a complete example.

Key features:
- Non-root user (distroless image)
- Resource limits (CPU, memory)
- Liveness probe: GET /healthz on port 8080
- Readiness probe: GET /readyz on port 8080
- ServiceMonitor for Prometheus scraping

---

## Architecture

### Request Flow

```
Claude Client
    ↓
MCP STDIO Transport (stdin/stdout)
    ↓
MCP Server (server.py)
  - List tools
  - Route tool calls
  - Log invocations
  - Record metrics
    ↓
HTTP Client (client.py)
  - Build request
  - Retry logic (exponential backoff)
  - Parse response
  - Log API calls
  - Record metrics
    ↓
OTC Price Calculator API
    ↓
(Response flows back through each layer)
```

### Component Overview

| Component | Purpose |
|-----------|---------|
| `__main__.py` | Entry point, launches STDIO server + HTTP metrics server |
| `server.py` | MCP server, routes tool calls, logs invocations |
| `client.py` | HTTP client for OTC API, retry logic, API logging |
| `tools/` | Tool implementations (discovery, pricing, estimation) |
| `observability/` | Logging, metrics, health checks |
| `models.py` | Data models (validated with Pydantic) |
| `normalize.py` | Price parsing and formatting |

---

## Open Features (Future Development)

This v0.1.0 implementation provides the core MCP server with full observability.

Future stories can add these features:

### Story 8: ArgoCD Deployment (Kubernetes)
- Deploy to k3s cluster with ArgoCD
- Auto-sync from git repository
- Kustomize overlays for dev/staging/prod

### Story 9: Open Source Documentation
- Publish to GitHub with CONTRIBUTING.md
- API documentation (OpenAPI spec)
- Architecture decision records (ADRs)

### Enhancement Ideas (Post-v1.0)

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

**Copyright**: NEVIT (platform@nevit.ch)

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
| 6 | CI/CD pipeline | ✅ Done |
| 7 | Observability (logging, metrics, health) | ✅ Done |
| 8 | ArgoCD deployment | 🔄 Next |
| 9 | Open source documentation | 🔄 Next |

---

## Architecture Decisions

See [docs/](docs/) directory for detailed documentation:
- `docs/ci-cd.md` — CI/CD workflow details
- `docs/deployment.md` — Deployment guide
- `docs/security.md` — Security features and considerations

---
<!-- mcp-name: io.github.seaser0/otc-pricing-mcp -->
**Built with ❤️ by NEVIT**

*Last updated: 2026-05-06*
