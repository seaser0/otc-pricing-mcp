# Architecture: otc-pricing-mcp

## Overview

`otc-pricing-mcp` is a read-only [Model Context Protocol (MCP)](https://modelcontextprotocol.io) server that wraps the Open Telekom Cloud (OTC) Price Calculator REST API. It enables any MCP-compatible LLM client (Claude Desktop, Claude Code, Cursor, etc.) to query OTC pricing data using natural language.

The server is a **strict catalog wrapper** — no business logic, no markup, no vendor-specific assumptions. It exposes 7 MCP tools and is deployed to a NEVIT k3s cluster via ArgoCD.

---

## Tech Stack

| Concern | Technology |
|---------|-----------|
| Language | Python 3.12+ |
| MCP SDK | [`mcp`](https://github.com/modelcontextprotocol/python-sdk) (low-level `Server` API) |
| HTTP client | `httpx` (sync, with connection pooling) |
| Retry logic | `tenacity` (exponential backoff, up to 3 attempts) |
| Data models | `pydantic` v2 (`extra="allow"` for forward-compat) |
| Price parsing | Python `decimal.Decimal` (exact arithmetic) |
| Logging | `structlog` (JSON output, structured key-value pairs) |
| Metrics | `prometheus-client` (Counter + Histogram) |
| HTTP server | `werkzeug` WSGI (health/metrics endpoints) |
| Project mgmt | `uv` (lockfile, fast resolver) |
| Lint / format | `ruff` |
| Type checking | `mypy --strict` |
| Tests | `pytest` + `pytest-vcr` (cassette-based replay) |

---

## Repository Layout

```
otc-pricing-mcp/
├── src/otc_pricing_mcp/
│   ├── __init__.py               # Version constant (__version__ = "0.1.0")
│   ├── __main__.py               # CLI entrypoint — starts MCP + metrics servers
│   ├── server.py                 # MCP Server, tool registration, request routing
│   ├── client.py                 # httpx wrapper — all upstream API access
│   ├── models.py                 # Pydantic models: PriceItem, ApiResponse, ApiStats
│   ├── normalize.py              # parse_price(), extract_items(), normalize_response()
│   ├── tools/
│   │   ├── discovery.py          # list_services, list_regions, get_service_schema
│   │   ├── pricing.py            # query_pricing, find_compute_flavor
│   │   └── estimation.py         # estimate_monthly_cost, compare_billing_models
│   └── observability/
│       ├── __init__.py           # Re-exports: configure_logging, get_logger, metrics, http_server
│       ├── logging.py            # structlog setup (JSON format, LOG_LEVEL env var)
│       ├── metrics.py            # Prometheus Counter/Histogram definitions
│       ├── context.py            # Request ID propagation (contextvars)
│       └── http_server.py        # WSGI app: /healthz, /readyz, /metrics
├── tests/
│   ├── unit/                     # Pure-function tests, no network
│   ├── integration/              # @pytest.mark.live — hits real OTC API
│   ├── conformance/              # MCP protocol conformance
│   └── fixtures/                 # VCR cassettes (recorded API responses)
├── deploy/
│   ├── kubernetes/               # Raw Kubernetes manifests + Kustomize
│   │   ├── deployment.yaml
│   │   ├── service.yaml
│   │   ├── ingress.yaml
│   │   ├── servicemonitor.yaml
│   │   ├── network-policy.yaml
│   │   ├── poddisruptionbudget.yaml
│   │   └── kustomization.yaml
│   └── argocd/
│       └── application.yaml      # ArgoCD Application (auto-sync, self-heal)
├── .github/workflows/
│   ├── ci.yml                    # PR/push: lint, type check, tests, security scans
│   ├── release.yml               # Tag v*.*.*: multi-arch build → GHCR + GitHub release
│   └── security.yml              # Nightly: Trivy + pip-audit, opens issue on findings
└── docs/
    ├── architecture.md           # This file
    ├── tool-surface.md           # Full tool reference with parameter tables
    ├── deployment.md             # Docker, Helm, Claude Desktop setup
    ├── api-quirks.md             # OTC API behavioral quirks (empirically verified)
    └── catalog-inventory.md      # Services × regions × currencies × record counts
```

---

## Layered Architecture

```
┌─────────────────────────────────────────────────────┐
│              MCP Client (e.g., Claude Desktop)      │
└────────────────────────┬────────────────────────────┘
                         │ MCP protocol (STDIO or HTTP)
┌────────────────────────▼────────────────────────────┐
│                   server.py                         │
│   MCP Server — tool registration, request routing   │
│   Emits structured logs + Prometheus metrics        │
└────────────────────────┬────────────────────────────┘
                         │ delegates to
┌────────────────────────▼────────────────────────────┐
│                tools/ package                       │
│   discovery.py  │  pricing.py  │  estimation.py    │
│   Business logic: filtering, fan-out, aggregation   │
└────────────────────────┬────────────────────────────┘
                         │ calls
┌────────────────────────▼────────────────────────────┐
│                  client.py                          │
│   OTCPricingClient — httpx, retries, metrics        │
│   Enforces productType=OTC on every request         │
└────────────────────────┬────────────────────────────┘
                         │ returns ApiResponse
┌────────────────────────▼────────────────────────────┐
│               normalize.py / models.py              │
│   parse_price() — "0.051 EUR" → (Decimal, "EUR")   │
│   extract_items() — dict|list → list[PriceItem]     │
│   PriceItem (34 fields, extra="allow")              │
└────────────────────────┬────────────────────────────┘
                         │ HTTP GET
┌────────────────────────▼────────────────────────────┐
│         OTC Price Calculator REST API               │
│   https://calculator.otc-service.com/               │
│   en/open-telekom-price-api/                        │
│   Public, unauthenticated, read-only                │
└─────────────────────────────────────────────────────┘
```

---

## Process Architecture

The server runs two concurrent components in a single Python process:

```
python -m otc_pricing_mcp
        │
        ├─── asyncio event loop
        │    └── MCP STDIO server (main loop)
        │        Reads from stdin, writes to stdout
        │        Handles MCP protocol messages
        │
        └─── background Thread ("metrics-server")
             └── werkzeug WSGI server on :8080
                 ├── GET /healthz  → liveness probe
                 ├── GET /readyz   → readiness probe (HEAD to OTC API, cached 30s)
                 └── GET /metrics  → Prometheus text format
```

The STDIO transport is the primary MCP interface. The HTTP server is a sidecar concern (health checks, metrics scraping) that runs in a daemon thread and does not affect MCP communication.

---

## Request Data Flow

A typical tool invocation follows this path:

1. MCP client sends a `tools/call` message over STDIO
2. `server.py:call_tool()` receives the call, generates a `request_id`, starts a timer
3. The tool function in `tools/` is invoked with the parsed arguments
4. For pricing tools: `client.py:OTCPricingClient.get()` issues an HTTP GET to the OTC API
   - `productType=OTC` is always injected
   - On HTTP error: `tenacity` retries up to 3 times with exponential backoff (1s, 2s, 4s)
5. The raw JSON response is parsed into `ApiResponse` (Pydantic)
6. `normalize.py:extract_items()` normalizes the dict-or-list result shape to `list[PriceItem]`
7. Tool logic applies any additional filtering/aggregation
8. `server.py` records duration + status in Prometheus metrics and structured logs
9. Result is returned as `TextContent` to the MCP client

---

## Multi-Service Fan-Out

The OTC API only returns one service per request. Querying multiple services requires N parallel HTTP calls:

```
query_pricing(services=["ecs", "evs", "obs"])
       │
       ├── ThreadPoolExecutor(max_workers=5)
       │   ├── GET /...?serviceName=ecs
       │   ├── GET /...?serviceName=evs
       │   └── GET /...?serviceName=obs
       │
       └── merge results → {service: [items]}
           partial failure → results + warnings[]
```

If one service call fails, the other results are still returned with a `warnings` list describing what failed and why. This prevents a single flaky upstream endpoint from blocking an entire multi-service query.

---

## Key Design Decisions

### 1. Sync HTTP in an async server

`httpx` is used in sync mode (`httpx.Client`) even though the MCP server is async. The fan-out is parallelized via `ThreadPoolExecutor`, not `asyncio`. Rationale: the OTC API is called infrequently (on tool invocation, not per-message), and sync+threads is simpler to reason about and test than async with no performance difference at this call volume.

### 2. No caching layer

The OTC API returns `Cache-Control: private, max-age=900` (15-minute cache). Pricing data changes infrequently. Adding a server-side cache (Redis, in-memory LRU) would add operational complexity for marginal benefit. If profiling shows a need, this is a follow-up decision.

### 3. Price strings parsed to `Decimal`, never `float`

The API returns prices as strings like `"0.051175 EUR"`. These are parsed by `parse_price()` into `(Decimal, str)` tuples. `Decimal` prevents floating-point rounding errors in cost calculations. The currency code is always taken from the per-record `currency` field — the embedded suffix in the price string is validated but not trusted as the source of truth.

### 4. `extra="allow"` on all Pydantic models

The OTC API has 34 documented fields but the schema may evolve. All models use `ConfigDict(extra="allow")` so unknown fields are preserved rather than causing validation errors. New API fields are silently carried through; removed fields would surface as missing-attribute errors only if code explicitly accesses them.

### 5. Fail loudly on unknown product IDs

`estimate_monthly_cost` accepts product IDs (e.g., `OTC_S3M1_LI`) and fails with a clear error on unknown IDs rather than silently returning zero. Fuzzy matching would produce wrong cost estimates — a harder-to-detect failure mode.

### 6. German descriptions are documented, not translated

The API returns German-language `description` fields despite the `/en/` URL path. The wrapper documents this quirk (see `docs/api-quirks.md`) but does not attempt translation, as no `Accept-Language` override has any effect.

---

## Observability

### Prometheus Metrics

All metrics carry the `otc_pricing_mcp_` prefix:

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `otc_pricing_mcp_requests_total` | Counter | `tool`, `status` | MCP tool invocations |
| `otc_pricing_mcp_request_duration_seconds` | Histogram | `tool` | End-to-end tool latency |
| `otc_pricing_mcp_upstream_requests_total` | Counter | `service`, `status` | OTC API calls |
| `otc_pricing_mcp_upstream_duration_seconds` | Histogram | `service` | Upstream call latency |
| `otc_pricing_mcp_multi_service_requests_total` | Counter | — | Multi-service fan-out count |
| `otc_pricing_mcp_concurrent_requests` | Histogram | — | Parallelism per fan-out |

### Structured Logging

All log output is JSON via `structlog`. Every log entry includes:
- `event` — the log event name (snake_case)
- `level` — log level
- `timestamp` — ISO 8601
- `request_id` — UUID propagated from the MCP invocation context
- Tool-specific fields (e.g., `tool`, `service`, `duration_seconds`, `error`)

Log level is controlled via the `LOG_LEVEL` environment variable (default: `INFO`).

### Health Endpoints

| Endpoint | Purpose | Returns |
|----------|---------|---------|
| `GET /healthz` | Liveness | `200 {"status": "ok"}` always |
| `GET /readyz` | Readiness | `200` if OTC API HEAD succeeds; `503` otherwise (cached 30s) |
| `GET /metrics` | Prometheus scrape | Prometheus text format |

---

## Security Model

- **No authentication required**: The OTC Price Calculator API is public. No secrets are needed to run the server.
- **Container hardening**: Distroless final image (`gcr.io/distroless/python3`), non-root UID 65532, read-only root filesystem.
- **Network policy**: Kubernetes `NetworkPolicy` restricts egress to `calculator.otc-service.com:443` only; ingress from the ingress controller only.
- **Supply chain**: `pip-audit` (dependency CVEs), `bandit` (static analysis), `trivy` (container image scan) run in CI on every push and nightly.
- **SBOM**: CycloneDX SBOM generated and attached to every GitHub release.

---

## Deployment

The server is deployed to NEVIT's k3s cluster via ArgoCD GitOps:

```
GitHub repository (main branch)
        │
        │ auto-sync (ArgoCD)
        ▼
ArgoCD Application
        │ applies
        ▼
Kubernetes namespace: mcp-otc-pricing
        ├── Deployment (2 replicas, anti-affinity)
        │   ├── Resource requests: 100m CPU / 128Mi RAM
        │   ├── Resource limits:   500m CPU / 512Mi RAM
        │   └── Container: ghcr.io/<owner>/otc-pricing-mcp:latest
        ├── Service (ClusterIP :8080)
        ├── Ingress (TLS via cert-manager / Let's Encrypt)
        │   └── https://mcp-otc-pricing.nevit.ch/
        ├── ServiceMonitor (Prometheus Operator scrape config)
        ├── NetworkPolicy (egress → OTC API only)
        └── PodDisruptionBudget (minAvailable: 1)
```

ArgoCD is configured with `automated.prune: true` and `automated.selfHeal: true`, so the cluster state always converges to what is in the repository.

For local development and alternative deployment options, see `docs/deployment.md`.

---

## OTC API Quirks

The upstream API has several non-obvious behaviors that the wrapper papers over. Clients of this MCP server never see these details; they are handled internally.

| Quirk | Behavior | Mitigation |
|-------|----------|-----------|
| Result shape varies | Unfiltered: `result` is `{service: [...]}`. Filtered: `result` is `[...]` | `extract_items()` in `normalize.py` handles both |
| Multi-service broken | Repeated `serviceName=` params only return one service | Fan-out: one request per service, merged client-side |
| Filter syntax | `filterBy[region][0]=eu-ch2` returns 0 results; correct form is `filterBy[region]=eu-ch2` | Hard-coded correct form in `client.py` |
| German descriptions | `description` field is German despite `/en/` URL | Documented; not translated |
| Price strings | `"0.051175 EUR"` — amount and currency in one field | `parse_price()` splits into `(Decimal, str)` |
| No hard pagination | `limitMax=5000` returns all records for any service | Default `limitMax=5000` to fetch full catalog in one call |

Full details and curl examples are in `docs/api-quirks.md`.

---

## References

- OTC Price Calculator API: https://docs.otc.t-systems.com/price-calculator/api-ref/
- Model Context Protocol spec: https://modelcontextprotocol.io
- Python MCP SDK: https://github.com/modelcontextprotocol/python-sdk
- Project epic and original requirements: `EPIC_otc-pricing-mcp_1.md`
- API behavioral quirks: `docs/api-quirks.md`
- Service catalog inventory: `docs/catalog-inventory.md`
