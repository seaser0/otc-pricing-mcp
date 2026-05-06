# CI/CD Pipeline

This document describes the automated CI/CD pipeline for the OTC Pricing MCP server.

## Overview

The project uses GitHub Actions to automate:
- **Code quality checks** (linting, type checking, formatting)
- **Testing** (unit tests, conformance tests)
- **Security scanning** (static analysis, dependency audit, container scan)
- **Release automation** (build, publish, release notes)

## Workflows

### 1. CI Workflow (`.github/workflows/ci.yml`)

Runs on every push to `main` and pull requests.

**Jobs:**
- **Lint** (`ruff`): Code style and format checks
- **Type Check** (`mypy --strict`): Type annotations and safety
- **Unit Tests** (`pytest`): Core functionality tests
- **Conformance Tests**: MCP protocol compliance
- **Security - Bandit**: Static analysis for security issues
- **Security - pip-audit**: Dependency vulnerability scanning
- **Security - Trivy**: Container image vulnerability scanning

**Requirements to merge:**
- All jobs must pass
- No merge without green CI status

**Example CI output:**
```
✓ Lint (ruff)
✓ Type Check (mypy --strict)
✓ Unit Tests
✓ Conformance Tests
✓ Security - Bandit
✓ Security - pip-audit
✓ Security - Trivy
✓ Status Check
```

### 2. Release Workflow (`.github/workflows/release.yml`)

Triggered when a git tag matching `v*.*.*` is pushed.

**Jobs:**
1. **Build Image**: Builds and pushes container to GHCR
   - Builds distroless Docker image
   - Tags with semantic version (e.g., `v0.1.0`)
   - Tags with `latest`
   - Pushes to `ghcr.io/seaser0/otc-pricing-mcp`

2. **Generate SBOM**: Creates Software Bill of Materials
   - CycloneDX format (machine-readable)
   - Lists all dependencies
   - Enables downstream vulnerability tracking

3. **Create Release**: Creates GitHub release
   - Auto-generates changelog from commits
   - Attaches SBOM as artifact
   - Links to container image

4. **Verify Image**: Ensures image is publicly accessible
   - Tests pulling without authentication
   - Verifies image execution

### 3. Security Workflow (`.github/workflows/security.yml`)

Runs on:
- Every push to `main`
- Every pull request
- **Nightly at 2 AM UTC** (catches new CVEs)

**Jobs:**
- **Dependency Audit**: `pip-audit` checks for CVEs
- **Static Analysis**: `bandit` checks for security issues
- **Container Scan**: `trivy` scans for vulnerabilities
- **Report Vulnerabilities**: Opens issue if vulnerabilities found (nightly only)

**Failure handling:**
- PR/push triggers: Fails CI to block merge
- Nightly triggers: Creates/updates issue automatically

## Release Process

### Manual Release (Recommended for v1)

1. **Prepare release locally**
   ```bash
   # Run full CI locally before pushing
   uv run ruff check src/ tests/
   uv run ruff format --check src/ tests/
   uv run mypy src/ --strict
   uv run pytest tests/unit/ -v
   uv run pytest tests/integration/test_mcp_conformance.py -v
   uv run bandit -r src/ -ll
   ```

2. **Create git tag**
   ```bash
   # Use semantic versioning (MAJOR.MINOR.PATCH)
   git tag v0.1.0
   git push origin v0.1.0
   ```

3. **Monitor release**
   - Go to Actions tab on GitHub
   - Watch `Release` workflow run
   - Verify image pushed to GHCR
   - Check GitHub Releases for new entry

### Semantic Versioning

Follow [semver.org](https://semver.org/):

- **MAJOR** (`v1.0.0`): Incompatible API changes
- **MINOR** (`v0.1.0`): New features (backward compatible)
- **PATCH** (`v0.0.1`): Bug fixes

Examples:
- First release: `v0.1.0`
- Patch release: `v0.1.1`
- Minor release: `v0.2.0`
- Major release: `v1.0.0`

## Testing Before Release

### Run CI Locally

```bash
# Install dependencies
uv sync

# Lint and format
uv run ruff check src/ tests/
uv run ruff format --check src/ tests/

# Type checking
uv run mypy src/ --strict

# Unit tests
uv run pytest tests/unit/ -v --cov

# Conformance tests
uv run pytest tests/integration/test_mcp_conformance.py -v

# Security checks
uv run bandit -r src/ -ll
source .venv/bin/activate && pip-audit --skip-editable
```

### Build Image Locally

```bash
# Build image
docker build -t otc-pricing-mcp:test .

# Test image runs
docker run --rm otc-pricing-mcp:test

# Test import
docker run --rm otc-pricing-mcp:test python -c "import otc_pricing_mcp; print('✓ Import works')"
```

## Accessing Released Images

### Pull from GHCR

```bash
# Pull latest version
docker pull ghcr.io/seaser0/otc-pricing-mcp:latest

# Pull specific version
docker pull ghcr.io/seaser0/otc-pricing-mcp:v0.1.0

# Run the image
docker run --rm ghcr.io/seaser0/otc-pricing-mcp:v0.1.0
```

### No authentication required

The container image is publicly accessible. No login needed for `docker pull`.

## CI Failure Troubleshooting

### Lint Failures

```bash
# Auto-fix formatting
uv run ruff format src/ tests/

# Check remaining issues
uv run ruff check src/ tests/
```

### Type Check Failures

```bash
# Run mypy locally
uv run mypy src/ --strict

# Common fixes:
# - Add type annotations to function parameters
# - Add return type annotations
# - Check for Any types (not allowed with --strict)
```

### Test Failures

```bash
# Run failed test locally
uv run pytest tests/unit/test_file.py::TestClass::test_method -v

# Check coverage
uv run pytest tests/unit/ --cov=src/otc_pricing_mcp
```

### Security Scan Failures

#### Bandit
```bash
uv run bandit -r src/ -v

# Ignore false positives with # nosec comment
```

#### pip-audit
```bash
source .venv/bin/activate && pip-audit --skip-editable

# Check if CVE is in dev-only deps (usually safe)
```

#### Trivy
```bash
docker build -t test:scan .
trivy image --severity HIGH,CRITICAL test:scan
```

## Environment Variables

The workflows use standard GitHub Actions environment variables:

- `GITHUB_TOKEN`: Automatically provided for authentication
- `GITHUB_REF`: Commit reference (tag for releases)
- `GITHUB_REPOSITORY`: Repository name (`seaser0/otc-pricing-mcp`)
- `GITHUB_ACTOR`: User who triggered the workflow

No additional setup required.

## Permissions

### CI Workflow
- Read-only access to repository
- Can upload artifacts
- Can upload coverage reports

### Release Workflow
- **packages:write**: Push to container registry
- **contents:write**: Create GitHub releases

### Security Workflow
- **security-events:write**: Upload SARIF reports
- **issues:write**: Create vulnerability issues

## Troubleshooting

### Workflow not triggering

**Push to main doesn't trigger CI:**
- Ensure branch protection rule requires status checks
- Check workflow syntax with `act --list` (local testing)

**Release workflow doesn't trigger:**
- Verify tag matches `v*.*.*` pattern
- Check if workflow is enabled in Actions tab

### Image push fails

**Authentication error:**
- GITHUB_TOKEN is scoped to current repository only
- Verify repository has Packages enabled in settings

**Image too large:**
- Multi-stage Dockerfile should keep final image < 200MB
- Check `docker images` size

### SBOM generation fails

**Command not found:**
- Ensure `cyclonedx-bom` is installed: `uv sync`
- Check scripts/generate-sbom.sh is executable: `chmod +x scripts/generate-sbom.sh`

## Performance

### Caching
- uv dependency cache reduces install time
- Docker layer caching speeds up image builds
- GitHub Actions maintains cache across runs

### Parallel execution
- Lint, typecheck, tests run in parallel
- Security checks run in parallel
- Speeds up overall CI time to ~5-10 minutes

## Security Notes

- All workflows use `actions/checkout@v4` (latest)
- GITHUB_TOKEN is scoped to current repository
- No secrets required (API is public)
- Container image is publicly readable (by design)

## References

- [GitHub Actions Documentation](https://docs.github.com/en/actions)
- [Semantic Versioning](https://semver.org/)
- [CycloneDX SBOM Standard](https://cyclonedx.org/)
- [OTC Pricing MCP Architecture](./architecture.md)
