# Epic: `otc-pricing-mcp` — Open Telekom Cloud Price Calculator MCP Server

| | |
|---|---|
| **Owner** | NEVIT Platform Engineering |
| **Status** | Ready for development |
| **Visibility** | Public (Apache 2.0, open source) |
| **Target deployment** | NEVIT k3s cluster, GitOps via ArgoCD, exposed under `nevit.ch` |
| **Implementation agent** | Claude Code (Opus 4.7) |
| **Repository (proposed)** | `github.com/<owner>/otc-pricing-mcp` |

---

## 1. Context & Goal

The Open Telekom Cloud (T Cloud Public) exposes a public, unauthenticated Price Calculator REST API at `https://calculator.otc-service.com/en/open-telekom-price-api/`. There is no existing MCP server for it (verified across `modelcontextprotocol/servers`, PulseMCP, mcpservers.org, and the official `opentelekomcloud-*` GitHub orgs).

This Epic delivers a Python MCP server that exposes the OTC Price Calculator to any MCP-compatible LLM client (Claude Desktop, Claude Code, OpenClaw agents, Cursor, etc.), hosted on NEVIT's k3s cluster and published as open source. The server is a **strict catalog wrapper** — no business logic, no markup, no NEVIT-specific assumptions.

### In scope
- Read-only MCP server wrapping the OTC Price Calculator API
- 7 MCP tools (see §4)
- Container image, Helm chart, ArgoCD `Application`
- CI/CD, security scanning, observability
- Public open-source release

### Out of scope
- Hyperscaler comparison (AWS/Azure/GCP pricing)
- NEVIT margin, package definitions, proposal generation
- Local caching layer (rely on upstream API caching)
- Authentication/authorization (API is public; MCP server stays unauthenticated for v1)
- Write operations (API is read-only by nature)

---

## 2. Probe findings (binding for implementation)

These are confirmed empirically against the live API on 2026-05-06. The implementation must respect them:

| Topic | Finding | Implication |
|---|---|---|
| Endpoint | `https://calculator.otc-service.com/en/open-telekom-price-api/` (trailing slash, `/en/` segment, both required) | Hard-code as default; expose as env var `OTC_PRICING_API_BASE` |
| `result` shape | Dict `{service: [...]}` when unfiltered; flat list `[...]` when `filterBy` is applied | Wrapper must normalize to a consistent internal shape |
| Pagination | No hard ceiling on `limitMax`. At `limitMax=5000`, server returns all 828 ECS records in one call | Default to one request per service with a high `limitMax` (e.g., 5000); paginate only if hit |
| Multi-service | Neither `serviceName=a&serviceName=b` nor `serviceName[]=a&serviceName[]=b` returns both services. Only one comes back | Fan out: one HTTP request per service, then merge |
| Price format | Strings like `"0.051175 EUR"` (amount + currency in one field); separate `currency: "EUR"` field also present | Parser must split into `(Decimal, currency_code)`; never trust ambiguous strings downstream |
| Reserved pricing | Fields `R12`, `R24`, `R36` (reserved monthly) and `RU12`, `RU24`, `RU36` (reserved upfront), all currency-suffixed strings | Parse the same way; expose alongside PAYG `priceAmount` |
| Region values | `productType=OTC` is the unified catalog and includes Swiss (`eu-ch2`) records alongside `eu-de` and `eu-nl`. The probe's test 2 sampled only the first 100 of 828 ECS records and didn't happen to see Swiss rows; full pagination shows them. | Single MCP serves all regions; no separate `productType` switch needed |
| Currency | Each record carries its own `currency` field (`EUR` for `eu-de`/`eu-nl`, `CHF` for `eu-ch2`) plus a currency-suffixed `priceAmount` string | Wrapper trusts the per-record currency; never converts |
| Locale | `description` field returns German content despite `/en/` URL | Document; do not attempt to translate |
| Schema | 34 fields per ECS item including `id`, `_idGroup`, `productId`, `productName`, `productCategory`, `productFamily`, `opiFlavour`, `serviceType`, `osUnit`, `vCpu`, `ram`, `region`, `unit`, `isMRC`, `fromOn`, `upTo`, `minAmount`, `maxAmount`, `idGroupTiered`, `storageType`, `storageVolume` | Pydantic models cover these explicitly; allow `extra = "allow"` for forward-compat |

### Filter syntax to investigate

The probe's `filterBy[region][0]=eu-ch2` returned 0 items even though the wider catalog contains Swiss rows. This is a filter-syntax issue, not a data availability issue. Story 1 will determine the correct form (likely `filterBy[region]=eu-ch2` without the `[0]` index, or a different parameter name entirely) by inspecting how the official price calculator UI's network requests are structured.

---

## 3. Architecture

### Stack
- **Language**: Python 3.12+
- **MCP SDK**: [`mcp`](https://github.com/modelcontextprotocol/python-sdk) (FastMCP-style decorators)
- **HTTP client**: `httpx` (sync mode; async is overkill for this workload)
- **Models**: `pydantic` v2
- **Project mgmt**: `uv` (lockfile, fast resolver)
- **Lint/format**: `ruff`
- **Type check**: `mypy --strict`
- **Tests**: `pytest`, `pytest-vcr` for cassette-based replay
- **Logging**: `structlog` (JSON output)
- **Metrics**: `prometheus-client`

### Transport
- **Streamable HTTP** (MCP spec ≥ 2025-11-25), exposed at `/mcp`
- Stateless — no session storage; every request is independently servable
- Optional **stdio** mode for local debugging (`python -m otc_pricing_mcp --stdio`)

### Repository layout
```
otc-pricing-mcp/
├── README.md
├── LICENSE                       # Apache 2.0
├── CONTRIBUTING.md
├── CODE_OF_CONDUCT.md
├── SECURITY.md
├── pyproject.toml
├── uv.lock
├── src/otc_pricing_mcp/
│   ├── __init__.py
│   ├── __main__.py               # CLI entrypoint
│   ├── server.py                 # FastMCP server, tool registration
│   ├── client.py                 # httpx wrapper around the OTC API
│   ├── models.py                 # Pydantic models for API responses
│   ├── normalize.py              # Handle dict/list result shapes; price string parser
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── discovery.py          # list_services, list_regions, get_service_schema
│   │   ├── pricing.py            # query_pricing, find_compute_flavor
│   │   └── estimation.py         # estimate_monthly_cost, compare_billing_models
│   └── observability.py          # Prometheus metrics, healthz/readyz, logging setup
├── tests/
│   ├── unit/
│   ├── integration/              # @pytest.mark.live — hit real API
│   ├── conformance/              # MCP protocol conformance via mcp-inspector
│   └── fixtures/                 # VCR cassettes
├── deploy/
│   ├── Dockerfile                # Multi-stage, distroless final
│   ├── helm/otc-pricing-mcp/
│   │   ├── Chart.yaml
│   │   ├── values.yaml
│   │   └── templates/
│   └── argocd/
│       └── application.yaml
├── .github/workflows/
│   ├── ci.yml
│   ├── release.yml
│   └── security.yml
└── docs/
    ├── architecture.md
    ├── tool-surface.md
    └── deployment.md
```

---

## 4. Tool surface (target spec)

Names, signatures, and descriptions are binding for the MCP tool registration. Descriptions are written for LLM consumption — they should be precise about parameters and return shapes.

| Tool | Purpose |
|---|---|
| `list_services` | Catalog of services with pricing data |
| `list_regions` | Available regions per `product_type` |
| `get_service_schema` | Filterable/returnable columns for a service |
| `query_pricing` | Flexible raw query (services × filters × columns) |
| `find_compute_flavor` | Convenience search for VMs by vCPU/RAM/OS |
| `estimate_monthly_cost` | Itemized monthly cost from a list of resources |
| `compare_billing_models` | PAYG vs Reserved 12/24/36 side-by-side |

Detailed signatures live in `docs/tool-surface.md` and were drafted previously — Claude Code should treat them as the starting point and refine field names against the actual probe schema (Story 1 outputs).

---

## 5. Stories

### Story 0 — Catalog inventory & filter syntax discovery
**Goal**: Produce a definitive inventory of services, regions, and currencies in `productType=OTC`, and identify the correct `filterBy` syntax for region filtering. Non-blocking — Story 1 can start in parallel once the inventory is at hand.

**Tasks**
- Extend the probe script (`scripts/probe.py`, port from `otc_price_api_probe.py`) to fetch the full catalog (`limitMax=5000`) for every known service.
- Produce `docs/catalog-inventory.md` listing: services × regions × currencies × record counts. Confirm `eu-ch2` rows exist with `currency=CHF`.
- Empirically determine the working `filterBy` form for `region` by trying variants: `filterBy[region]=eu-ch2`, `filterBy[region][]=eu-ch2`, `filterBy[region][0]=eu-ch2`, and inspecting the official Price Calculator web UI's network calls (browser devtools) for reference.
- Document the canonical filter syntax in `docs/api-quirks.md` alongside the dict/list result-shape note and the multi-service workaround.

**Acceptance criteria**
- `docs/catalog-inventory.md` exists and shows `eu-ch2` records with `CHF` prices.
- `docs/api-quirks.md` documents the working `filterBy` form with a runnable curl example.
- The probe script can be re-run by anyone to regenerate the inventory.

**Estimate**: 0.5 day

---

### Story 1 — Core API client and data normalization
**Goal**: Reliable, typed, side-effect-isolated wrapper around the OTC API.

**Tasks**
- `client.py`: `httpx.Client` with sane defaults (timeout 30s, retries with backoff via `tenacity`, custom `User-Agent: otc-pricing-mcp/<version>`).
- `normalize.py`:
  - `parse_price(s: str) -> tuple[Decimal, str]` — handles `"0.051175 EUR"`, `"0.000000 EUR"`, `"23.150000 CHF"`, etc.
  - `extract_items(response, service) -> list[PriceItem]` — handles both dict and list shapes.
- `models.py`:
  - `PriceItem` (Pydantic) covering all 34 known fields plus `model_config = ConfigDict(extra="allow")` for forward-compat.
  - `ApiResponse` envelope with `stats`, `parameters`, `result`, `columns`, `code`, `message`.
- All API access goes through the client; no `requests`/`urllib` calls anywhere else.

**Acceptance criteria**
- `parse_price` has 100% line coverage with edge cases (`"0.000000 EUR"`, missing currency, malformed input → `ValueError`).
- Round-trip test: fetch real ECS data → parse → re-serialize, no field loss.
- `mypy --strict` passes on `client.py`, `models.py`, `normalize.py`.

**Estimate**: 1 day

---

### Story 2 — MCP tool implementations
**Goal**: All 7 tools registered and callable via MCP.

**Tasks**
- Implement each tool as a function decorated with `@mcp.tool(...)`.
- Tool descriptions written for LLM consumption — explicit about units, defaults, currency handling.
- `find_compute_flavor` and `compare_billing_models` are pure derivations on top of `query_pricing` — no extra API calls beyond what `query_pricing` makes.
- `estimate_monthly_cost` accepts items by `id` (e.g., `OTC_S3M1_LI`) — no fuzzy matching, fail loudly on unknown IDs.

**Acceptance criteria**
- All 7 tools listed in `mcp-inspector` with rendered schemas.
- Each tool has at least one happy-path example in its docstring.
- `query_pricing` accepts both single and multi-service requests; multi-service is fanned out internally and merged.

**Estimate**: 2 days

---

### Story 3 — Multi-service fan-out
**Goal**: Make multi-service requests work despite the upstream API limitation.

**Tasks**
- In `query_pricing`, if `services` has length > 1, issue N HTTP calls in parallel via `httpx` with a `ThreadPoolExecutor` (concurrency cap of 5).
- Merge results into the canonical normalized shape `{service: [items]}`.
- Surface partial-failure: if 2 of 3 services succeed, return the 2 with a `warnings` field listing what failed and why.

**Acceptance criteria**
- Calling `query_pricing(services=["ecs", "evs", "obs"])` returns a dict with all three keys populated.
- Simulated failure (mocked 500 on one service) returns the other two plus a non-empty `warnings` list.

**Estimate**: 0.5 day

---

### Story 4 — Testing
**Goal**: Confidence to refactor without breaking real behavior.

**Tasks**
- **Unit tests** (`tests/unit/`): pure-function tests for `parse_price`, `extract_items`, models. No network. Coverage target ≥ 90% on `normalize.py` and `models.py`.
- **Integration tests** (`tests/integration/`): hit the real API. Marked `@pytest.mark.live`, skipped by default in CI unless `OTC_LIVE=1` is set. Run nightly via scheduled GitHub Action.
- **VCR cassettes**: `pytest-vcr` records real responses once, replays them in CI. Cassettes committed to repo (responses are public data).
- **MCP conformance**: `mcp-inspector` invocation in CI against the running server, asserts all 7 tools list correctly.

**Acceptance criteria**
- `pytest` passes locally and in CI without network.
- `pytest -m live` passes against the live API on a fresh machine.
- `mcp-inspector` reports 0 protocol errors.

**Estimate**: 1.5 days

---

### Story 5 — Security
**Goal**: No supply-chain or container surprises before publication.

**Tasks**
- **Dependency audit**: `uv pip audit` (or `pip-audit`) in CI. Fail on any CVE ≥ medium.
- **SBOM**: generate CycloneDX SBOM via `cyclonedx-py` on release, attach to GitHub release.
- **Container scan**: `trivy image` step in CI against the built image. Fail on HIGH/CRITICAL.
- **Static analysis**: `bandit -r src/`. Fail on any HIGH severity finding.
- **Container hardening**: Dockerfile uses `distroless` final stage, runs as non-root UID 65532, read-only root filesystem.
- **Network policy**: Kubernetes `NetworkPolicy` restricts egress to `calculator.otc-service.com:443` only.
- **No secrets**: API is public; document that no secrets are needed. If the MCP itself ever needs auth, that's a follow-up Epic.

**Acceptance criteria**
- All scans pass in CI on the `main` branch.
- SBOM is attached to every GitHub release.
- The container, when launched with the wrong egress, fails closed.

**Estimate**: 1 day

---

### Story 6 — CI/CD pipeline
**Goal**: Automated build, test, scan, publish.

**Tasks**
- `.github/workflows/ci.yml`: triggered on PR + push to `main`. Runs lint, type check, unit tests, conformance, security scans.
- `.github/workflows/release.yml`: triggered on git tag `v*.*.*`. Builds multi-arch container (`linux/amd64`, `linux/arm64`) via `docker buildx`, pushes to `ghcr.io/<owner>/otc-pricing-mcp`, creates GitHub release with SBOM.
- `.github/workflows/security.yml`: nightly scheduled scan (Trivy, pip-audit) against `main`, opens an issue on findings.
- Semantic versioning via [`commitizen`](https://commitizen-tools.github.io/commitizen/) or manual tags.

**Acceptance criteria**
- A PR with no functional changes shows all green checks.
- Tagging `v0.1.0` produces a GitHub release with image, SBOM, and changelog.
- Image is pullable from GHCR by an unauthenticated user.

**Estimate**: 1 day

---

### Story 7 — Observability
**Goal**: Operable in production from day one.

**Tasks**
- `/healthz` endpoint — liveness, always 200 if process is up.
- `/readyz` endpoint — readiness, performs a HEAD against the OTC API (cached for 30s), 200 if reachable.
- `/metrics` endpoint — Prometheus format. Metrics:
  - `otc_pricing_mcp_requests_total{tool, status}`
  - `otc_pricing_mcp_request_duration_seconds{tool}` (histogram)
  - `otc_pricing_mcp_upstream_requests_total{service, status}`
  - `otc_pricing_mcp_upstream_duration_seconds{service}` (histogram)
- Structured JSON logs via `structlog`, including `request_id` propagated from MCP context.
- Grafana dashboard JSON shipped in `docs/grafana-dashboard.json` (request rate, p95 latency, upstream error rate).

**Acceptance criteria**
- Prometheus scrape works against the deployed pod.
- The shipped dashboard imports cleanly and shows all 4 panels with real data.
- A failed upstream call produces a structured error log and increments the corresponding counter.

**Estimate**: 1 day

---

### Story 8 — ArgoCD deployment to NEVIT k3s
**Goal**: GitOps-managed deployment under `nevit.ch`.

**Tasks**
- **Helm chart** in `deploy/helm/otc-pricing-mcp/`:
  - Deployment with 2 replicas, anti-affinity across nodes.
  - Resource requests/limits: 100m CPU / 128Mi RAM request, 500m CPU / 512Mi RAM limit.
  - `Service` (ClusterIP).
  - `Ingress` with cert-manager annotations for Let's Encrypt; hostname `mcp-otc-pricing.nevit.ch` (or as decided).
  - `ServiceMonitor` for Prometheus Operator.
  - `NetworkPolicy` (egress to OTC API only, ingress from ingress controller only).
  - `PodDisruptionBudget` (minAvailable: 1).
- **ArgoCD `Application`** in `deploy/argocd/application.yaml`:
  - Source: this repo, path `deploy/helm/otc-pricing-mcp`.
  - Destination: `in-cluster`, namespace `mcp-otc-pricing`.
  - Sync policy: automated, prune true, self-heal true.
  - Retry on failure with exponential backoff.
- Wave/sync ordering if needed (probably not for this app).

**Acceptance criteria**
- ArgoCD shows the application Synced + Healthy.
- `https://mcp-otc-pricing.nevit.ch/healthz` returns 200 over public TLS.
- Pod logs show structured JSON.
- Killing one pod still serves traffic on the other.
- Network policy blocks egress to anywhere except `calculator.otc-service.com:443`.

**Estimate**: 1 day

---

### Story 9 — Documentation & open-source publication
**Goal**: Repository is genuinely useful to outside contributors.

**Tasks**
- **README.md**:
  - One-paragraph what/why.
  - Quickstart: `npx mcp-inspector` against hosted endpoint, plus stdio install.
  - Tool surface table with one example per tool.
  - Configuration reference.
  - Hosted endpoint URL.
- **CONTRIBUTING.md**: dev setup with `uv`, test instructions, PR conventions.
- **SECURITY.md**: how to report vulnerabilities (private email or GitHub Security Advisory).
- **LICENSE**: Apache 2.0.
- **`docs/architecture.md`**: this Epic, distilled.
- **`docs/tool-surface.md`**: full tool reference with parameter tables.
- **`docs/deployment.md`**: how to run via Docker, Helm, or Claude Desktop config.
- **Submissions**:
  - Open a PR against `opentelekomcloud-community/awesome-opentelekomcloud` to add the project.
  - Submit to the official MCP registry (`modelcontextprotocol/registry`).
  - Submit to PulseMCP and mcpservers.org directories.
  - Optional: announce in the OTC community forum and on Mattermost.

**Acceptance criteria**
- A new contributor can clone the repo and have a working dev environment in under 5 minutes.
- All four directory submissions are at least filed (acceptance is out of our control).
- README renders cleanly on GitHub and includes badges (CI, release, license, MCP-compatible).

**Estimate**: 1 day

---

## 6. Total estimate & sequencing

| Story | Days | Depends on |
|---|---|---|
| 0 — Catalog inventory & filter syntax | 0.5 | — |
| 1 — Core client | 1.0 | — (can start in parallel with 0) |
| 2 — Tools | 2.0 | 0, 1 |
| 3 — Multi-service fan-out | 0.5 | 2 |
| 4 — Testing | 1.5 | 2, 3 |
| 5 — Security | 1.0 | 4 (parallel-able) |
| 6 — CI/CD | 1.0 | 4 |
| 7 — Observability | 1.0 | 2 |
| 8 — ArgoCD deployment | 1.0 | 5, 6, 7 |
| 9 — Docs & publication | 1.0 | 8 |
| **Total** | **~10 days** | |

Critical path: 1 → 2 → 4 → 6 → 8 → 9 ≈ 7.5 days. Stories 0, 3, 5, 7 parallelize.

---

## 7. Definition of Done (Epic-level)

- [ ] All 9 stories closed with their AC met.
- [ ] Repository is public on GitHub, Apache 2.0 licensed.
- [ ] Container image tagged `v0.1.0` published on GHCR with SBOM.
- [ ] `https://mcp-otc-pricing.nevit.ch/mcp` reachable from the internet, registered in Claude Desktop and OpenClaw.
- [ ] At least one external entry created in the MCP registry / PulseMCP / awesome-opentelekomcloud.
- [ ] README badges show all green CI, license, latest release.
- [ ] Grafana dashboard live in NEVIT's monitoring stack with 7 days of metrics.

---

## 8. Implementation notes for Claude Code (Opus 4.7)

- **Story 0 and Story 1 can run in parallel.** The inventory work (Story 0) is reference material that informs tool design; the client (Story 1) can begin against the known schema while inventory completes.
- **Use the existing probe script** (`otc_price_api_probe.py`) as the starting point; port it to `scripts/probe.py` and extend.
- **Treat field names as data, not code.** The 34 fields documented in §2 are real but may evolve. Use Pydantic with `extra="allow"` and prefer dict access in tool implementations over hardcoded attribute access where the field could disappear.
- **Hide all upstream weirdness** behind the client + normalize layer. Tool authors and end users should never see the dict-or-list shape ambiguity, the broken multi-service syntax, or the embedded-currency price strings. Those are upstream bugs we paper over.
- **Version the API contract.** Tag the Pydantic schema with a comment referencing the probe date. If the upstream API breaks our assumptions, fail loudly and clearly with the actual response in the error.
- **Don't over-engineer caching.** The user explicitly wants to rely on upstream caching only. No Redis, no in-memory LRU. If profiling later shows a need, file a follow-up issue.
- **Keep tool descriptions LLM-shaped.** Each tool's description should explicitly mention units, currency, defaults, and what happens on unknown inputs. The LLM consuming this doesn't read code — it reads descriptions.
- **Commits**: conventional commits (`feat:`, `fix:`, `chore:`, etc.). One story per branch, one PR per story.
- **Push early, push often.** ArgoCD auto-sync means main = production. Use feature branches for everything; merge only with green CI.

---

## 9. Risks & open items

| Risk | Mitigation |
|---|---|
| Upstream API changes shape without notice | Pydantic `extra="allow"` + nightly integration test catches it within 24h. |
| Region filter syntax differs from documented form | Story 0 nails this down empirically against the live API. |
| `nevit.ch` ingress conflicts with existing services | Use a dedicated subdomain; coordinate with existing ingress rules. |
| MCP spec evolves before v1.0 | Pin `mcp` SDK version; bump deliberately. |
| Open-source visibility creates support burden | `SECURITY.md` and `CONTRIBUTING.md` set expectations; issues triaged weekly, no SLA. |

---

## 10. References

- OTC Price Calculator API docs: https://docs.otc.t-systems.com/price-calculator/api-ref/
- Probe script & raw findings: `otc_price_api_probe.py` + `probe_results/`
- Model Context Protocol spec: https://modelcontextprotocol.io
- Python MCP SDK: https://github.com/modelcontextprotocol/python-sdk
- OTC community org: https://github.com/opentelekomcloud-community
- Awesome OpenTelekomCloud list: https://github.com/opentelekomcloud-community/awesome-opentelekomcloud
