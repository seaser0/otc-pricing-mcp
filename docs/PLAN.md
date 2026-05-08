# Implementation Plan: `otc-pricing-mcp`

## Goal Summary

Build an open-source Python MCP server that wraps the Open Telekom Cloud Price Calculator API, enabling LLM clients to query OTC pricing, explore services/regions, and compare billing models. The server is a strict catalog wrapper with no business logic, deployed to a k3s cluster via ArgoCD, and published under Apache 2.0.

## Understanding of the Scope

- The OTC Price Calculator API (`https://calculator.otc-service.com/en/open-telekom-price-api/`) exposes pricing data across multiple services (ECS, EVS, OBS, etc.) in multiple regions (eu-de, eu-nl, eu-ch2).
- The API has quirks: dict vs. flat-list result shapes depending on filters, broken multi-service syntax, currency-suffixed price strings, and an unconfirmed region filter syntax.
- We expose 7 MCP tools covering discovery (list_services, list_regions, get_service_schema), pricing queries (query_pricing, find_compute_flavor, estimate_monthly_cost, compare_billing_models).
- The probe script has already discovered the basic schema and identified that `filterBy[region][0]=eu-ch2` returns 0 items despite Swiss records existing in the unfiltered catalog.

## Execution Order & Parallelization

### Phase A — Foundation (parallel, ~1 day)
1. **Story 0 (Subagent)**: Catalog inventory & filter syntax discovery
   - Extend probe script to fetch full catalog with `limitMax=5000`
   - Determine correct `filterBy` syntax for region (test variants: `filterBy[region]=eu-ch2`, `filterBy[region][]=eu-ch2`, etc.)
   - Produce `docs/catalog-inventory.md` and `docs/api-quirks.md`
   - Deliverables: working filter syntax, proof of eu-ch2/CHF records

2. **You (main agent)**: Repository scaffold
   - Initialize `pyproject.toml` with `uv`, `ruff`, `mypy`, `pytest`, `structlog`, `prometheus-client`, `httpx`, `pydantic`, `mcp` SDK
   - Create directory structure: `src/otc_pricing_mcp/`, `tests/`, `deploy/`, `docs/`
   - Configure `ruff.toml`, `pyproject.toml` with quality gates (lint, format, type-check)
   - Set up `pytest` with fixtures directory and VCR cassettes

### Phase B — Core (sequential, you, ~3.5 days)
3. **Story 1**: Core API client & data normalization
   - `client.py`: httpx.Client with timeout, retries (tenacity), custom User-Agent
   - `normalize.py`: `parse_price()` for `"0.051175 EUR"` → `(Decimal("0.051175"), "EUR")`, `extract_items()` for dict/list shapes
   - `models.py`: Pydantic `PriceItem` (34 fields + `extra="allow"`), `ApiResponse` envelope
   - Tests: 100% coverage on `parse_price` edge cases

4. **Story 2**: MCP tool implementations (all 7 tools)
   - `tools/discovery.py`: `list_services`, `list_regions`, `get_service_schema`
   - `tools/pricing.py`: `query_pricing`, `find_compute_flavor`
   - `tools/estimation.py`: `estimate_monthly_cost`, `compare_billing_models`
   - LLM-focused descriptions; no extra API calls beyond what query_pricing makes

5. **Story 3**: Multi-service fan-out
   - Modify `query_pricing` to detect multi-service requests and fan out with ThreadPoolExecutor (max 5 concurrent)
   - Merge results and surface partial-failure warnings

### Phase C — Quality & Platform (parallel, ~3 days)
6. **Story 4 (you)**: Testing
   - Unit tests for `parse_price`, `extract_items`, models (≥90% coverage on normalize.py, models.py)
   - Integration tests marked `@pytest.mark.live`, VCR cassettes for CI replay
   - MCP conformance test against running server

7. **Story 5 (Subagent)**: Security
   - `pip-audit`, `bandit`, `trivy` configs in CI
   - Dockerfile multi-stage with distroless, non-root UID 65532, read-only root
   - SBOM generation (CycloneDX)

8. **Story 6 (Subagent)**: CI/CD GitHub Actions
   - `ci.yml`: PR/push checks (lint, type, unit tests, conformance)
   - `release.yml`: tag-triggered multi-arch build (amd64, arm64) → GHCR + GitHub release
   - `security.yml`: nightly scheduled scans

9. **Story 7 (Subagent)**: Observability
   - `/healthz`, `/readyz` (HEAD check to OTC API, cached 30s)
   - `/metrics` (Prometheus: request rate, latency, upstream stats)
   - Structured JSON logs via `structlog` with request_id
   - Grafana dashboard JSON

### Phase D — Deployment (sequential, you, ~2 days)
10. **Story 8**: Helm + ArgoCD
    - Helm chart in `deploy/helm/otc-pricing-mcp/`: Deployment, Service, Ingress, ServiceMonitor, NetworkPolicy, PDB
    - ArgoCD Application in `deploy/argocd/application.yaml`
    - Coordinates on hostname, namespace, resource limits

11. **Story 9 (Subagent with you review)**: Docs & publication
    - README (one-para what/why, quickstart, tool table, config reference)
    - CONTRIBUTING.md, SECURITY.md, LICENSE (Apache 2.0)
    - `docs/architecture.md`, `docs/tool-surface.md`, `docs/deployment.md`
    - Submit to MCP registry, PulseMCP, awesome-opentelekomcloud

## Critical Path

**1 → 2 → 3 → 4 → 6 → 8 → 9** (sequential core, ~7.5 days)
Stories **0, 5, 7** parallelize alongside the critical path.

## Ambiguities & Clarifications Needed

1. **Region filter syntax**: Story 0 will empirically determine whether `filterBy[region]=eu-ch2` (no bracket index) or another form is correct. The existing probe found `filterBy[region][0]=eu-ch2` returns 0 items.

2. **GitHub repository location**: Is the repo `github.com/opentelekomcloud-community/otc-pricing-mcp` or another org? Need confirmation before pushing.

3. **Hosted endpoint hostname**: Confirm the final subdomain for your deployment.

4. **Kubernetes namespace**: Should the deployment land in a specific namespace (e.g., `mcp-otc-pricing`)? Confirm resource limits and ingress class.

5. **Multi-arch images**: The release workflow should build for `linux/amd64` and `linux/arm64` — confirm both are needed or if amd64-only suffices for your cluster.

6. **SBOM attachment**: CycloneDX SBOM will be generated and attached to GitHub releases. Confirm this is your preference (vs. SPDX or other format).

## Quality Gates (Non-Negotiable)

All stories must pass before merge to `main`:
- `ruff check` + `ruff format --check` (zero issues)
- `mypy --strict` on `src/` (zero errors)
- `pytest` passes (unit + integration, VCR cassettes)
- `pip-audit` (zero medium+ CVEs)
- `bandit -r src/` (zero HIGH severity)
- Conformance: `mcp-inspector` lists all 7 tools
- Coverage: ≥90% on `normalize.py` and `models.py`

## Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Upstream API breaks our assumptions | Pydantic `extra="allow"` + nightly live tests catch it within 24h. Fail loudly with actual response. |
| Filter syntax differs from tested form | Story 0 owns this; empirical testing against live API + reference to official UI network calls. |
| Ingress/networking conflicts in k3s | Dedicated subdomain + NetworkPolicy to restrict egress to OTC API only. |
| MCP spec changes | Pin SDK version; bump deliberately; communicate to consumers. |

---

**Next Steps**: Confirm the ambiguities above, then begin Phase A (dispatch Story 0 subagent + start skeleton in parallel).
