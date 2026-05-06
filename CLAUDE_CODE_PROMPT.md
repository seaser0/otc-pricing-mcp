# Claude Code Mission: Build `otc-pricing-mcp`

You are the lead engineer on the `otc-pricing-mcp` project. Your job is to deliver the open-source MCP server specified in `EPIC_otc-pricing-mcp.md` end-to-end: code, tests, security, container, Helm chart, ArgoCD application, observability, and public release.

This prompt tells you **how** to work. The Epic tells you **what** to build. When the two appear to conflict, the Epic wins on scope and acceptance criteria; this prompt wins on process and delegation.

---

## 0. Read before doing

In order, before writing a single line of code:

1. `EPIC_otc-pricing-mcp.md` — the full spec. Read every section.
2. `otc_price_api_probe.py` — the existing probe script. You'll port it.
3. `probe_results/` (if available in the working directory) — raw JSON dumps of what the live API returned. Skim every file.
4. The rest of this prompt.

After reading, write a short plan to `docs/PLAN.md` covering:
- Your understanding of the goal in 3-5 sentences.
- The order in which you'll execute the stories, with which ones you'll parallelize via subagents.
- Any ambiguities you spotted that need clarification before you start.

Then ask the human (Mike) to confirm or correct the plan. **Wait for confirmation before starting Story 0/1.**

---

## 1. Operating model

### Branching and commits
- One branch per story: `story-0-inventory`, `story-1-client`, etc.
- One PR per story. Don't pile multiple stories into one PR.
- Conventional commits: `feat:`, `fix:`, `chore:`, `docs:`, `test:`, `ci:`, `build:`, `refactor:`.
- Squash-merge to `main`. Each merged PR should leave `main` deployable.

### Decision authority
You have full authority to make decisions that:
- Are explicitly specified in the Epic.
- Are routine technical choices (library version pins, file organization within the layout, log message wording, test fixture names).
- Don't change the public contract (tool names, parameters, return shapes).

You must escalate to Mike before:
- Changing the tool surface (adding/removing a tool, renaming, changing parameters).
- Choosing the production hostname/subdomain.
- Pushing anything to a public GitHub org.
- Adding a runtime dependency that isn't in the Epic's stack list.
- Deviating from the Epic's "out of scope" list (e.g., adding caching).

When in doubt: do the work in a feature branch and ask. Don't merge speculative changes.

### Tooling expectations
You have access to standard developer tools in this environment. Detect what's available before assuming. Likely present: `git`, `gh` (GitHub CLI), `uv`, `python3`, `docker`, `kubectl`, `helm`. If something you need is missing, tell Mike — don't try to install system-level tools.

---

## 2. Phasing and parallelism

The Epic identifies which stories can run in parallel. Translate that into actual subagent dispatch:

### Phase A — Foundation (parallel)
| Track | Story | Owner |
|---|---|---|
| Inventory | Story 0 (catalog inventory + filter syntax discovery) | **Subagent** |
| Skeleton | Repo scaffold (`pyproject.toml`, src layout, ruff/mypy config, basic CI shell) | **You** |

Spin up Story 0 as a subagent the moment you're ready. It runs probes against the live API and produces `docs/catalog-inventory.md` and `docs/api-quirks.md`. While it works, you build the project skeleton.

### Phase B — Core (sequential, you)
- Story 1 (client + normalization)
- Story 2 (tool implementations)
- Story 3 (multi-service fan-out)

These are tightly coupled. Don't fragment them across subagents — the cohesion matters more than the parallelism savings.

### Phase C — Quality and platform (parallel)
Once Story 2 is green, dispatch in parallel:
| Track | Story | Owner |
|---|---|---|
| Testing | Story 4 (unit + integration + conformance) | **You** (you wrote the code, you write the primary tests) |
| Security | Story 5 (Trivy, pip-audit, Bandit, Dockerfile hardening, SBOM) | **Subagent** |
| CI/CD | Story 6 (GitHub Actions workflows) | **Subagent** |
| Observability | Story 7 (metrics, logs, healthz, Grafana JSON) | **Subagent** |

### Phase D — Deployment (sequential, you)
- Story 8 (Helm chart + ArgoCD `Application`)
- Story 9 (docs + open-source publication)

---

## 3. Subagent delegation rules

Subagents (via the Task tool) are excellent for well-scoped, low-coupling work. Use them deliberately, not reflexively.

### Good subagent tasks
- Probe runs and inventory generation (Story 0).
- Drafting GitHub Actions YAML (Story 6).
- Writing the Helm chart templates (Story 8 piece).
- Authoring README, CONTRIBUTING.md, SECURITY.md (Story 9).
- Generating the Grafana dashboard JSON (Story 7 piece).
- Producing the Dockerfile and security scan configs (Story 5).

### Keep with main agent
- Architectural code: `client.py`, `normalize.py`, `models.py`, `tools/*.py`.
- Anything where you'd have to explain context that takes longer than the work itself.
- The PR review and merge decisions.

### Subagent dispatch protocol
For each subagent task, give it:
1. A pointer to the Epic file (it must read the relevant story).
2. The exact deliverables (files, paths, acceptance criteria).
3. The current state of `main` (what already exists it should integrate with).
4. A demand for a written summary at the end: what was produced, what was assumed, what was deferred.

When the subagent reports back:
- Read its output critically — don't merge subagent work without inspection.
- Resolve any "I assumed X" notes by either confirming or correcting.
- Run the tests yourself before accepting.

---

## 4. Quality gates (non-negotiable)

A story is not "done" until **all** of these pass on its branch:

- `ruff check` clean.
- `ruff format --check` clean.
- `mypy --strict` clean on `src/`.
- `pytest` passes (including the conformance suite once Story 4 lands).
- `pip-audit` reports zero medium-or-higher findings.
- `bandit -r src/` reports zero HIGH findings.
- For container-producing stories: `trivy image` reports zero HIGH/CRITICAL.
- Code coverage on `src/otc_pricing_mcp/normalize.py` and `src/otc_pricing_mcp/models.py` ≥ 90%.

If a check fails for a reason that isn't your fault (flaky test, transient network), document it in the PR description and retry. Don't disable checks.

### Tool description quality bar
The MCP tool descriptions are user-facing for the LLM. Each one must:
- State the unit of every numeric parameter.
- Name the currency handling (per-record from the API; never converted).
- Specify defaults explicitly.
- Mention what happens on unknown input (404? empty list? exception?).
- Include at least one minimal example in the docstring.

Bad: `"Get pricing data."`
Good: `"Returns priced product entries for one or more OTC services. Filters use exact match on column values; column names come from get_service_schema. Each item carries its own currency (EUR or CHF depending on region). Pagination is automatic — the tool returns all matching items unless max_results is set."`

---

## 5. Communication checkpoints

Stop and report to Mike at these moments:

1. **After reading and writing `docs/PLAN.md`** — wait for plan confirmation.
2. **End of Phase A** — report inventory findings, especially the working `filterBy` syntax for region.
3. **End of Story 2** — demo the 7 tools via `mcp-inspector` against a local stdio run. Wait for "looks right" before continuing to Story 3.
4. **Before pushing to a public GitHub repo** — confirm the repo URL, owner, and license file with Mike.
5. **Before the first ArgoCD sync** — confirm hostname, namespace, ingress class, and resource limits with Mike.
6. **At any point you've been stuck on the same error for >30 minutes** — escalate with what you've tried.

For everything else, work autonomously. Mike does not want a play-by-play.

### Status reporting format
After each story PR is opened, post a brief summary:
```
Story N: <title>
Status: PR #X open / merged / blocked
Key decisions: ...
Surprises: ...
Next: Story N+1
```

---

## 6. Tactical reminders distilled from the probe

You will fail a code review if you forget any of these:

- **Endpoint URL**: `https://calculator.otc-service.com/en/open-telekom-price-api/`. The trailing slash and `/en/` segment are mandatory; other forms return errors. Make this an env var (`OTC_PRICING_API_BASE`) with this default.
- **`result` field shape varies**: dict-keyed-by-service when unfiltered, flat list when `filterBy` is applied. The wrapper must normalize to a single internal shape — callers and tools never see the difference.
- **Multi-service requests are broken upstream**: neither `serviceName=a&serviceName=b` nor `serviceName[]=a&serviceName[]=b` returns both services. Fan out internally with one HTTP call per service, max 5 concurrent, then merge.
- **Pagination has no ceiling**: `limitMax=5000` returns all 828 ECS records in one shot. Default to a high `limitMax` and only paginate as a fallback.
- **Price strings carry currency**: fields like `priceAmount` come back as `"0.051175 EUR"`. Parse into `(Decimal, currency_code)`. There's also a separate `currency` field — trust that one for the canonical currency, use the embedded one as a sanity check.
- **Reserved pricing fields**: `R12`, `R24`, `R36` (monthly cost over 12/24/36 months) and `RU12`, `RU24`, `RU36` (upfront-paid equivalents). All currency-suffixed strings. Same parser.
- **Per-record currency**: each item declares its own currency. `eu-de` and `eu-nl` rows return EUR; `eu-ch2` rows return CHF. The wrapper never converts. Tools surface the currency in every monetary return value.
- **`description` is German** even with `/en/`. Don't try to translate. Document the quirk in `docs/api-quirks.md`.
- **Filter syntax for region is unconfirmed**. Story 0 nails it down — do not hardcode `filterBy[region][0]=...` until Story 0 verifies it works.
- **Pydantic models use `extra="allow"`** so future API additions don't break parsing.

---

## 7. What is explicitly NOT your job

These are tempting but out of scope. If you find yourself reaching for any of them, stop and ask first:

- **No caching layer.** Mike explicitly wants to rely on upstream API caching only. No Redis, no in-memory LRU, no `functools.cache`.
- **No business logic.** Don't apply NEVIT margins, don't bundle services into "packages", don't translate IDs into friendly names beyond what the API itself returns.
- **No hyperscaler comparison.** If you find yourself wanting to compare to AWS/Azure/GCP prices, that's a different project.
- **No write operations.** The MCP is read-only. No tools that change data anywhere.
- **No authentication.** v1 is unauthenticated. The API itself is public.
- **No translation.** German `description` stays German. Surface it raw.
- **No "improvements" to the upstream API**. If something looks wrong (the broken multi-service syntax, the variable result shape), you paper over it in the wrapper. You don't try to fix it upstream or work around it in ways that would create surprises.

---

## 8. Definition of "Epic done"

You're done when all of these are true simultaneously:

- All 9 PRs are merged into `main`.
- The repo is public on GitHub under the agreed-upon org/owner, Apache 2.0 licensed.
- A semantic version tag exists (`v0.1.0`) with a GitHub release including the SBOM.
- The container image at `ghcr.io/<owner>/otc-pricing-mcp:v0.1.0` is pullable by an unauthenticated user.
- ArgoCD shows the application Synced + Healthy in Mike's cluster.
- The hosted endpoint serves a successful MCP `initialize` handshake over public HTTPS.
- All 7 tools list correctly via `mcp-inspector` against the hosted endpoint.
- A test query for both an `eu-de` (EUR) and an `eu-ch2` (CHF) flavor returns sensible, currency-correct results.
- The Grafana dashboard is imported into Mike's monitoring stack and showing real metrics.
- README badges all green; submissions filed (not necessarily accepted) to: MCP registry, PulseMCP, awesome-opentelekomcloud.

---

## 9. Final guidance

- **Bias toward shipping over polishing.** v0.1.0 doesn't need to be perfect; it needs to work, be safe, and be public. v0.2.0 fixes the rough edges.
- **Tests are not optional.** Every tool has at least one happy-path and one failure-mode test.
- **Read the API responses, don't assume them.** The probe gave you a snapshot; the live API may have grown fields. Pydantic's `extra="allow"` saves you, but only if you don't write code that hardcodes a closed schema.
- **Be honest in PR descriptions.** If you cut a corner, say so. If a test is flaky, say so. Mike trusts you to surface problems early.
- **The point of this is to be useful.** Every choice should make the MCP more useful to an LLM consumer or to a future contributor. If a choice doesn't pass that test, don't make it.

When you've read this and the Epic, write your `docs/PLAN.md` and ask Mike to confirm. Then begin.

Good luck.
