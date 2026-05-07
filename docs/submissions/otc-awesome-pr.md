# Draft: PR for opentelekomcloud-community/otc-awesome

**Target repo**: https://github.com/opentelekomcloud-community/otc-awesome

**Status**: Needs manual filing by Mike (do not auto-submit — escalation required per project rules)

---

## PR title

`Add otc-pricing-mcp — MCP server for OTC Price Calculator API`

## PR body

```markdown
## Summary

Adds `otc-pricing-mcp` to a new **AI & LLM Tools** section under Projects.

This is an open-source Model Context Protocol (MCP) server that wraps the OTC Price Calculator REST API (`calculator.otc-service.com`), enabling any MCP-compatible LLM client (Claude Desktop, Claude Code, Cursor, etc.) to query OTC pricing with natural language.

- 7 MCP tools: service discovery, pricing queries, compute flavor search, monthly cost estimation, billing model comparison
- Covers all 3 OTC regions: eu-de (EUR), eu-nl (EUR), eu-ch2 (CHF)
- Production-ready: containerized, Helm chart, ArgoCD, full observability
- Apache 2.0 licensed

## Change

In `README.md`, after the CCE section and before Community Posts, add a new section:

### AI & LLM Tools

- [otc-pricing-mcp](https://github.com/seaser0/otc-pricing-mcp) — MCP server for the OTC Price Calculator API. Exposes 7 tools for pricing queries, compute flavor search, and cost estimation across eu-de, eu-nl, and eu-ch2 to any MCP-compatible LLM client.
```

---

## Where to insert in README.md

Find this section in `README.md`:

```markdown
### CCE

- [cce-argocd-bootstrap](...)
```

Insert a new `### AI & LLM Tools` subsection **after** the CCE section, before `## Community Posts`. Also add `[AI & LLM Tools](#ai--llm-tools)` to the Contents list under Projects.

---

## How to file

```bash
# Fork the repo, clone locally
gh repo fork opentelekomcloud-community/otc-awesome --clone
cd otc-awesome

# Make the change (insert new section per the draft above)
# Then:
git checkout -b add-otc-pricing-mcp
git add README.md
git commit -m "Add otc-pricing-mcp to AI & LLM Tools"
gh pr create \
  --repo opentelekomcloud-community/otc-awesome \
  --title "Add otc-pricing-mcp — MCP server for OTC Price Calculator API" \
  --body "$(cat <<'EOF'
Adds `otc-pricing-mcp` to a new **AI & LLM Tools** section.

This is an open-source MCP server wrapping the OTC Price Calculator API, enabling LLM clients like Claude Desktop and Claude Code to query OTC pricing data with natural language.

- 7 MCP tools (discovery, pricing, estimation)
- All 3 OTC regions: eu-de, eu-nl, eu-ch2
- Apache 2.0, containerized, production-ready
- https://github.com/seaser0/otc-pricing-mcp
EOF
)"
```
