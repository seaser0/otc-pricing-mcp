# Security Policy

## Supported Versions

We release security patches for disclosed vulnerabilities. Currently supported:

| Version | Supported          |
| ------- | ------------------ |
| 0.1.x   | ✅ Yes |
| < 0.1   | ❌ No  |

## Reporting a Vulnerability

**Do NOT open a public GitHub issue for security vulnerabilities.**

Instead, please report security issues via:

1. **GitHub Security Advisory (Recommended):** [Create private advisory](https://github.com/seaser0/otc-pricing-mcp/security/advisories/new)
   - Allows private disclosure and coordinated remediation
   - Visible only to maintainers until published
   - Mark subject: `[SECURITY] OTC Pricing MCP`
   - Include reproduction steps and severity assessment

We will:
- Acknowledge receipt within 48 hours
- Provide a fix or workaround within 7 days for critical issues
- Credit the reporter (unless anonymity requested)
- Publish advisory after a fix is released or 90 days pass

## Security Features

### Authentication & Authorization
- **No authentication required**: The upstream OTC Price Calculator API is public and unauthenticated. This MCP server reflects that design.
- **No authorization checks**: API is read-only by nature; anyone with access to the MCP server can query pricing data.
- **No API keys or secrets**: Server does not store, transmit, or require any sensitive credentials.

### Container Security
- **Non-root user**: Container runs as `nonroot` user (UID 65532), preventing privileged operations.
- **Distroless base image**: `gcr.io/distroless/python3-debian12:nonroot` provides minimal attack surface:
  - No shell (`/bin/sh` unavailable)
  - No package manager (`apt`, `pip` unavailable)
  - Only Python 3.12 runtime and glibc
  - ~120MB image size (vs 1GB+ with standard Python image)
- **Read-only root filesystem**: Supported via Kubernetes `securityContext.readOnlyRootFilesystem: true`
  - Only `/tmp` is writable (for logging, metrics buffering)
  - Prevents accidental or malicious file modifications

### Network Security
- **Kubernetes NetworkPolicy**: Restricts egress to:
  - DNS resolution (`UDP 53` to `kube-system`)
  - HTTPS to `calculator.otc-service.com:443` only
  - Blocks all other outbound connections (fail-closed)
- **No exposed ports in container**: STDIO-based MCP communication; no TCP services.
- **TLS enforcement**: All communication to upstream API requires HTTPS; HTTP requests are rejected.

### Dependency Security
- **Dependency auditing**: Automated vulnerability scanning via:
  - `pip-audit` in CI: Fails on CVE ≥ medium severity
  - Nightly scheduled scans detect newly published CVEs
  - Locked dependencies (`uv.lock`) ensure reproducibility
- **No major frameworks**: Minimal dependencies reduce attack surface:
  - Core: `httpx`, `pydantic`, `mcp`, `tenacity`
  - Logging: `structlog`
  - Metrics: `prometheus-client`
  - No ORM, serialization library, or web framework needed

### Code Security
- **Static analysis**: Bandit security linter in CI:
  - Fails on HIGH severity findings
  - Checks for: hardcoded secrets, insecure functions, SQL injection patterns, etc.
  - Excludes tests (they may use test fixtures that trigger low-severity warnings)
- **Type checking**: `mypy --strict` enforces:
  - All parameters must be typed
  - All return values must be typed
  - No implicit `Any` types
  - Reduces logic errors that could lead to security issues

### Software Bill of Materials (SBOM)
- **CycloneDX SBOM**: Generated from locked dependencies (`uv.lock`)
- **Attached to releases**: Every GitHub release includes `sbom.json`
- **Enables tracking**: Downstream users can monitor their supply chain for CVEs
- **Format**: CycloneDX 1.5 (machine-readable, widely supported)

## Known Limitations

### Upstream API
- **No rate limiting**: OTC Price Calculator API does not enforce rate limits.
  - **Mitigation**: Implement rate limiting at your network layer or MCP gateway.
  - **Risk**: Pod could be used to DDoS the upstream service.

### Data in Transit
- **User queries logged**: Structlog JSON logging includes full request/response data.
  - **Mitigation**: Filter sensitive queries at the MCP gateway layer.
  - **Risk**: Logs may contain user prompts (usually not PII, but be cautious).
- **HTTPS only to upstream**: Encryption in transit is standard TLS, no additional integrity checks.

### Container Runtime
- **No SELinux**: Policy assumes standard Kubernetes RBAC.
- **Distroless limitations**: Cannot install additional tools for debugging (no `apt`, no `bash`).
  - **Mitigation**: Use `kubectl debug` for pod inspection with a debugging sidecar.

## Security Scanning Schedule

| Scan | Frequency | Fails on | Location |
|------|-----------|----------|----------|
| Dependency audit (pip-audit) | Every commit, nightly | CVE ≥ medium | `.github/workflows/security.yml` |
| Static analysis (Bandit) | Every commit | HIGH severity | `.github/workflows/security.yml` |
| Container image (Trivy) | Every commit | HIGH, CRITICAL | `.github/workflows/security.yml` |
| Type checking (mypy --strict) | Every commit | Type errors | Quality gate in CI |
| Linting (ruff) | Every commit | Code style | Quality gate in CI |

## Deployment Security Checklist

When deploying to Kubernetes, ensure:

- [ ] Pod runs with `runAsNonRoot: true` and `runAsUser: 65532`
- [ ] Pod uses `readOnlyRootFilesystem: true`
- [ ] Pod has `allowPrivilegeEscalation: false`
- [ ] Pod has `capabilities.drop: ["ALL"]`
- [ ] NetworkPolicy is deployed (see `deploy/kubernetes/network-policy.yaml`)
- [ ] RBAC policy limits CRUD operations (read-only MCP)
- [ ] No sensitive environment variables (API is public)
- [ ] Pod Disruption Budget is set (graceful shutdown on node drain)
- [ ] Resource limits are set (prevent resource exhaustion attacks)

Example secure Pod spec:
```yaml
apiVersion: v1
kind: Pod
metadata:
  name: otc-pricing-mcp
spec:
  containers:
  - name: otc-pricing-mcp
    image: ghcr.io/seaser0/otc-pricing-mcp:v0.1.0
    securityContext:
      allowPrivilegeEscalation: false
      runAsNonRoot: true
      runAsUser: 65532
      readOnlyRootFilesystem: true
      capabilities:
        drop:
          - ALL
    resources:
      requests:
        cpu: 100m
        memory: 128Mi
      limits:
        cpu: 500m
        memory: 512Mi
    volumeMounts:
    - name: tmp
      mountPath: /tmp
  securityContext:
    fsGroup: 65532
  volumes:
  - name: tmp
    emptyDir: {}
  networkPolicy:
    podSelector:
      matchLabels:
        app: otc-pricing-mcp
```

## Security Contact

- **Vulnerability reports**: [GitHub Security Advisory](https://github.com/seaser0/otc-pricing-mcp/security/advisories/new) (preferred)
- **General questions**: [GitHub Discussions](https://github.com/seaser0/otc-pricing-mcp/discussions)
- **Issue tracker**: https://github.com/seaser0/otc-pricing-mcp/issues (for non-security issues only)

## References

- OWASP Top 10: https://owasp.org/www-project-top-ten/
- CWE Top 25: https://cwe.mitre.org/top25/
- NIST Cybersecurity Framework: https://www.nist.gov/cyberframework
- Kubernetes Security Best Practices: https://kubernetes.io/docs/concepts/security/
- Distroless Images: https://github.com/GoogleContainerTools/distroless
- CycloneDX SBOM: https://cyclonedx.org/
