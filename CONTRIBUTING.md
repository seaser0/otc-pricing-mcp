# Contributing to OTC Pricing MCP

Thank you for your interest in contributing! This guide will help you get started quickly. The OTC Pricing MCP server enables LLMs to query Open Telekom Cloud pricing data, and we appreciate community contributions.

## Quick Start (< 5 minutes)

### Prerequisites
- Python 3.12 or later
- `uv` package manager ([install uv](https://docs.astral.sh/uv/))
- Git

### Setup

```bash
# Clone the repository
git clone https://github.com/seaser0/otc-pricing-mcp.git
cd otc-pricing-mcp

# Install dependencies
uv sync

# Run tests to verify setup
uv run pytest tests/ -v

# Expected output: All tests pass
```

If all tests pass, your environment is ready to develop!

## Development Workflow

### Running the Server Locally

The MCP server communicates via STDIO (standard input/output). To test locally:

```bash
# Start the server in STDIO mode
uv run python src/server.py

# The server waits for MCP protocol messages on stdin
# To quit, press Ctrl+C
```

### Making Changes

1. **Create a new branch** for your work:
   ```bash
   git checkout -b feature/my-feature
   ```

2. **Write or modify code** in the `src/` directory

3. **Add tests** for new functionality in `tests/`

4. **Run code quality checks** (see below)

5. **Commit with conventional commits**:
   ```bash
   git add .
   git commit -m "feat: add new pricing feature"
   ```

### Code Quality Checks

Before submitting a pull request, ensure all checks pass:

**Linting** (style and import checks):
```bash
uv run ruff check src/
```

**Type checking** (strict mode):
```bash
uv run mypy src/ --strict
```

**Security scanning**:
```bash
uv run bandit -r src/
```

**Tests**:
```bash
uv run pytest tests/ -v
```

**All checks together**:
```bash
uv run ruff check src/ && \
uv run mypy src/ --strict && \
uv run bandit -r src/ && \
uv run pytest tests/ -v
```

### Commit Message Conventions

We use [Conventional Commits](https://www.conventionalcommits.org/). Examples:

- `feat: add new tool for cost estimation` — New feature
- `fix: correct pricing calculation bug` — Bug fix
- `docs: update deployment guide` — Documentation
- `test: add tests for retry logic` — Tests only
- `refactor: simplify API response handling` — Code refactoring (no behavior change)
- `chore: update dependencies` — Dependencies, build scripts

### Branch Naming

Use descriptive branch names matching your work:
- `feature/add-comparison-tool` — New feature
- `fix/pricing-precision` — Bug fix
- `docs/architecture` — Documentation
- `chore/update-dependencies` — Maintenance

## Pull Request Process

1. **Push your branch**:
   ```bash
   git push origin feature/my-feature
   ```

2. **Open a pull request** on GitHub with:
   - Clear title (use conventional commit format)
   - Description of what changed and why
   - Link to related issue (if applicable)
   - Screenshots or examples (if UI/output changes)

3. **Ensure all checks pass**:
   - ✅ All tests pass
   - ✅ Linting passes
   - ✅ Type checking passes
   - ✅ Security scan passes
   - ✅ CI workflow succeeds

4. **Respond to review feedback**:
   - Address comments politely
   - Request re-review when ready
   - Commit new changes (don't squash during review)

5. **Merge**:
   - Maintainers will squash and merge your branch
   - Your contribution is live!

## Understanding the Codebase

### Project Structure

```
src/
├── server.py              # MCP server implementation
├── client.py              # HTTP client wrapper for OTC API
├── models.py              # Pydantic data models
├── tools/                 # Tool implementations (7 tools)
│   ├── listing.py
│   ├── discovery.py
│   ├── pricing.py
│   └── ...
├── normalize.py           # Price parsing and normalization
└── observability/         # Logging, metrics, health
    ├── logging.py
    ├── metrics.py
    └── health.py

tests/
├── test_server.py         # Server and tool tests
├── test_client.py         # Client and API tests
└── test_normalize.py      # Data normalization tests

deploy/
├── kubernetes/            # K8s manifests and Kustomize
├── argocd/               # ArgoCD application
└── docker/               # Docker build config
```

### Key Files

- **src/server.py** — Registers MCP tools and handles protocol
- **src/client.py** — Wraps OTC API with retry logic and response normalization
- **src/tools/** — Individual tool implementations (discovery, pricing, estimation, etc.)
- **docs/architecture.md** — Deep dive into system design
- **docs/tool-surface.md** — Complete API reference for all tools

### API Integration

The server calls the OTC Price Calculator API at:
```
https://calculator.otc-service.com/en/open-telekom-price-api/
```

Key quirks documented in `src/client.py`:
- Multi-service queries require fan-out (one request per service)
- Prices are strings like `"0.051175 EUR"` (must parse with `normalize.py`)
- Result format varies by query (dict vs list)

## Testing

### Running Tests

```bash
# All tests
uv run pytest tests/ -v

# Specific test file
uv run pytest tests/test_server.py -v

# Specific test
uv run pytest tests/test_server.py::test_list_services -v

# With coverage
uv run pytest tests/ --cov=src/
```

### Writing Tests

Tests use pytest and should:
- Test public API contracts
- Mock external API calls (use `responses` or `unittest.mock`)
- Cover happy path and error cases
- Use descriptive names: `test_list_services_returns_service_list()`

Example:
```python
def test_query_pricing_returns_prices(mock_api):
    """Query pricing should return list of price items."""
    result = query_pricing(service="ecs", region="eu-de")

    assert isinstance(result, list)
    assert len(result) > 0
    assert all(isinstance(item, dict) for item in result)
```

## Adding a New Tool

To add a new MCP tool:

1. **Create implementation** in `src/tools/my_tool.py`:
   ```python
   async def my_new_tool(param1: str, param2: int) -> dict:
       """Tool description for Claude."""
       # Implementation here
       return {"result": "..."}
   ```

2. **Register in server** (`src/server.py`):
   ```python
   server.add_tool(
       "my_new_tool",
       "Description shown to Claude",
       my_new_tool,
       {
           "type": "object",
           "properties": {
               "param1": {"type": "string"},
               "param2": {"type": "integer"},
           },
           "required": ["param1"],
       }
   )
   ```

3. **Add tests** (`tests/test_server.py`):
   ```python
   def test_my_new_tool():
       result = my_new_tool("test", 42)
       assert result["result"] == "expected_value"
   ```

4. **Document** in `docs/tool-surface.md`

5. **Commit** with conventional commit

## Code Style

- **Python**: Follow PEP 8, enforced by ruff
- **Type hints**: Use strict type hints (mypy --strict)
- **Docstrings**: Add docstrings to public functions
- **Comments**: Only for "why", not "what" (code should be self-explanatory)
- **Logging**: Use structured logging (JSON format)

Example:
```python
async def find_compute_flavor(cpu: int, memory_gb: int) -> list[dict]:
    """Find ECS instances matching CPU and memory specs.

    Args:
        cpu: Number of CPU cores (e.g., 2, 4, 8)
        memory_gb: Memory in GB (e.g., 4, 8, 16)

    Returns:
        List of matching flavor objects with price data

    Raises:
        ValueError: If parameters are invalid
        APIError: If OTC API is unreachable
    """
    if cpu < 1 or memory_gb < 1:
        raise ValueError("CPU and memory must be positive")

    # ... implementation
```

## Observability

The server includes structured logging and Prometheus metrics. When adding features:

1. **Log important events**:
   ```python
   from src.observability.logging import logger

   logger.info("event", event="tool_invocation_start", tool="my_tool")
   ```

2. **Track metrics** if appropriate:
   ```python
   from src.observability.metrics import requests_total

   requests_total.labels(tool="my_tool", status="success").inc()
   ```

3. **Document new logs/metrics** in `docs/deployment.md`

## Debugging

### Enable Debug Logging

```bash
LOG_LEVEL=DEBUG uv run python src/server.py
```

This outputs:
- All API requests/responses
- Tool invocations
- Performance metrics

### Common Issues

**Tests fail after setup**:
```bash
# Clear cache and reinstall
rm -rf .venv
uv sync --refresh
uv run pytest tests/ -v
```

**Type checking fails**:
```bash
# Update type stubs
uv run mypy --install-types

# Run with more verbose output
uv run mypy src/ --strict --show-error-codes
```

**Import errors**:
```bash
# Ensure you're using the right Python version
python --version  # Should be 3.12+

# Reinstall in current venv
uv sync --reinstall
```

## Code of Conduct

Please note that this project adheres to the [Contributor Covenant Code of Conduct](CODE_OF_CONDUCT.md). By participating, you are expected to uphold this code. Please report unacceptable behavior via [GitHub Security Advisory](https://github.com/seaser0/otc-pricing-mcp/security/advisories/new).

## Getting Help

- **Questions about contributing?** Open a [GitHub Discussion](https://github.com/seaser0/otc-pricing-mcp/discussions)
- **Found a bug?** [Open an issue](https://github.com/seaser0/otc-pricing-mcp/issues) with:
  - What you were trying to do
  - What happened
  - What you expected
  - Your Python version and OS
  - Full error message/stack trace
- **Security issue?** [Create a private GitHub Security Advisory](https://github.com/seaser0/otc-pricing-mcp/security/advisories/new) (do not open a public issue)
- **Want to discuss a large feature?** Start a [GitHub Discussion](https://github.com/seaser0/otc-pricing-mcp/discussions/new) first

## Additional Resources

- [MCP Protocol Specification](https://modelcontextprotocol.io/introduction)
- [OTC Price Calculator API](https://calculator.otc-service.com/)
- [Python 3.12 Documentation](https://docs.python.org/3.12/)
- [pytest Documentation](https://docs.pytest.org/)
- [Conventional Commits](https://www.conventionalcommits.org/)

## Recognition

Contributors will be recognized in:
- GitHub contributor graph
- Release notes for significant contributions
- Project documentation

Thank you for helping make OTC Pricing MCP better! 🎉
