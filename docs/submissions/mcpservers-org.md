# Draft: mcpservers.org Submission

**Directory**: https://mcpservers.org

**Status**: Needs manual filing by Mike. Check current submission method at the URL above (look for "Submit" or "Add Server").

---

## Listing entry draft

| Field | Value |
|-------|-------|
| **Name** | OTC Pricing MCP |
| **Short description** | MCP server for the Open Telekom Cloud Price Calculator API |
| **GitHub URL** | https://github.com/seaser0/otc-pricing-mcp |
| **Hosted URL** | https://mcp-otc-pricing.example.com/mcp |
| **Category** | Cloud / Infrastructure |
| **Tags** | cloud, pricing, otc, open-telekom-cloud, cost-estimation, infrastructure |
| **Language** | Python |
| **License** | Apache 2.0 |
| **Auth required** | No |

---

## Full description

An open-source Model Context Protocol server that wraps the **Open Telekom Cloud (OTC) Price Calculator API**. Enables LLM clients (Claude Desktop, Claude Code, Cursor, etc.) to query OTC pricing data using natural language.

**7 tools:**
- `list_services` / `list_regions` / `get_service_schema` — catalog discovery
- `query_pricing` — flexible pricing queries with region filters and parallel multi-service fan-out
- `find_compute_flavor` — search ECS instances by vCPU, RAM, OS
- `estimate_monthly_cost` — itemized monthly cost for a list of resources
- `compare_billing_models` — PAYG vs Reserved 12/24/36-month side-by-side

**Regions**: eu-de (EUR), eu-nl (EUR), eu-ch2 (CHF)

**Install (stdio mode):**
```bash
git clone https://github.com/seaser0/otc-pricing-mcp.git
cd otc-pricing-mcp && uv sync
python -m otc_pricing_mcp
```

**Claude Desktop config:**
```json
{
  "mcpServers": {
    "otc-pricing": {
      "command": "python",
      "args": ["-m", "otc_pricing_mcp"]
    }
  }
}
```

---

## Submission process notes

mcpservers.org may accept submissions via a GitHub PR to their repository or through a web form. Common approaches:

1. **Web form**: Navigate to https://mcpservers.org and look for a "Submit" or "Add Server" button. Fill in the fields from the table above.
2. **GitHub PR**: If the site is maintained as a GitHub repo, fork it, add an entry in the appropriate data file (JSON/YAML/markdown), and open a PR.

Use the content above for either submission method.
