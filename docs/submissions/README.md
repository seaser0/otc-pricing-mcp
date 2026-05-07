# Directory Submissions

Drafts for community directory submissions. All require **manual filing by Mike** — do not auto-submit.

| File | Directory | Status | Notes |
|------|-----------|--------|-------|
| `otc-awesome-pr.md` | [opentelekomcloud-community/otc-awesome](https://github.com/opentelekomcloud-community/otc-awesome) | Ready to file | File a PR adding a new "AI & LLM Tools" section |
| `mcp-registry.md` | [modelcontextprotocol/registry](https://github.com/modelcontextprotocol/registry) | Requires PyPI publication first | Uses `mcp-publisher` CLI, not a GitHub PR |
| `pulsemcp.md` | [pulsemcp.com](https://www.pulsemcp.com) | Ready to file | May be a web form or GitHub PR |
| `mcpservers-org.md` | [mcpservers.org](https://mcpservers.org) | Ready to file | May be a web form or GitHub PR |

## Action required for MCP registry

Before submitting to the MCP registry:

1. Add `<!-- mcp-name: io.github.seaser0/otc-pricing-mcp -->` to `README.md`
2. Publish the package to PyPI: `uv build && uv run twine upload dist/*`
3. Then follow the steps in `mcp-registry.md`
