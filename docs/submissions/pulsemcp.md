# Draft: PulseMCP Submission

**Directory**: https://www.pulsemcp.com

**Status**: Needs manual filing by Mike. Check current submission method at the URL above.

---

## Listing entry draft

Use this content when submitting to PulseMCP (adapt to whatever form fields they present):

| Field | Value |
|-------|-------|
| **Name** | OTC Pricing MCP |
| **Slug / ID** | `otc-pricing-mcp` |
| **Description** | MCP server for the Open Telekom Cloud (OTC) Price Calculator API. Enables any MCP-compatible LLM client to query pricing data, find compute flavors, estimate monthly costs, and compare PAYG vs reserved billing across all three OTC regions (eu-de, eu-nl, eu-ch2). |
| **Repository URL** | https://github.com/seaser0/otc-pricing-mcp |
| **Author / Maintainer** | seaser0 (s34s3r@gmail.com) |
| **License** | Apache 2.0 |
| **Language** | Python |
| **Transport** | stdio (primary), HTTP (`/mcp`) |
| **Hosted endpoint** | https://mcp-otc-pricing.example.com/mcp |
| **Categories / Tags** | cloud, pricing, opentelekомcloud, otc, infrastructure, cost-estimation |
| **Tools count** | 7 |
| **Authentication required** | No — the OTC Price Calculator API is public |

---

## Tools list (for any tool listing field)

1. `list_services` — List all OTC services with pricing data
2. `list_regions` — List available regions (eu-de, eu-nl, eu-ch2)
3. `get_service_schema` — Get columns and schema for a service
4. `query_pricing` — Flexible pricing query with filters and multi-service fan-out
5. `find_compute_flavor` — Find ECS instances by vCPU/RAM/OS
6. `estimate_monthly_cost` — Itemized monthly cost estimate for a resource list
7. `compare_billing_models` — PAYG vs Reserved 12/24/36-month cost comparison

---

## Long description (for any free-text field)

`otc-pricing-mcp` is a read-only MCP server that wraps the Open Telekom Cloud Price Calculator REST API (`calculator.otc-service.com`). It is a strict catalog wrapper — no business logic, no markup, no vendor-specific assumptions.

**Key capabilities:**
- Query pricing for 20+ OTC services (ECS, EVS, OBS, RDS, CCE, and more)
- Filter by region, flavor, OS, and other service-specific attributes
- Search for compute flavors by vCPU, RAM, and OS
- Estimate monthly costs for a list of resources (PAYG and reserved)
- Compare PAYG vs 12/24/36-month reserved billing with savings percentages
- Covers eu-de (EUR), eu-nl (EUR), and eu-ch2 (CHF)

**Production-ready:** containerized (distroless), Helm chart, ArgoCD GitOps, Prometheus metrics, structured JSON logs, health endpoints.

---

## Submission process notes

PulseMCP may use a GitHub-based submission (PR to their repo) or a web form. Check https://www.pulsemcp.com/submit (or similar) for the current process. If it's a web form, fill in the fields from the table above. If it's a GitHub PR, the listing format will depend on their repo structure.
