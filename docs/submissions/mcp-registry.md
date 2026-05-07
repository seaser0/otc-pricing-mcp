# Draft: MCP Registry Submission (modelcontextprotocol/registry)

**Registry**: https://github.com/modelcontextprotocol/registry

**Status**: Needs manual filing by Mike. Requires PyPI publication first.

---

## Submission process (as of 2026-05-07)

The MCP Registry does **not** accept PRs to add servers. Submission is done via the `mcp-publisher` CLI tool. The server must be published on a supported package registry (PyPI for Python) first.

### Pre-requisites

1. PyPI account (https://pypi.org)
2. Package `otc-pricing-mcp` published on PyPI
3. `mcp-name` verification string added to the package README (see below)
4. Node.js (to run `mcp-publisher`)

### Step 1: Add verification string to README.md

Add this hidden comment **anywhere** in `README.md` (e.g., at the bottom before "Built with ❤️"):

```html
<!-- mcp-name: io.github.seaser0/otc-pricing-mcp -->
```

This is required for PyPI ownership verification. The `io.github.seaser0/` prefix must match the GitHub account used for authentication.

### Step 2: Publish to PyPI

```bash
# Build the distribution
uv build

# Upload to PyPI (requires TWINE_USERNAME / TWINE_PASSWORD or API token)
uv run twine upload dist/*
```

Make sure the PyPI package README includes the `mcp-name` comment above.

### Step 3: Create server.json

Create a file named `server.json` (can be anywhere — it is sent to the CLI, not committed to the repo):

```json
{
  "$schema": "https://static.modelcontextprotocol.io/schemas/2025-12-11/server.schema.json",
  "name": "io.github.seaser0/otc-pricing-mcp",
  "title": "OTC Pricing MCP",
  "description": "MCP server for the Open Telekom Cloud Price Calculator API. Query pricing data, find compute flavors, estimate monthly costs, and compare PAYG vs reserved billing across eu-de, eu-nl, and eu-ch2 regions.",
  "version": "0.1.0",
  "repository": {
    "url": "https://github.com/seaser0/otc-pricing-mcp"
  },
  "packages": [
    {
      "registryType": "pypi",
      "identifier": "otc-pricing-mcp",
      "version": "0.1.0",
      "transport": {
        "type": "stdio"
      },
      "runtimeArguments": ["-m", "otc_pricing_mcp"]
    }
  ]
}
```

### Step 4: Publish using mcp-publisher

```bash
# Install mcp-publisher
npm install -g @modelcontextprotocol/publisher

# Authenticate (GitHub-based auth)
mcp-publisher auth login

# Publish
mcp-publisher publish --server server.json
```

---

## Tool listing for registry metadata

When the registry asks for tool descriptions, use these one-liners:

| Tool | Description |
|------|-------------|
| `list_services` | List all available OTC services with pricing data |
| `list_regions` | List available OTC regions (eu-de, eu-nl, eu-ch2) |
| `get_service_schema` | Get filterable/returnable columns for a service |
| `query_pricing` | Query pricing records with flexible filters and fan-out |
| `find_compute_flavor` | Find ECS instances matching vCPU/RAM/OS criteria |
| `estimate_monthly_cost` | Calculate itemized monthly cost for a resource list |
| `compare_billing_models` | Compare PAYG vs Reserved 12/24/36-month billing side-by-side |

---

## References

- Publishing quickstart: https://github.com/modelcontextprotocol/registry/blob/main/docs/modelcontextprotocol-io/quickstart.mdx
- Package types (PyPI): https://github.com/modelcontextprotocol/registry/blob/main/docs/modelcontextprotocol-io/package-types.mdx
- Registry CONTRIBUTING.md: https://github.com/modelcontextprotocol/registry/blob/main/CONTRIBUTING.md
