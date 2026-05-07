# OTC Pricing MCP - Kubernetes Deployment Guide

Deploy the OTC Pricing MCP server to Kubernetes using ArgoCD and Kustomize for GitOps-based continuous deployment.

## Prerequisites

Your k3s cluster must have the following components installed:

- **ArgoCD** (namespace: `argocd`) — GitOps deployment controller
- **cert-manager** with `letsencrypt-prod` ClusterIssuer — TLS certificate management
- **Prometheus Operator** — Metrics scraping via ServiceMonitor CRD
- **nginx Ingress controller** — HTTP/HTTPS traffic routing

Verify prerequisites:

```bash
# Check ArgoCD
kubectl get ns argocd

# Check cert-manager
kubectl get crd clusterisuers.cert-manager.io

# Check Prometheus Operator
kubectl get crd servicemonitors.monitoring.coreos.com

# Check Ingress controller
kubectl get ingressclasses | grep nginx
```

## Architecture Overview

```
GitHub Repository
    ↓ (git push)
ArgoCD watches main branch (deploy/kubernetes/)
    ↓ (detects change)
Kustomize renders manifests
    ↓ (kubectl apply)
Kubernetes cluster
    ├── Namespace: mcp-otc-pricing
    ├── Deployment: 2 replicas with rolling updates
    ├── Service: ClusterIP on port 8080
    ├── Ingress: TLS via cert-manager
    ├── ServiceMonitor: Prometheus metrics scraping
    ├── PodDisruptionBudget: HA (minAvailable=1)
    └── NetworkPolicy: Egress to OTC API only
```

## Deploying to Kubernetes

### Step 1: Apply ArgoCD Application

Apply the ArgoCD Application manifest to your cluster:

```bash
kubectl apply -f deploy/argocd/application.yaml
```

This creates an ArgoCD Application that:
- Points to the `deploy/kubernetes/` directory in this git repo
- Uses Kustomize to render manifests
- Auto-syncs on every git push to `main`
- Prunes resources not in git
- Self-heals manual kubectl changes

### Step 2: Verify ArgoCD Application Status

```bash
# Check if application was created
kubectl get applications -n argocd otc-pricing-mcp

# Get detailed status
argocd app get otc-pricing-mcp

# Expected output:
# Health Status: Healthy
# Sync Status: Synced
# (it may take 30-60s for sync to complete)
```

### Step 3: Wait for Full Synchronization

```bash
# Wait for application to be synced and healthy
argocd app wait otc-pricing-mcp --sync --health --timeout 300

# Or watch in real-time
argocd app get otc-pricing-mcp --watch
```

### Step 4: Verify Pods Are Running

```bash
# Check pods in the namespace
kubectl get pods -n mcp-otc-pricing

# Expected output (2 Running pods):
# NAME                               READY   STATUS    RESTARTS   AGE
# otc-pricing-mcp-7c9d8f5b9c-abc12   1/1     Running   0          30s
# otc-pricing-mcp-7c9d8f5b9c-def34   1/1     Running   0          20s
```

### Step 5: Check Service and Ingress

```bash
# Verify service
kubectl get svc -n mcp-otc-pricing otc-pricing-mcp

# Expected: ClusterIP on port 8080

# Verify ingress
kubectl get ingress -n mcp-otc-pricing otc-pricing-mcp

# Expected: Ingress with hostname mcp-otc-pricing.nevit.ch

# Check TLS certificate status
kubectl get certificate -n mcp-otc-pricing otc-pricing-mcp-tls

# Expected: Ready=True (cert-manager may take 1-2 minutes)
```

## Testing the Deployment

### Test Health Endpoints

Health endpoints are available at `https://mcp-otc-pricing.nevit.ch/`:

```bash
# Liveness check (always returns 200 if pod is running)
curl -I https://mcp-otc-pricing.nevit.ch/healthz
# Expected: HTTP/2 200 OK

# Readiness check (checks OTC API connectivity, cached 30s)
curl https://mcp-otc-pricing.nevit.ch/readyz | jq .
# Expected: {"status": "ready", "upstream": "ok", "api_response_time": 0.042}

# If API is unreachable:
curl -I https://mcp-otc-pricing.nevit.ch/readyz
# Expected: HTTP/2 503 Service Unavailable
```

### Test Metrics Endpoint

```bash
# Port-forward to metrics (if you want to test from local machine)
kubectl port-forward -n mcp-otc-pricing svc/otc-pricing-mcp 8080:8080 &

# Fetch Prometheus metrics
curl http://localhost:8080/metrics | grep otc_pricing_mcp

# Expected: Prometheus format metrics
# otc_pricing_mcp_requests_total{tool="...",status="..."} 0.0
# otc_pricing_mcp_request_duration_seconds{tool="..."} ...
# otc_pricing_mcp_upstream_requests_total{service="...",status="..."} 0.0
```

### Test Pod Logs

```bash
# View structured JSON logs from both pods
kubectl logs -n mcp-otc-pricing -l app=otc-pricing-mcp --tail=50

# Parse JSON logs for readability
kubectl logs -n mcp-otc-pricing -l app=otc-pricing-mcp --tail=50 | jq .

# Expected JSON entries:
# {"timestamp": "2026-05-06T18:00:00Z", "event": "metrics_server_started", ...}
# {"timestamp": "2026-05-06T18:00:01Z", "event": "mcp_server_ready", ...}
```

### Test High Availability

Verify that killing one pod doesn't break the service:

```bash
# Kill one pod (service should still respond from the other)
kubectl delete pod -n mcp-otc-pricing -l app=otc-pricing-mcp --field-selector status.phase=Running -n mcp-otc-pricing | head -1

# Immediately test that service still responds
curl -I https://mcp-otc-pricing.nevit.ch/healthz

# Expected: HTTP/2 200 (even though we just killed a pod)

# Watch new pod recover
kubectl get pods -n mcp-otc-pricing --watch

# Expected: 1 pod shows Terminating, 1 pod recovering, eventually back to 2 Running
```

### Test PodDisruptionBudget

```bash
# Check PDB prevents disruptions
kubectl get pdb -n mcp-otc-pricing otc-pricing-mcp

# Try to drain all pods in the namespace (should fail to maintain minAvailable=1)
kubectl drain <node-name> --ignore-daemonsets --dry-run=client

# Expected: error about PodDisruptionBudget blocking drain if it would violate minAvailable
```

### Test NetworkPolicy

```bash
# Test that pod CAN reach OTC API (allowed egress)
kubectl run -it --rm debug -n mcp-otc-pricing \
  --image=curlimages/curl --restart=Never -- \
  curl -I https://calculator.otc-service.com/en/open-telekom-price-api/

# Expected: HTTP/1.1 200 or similar (successful)

# Test that pod CANNOT reach arbitrary external hosts (blocked egress)
kubectl run -it --rm debug -n mcp-otc-pricing \
  --image=curlimages/curl --restart=Never -- \
  curl -I https://google.com

# Expected: timeout or "no route to host" (blocked by NetworkPolicy)
```

## Updating Deployments

### Update Application Version

To deploy a new version of the application:

1. **Create a git tag** with the new version:
   ```bash
   git tag v0.2.0
   git push origin v0.2.0
   ```

2. **Wait for GitHub Actions** to build and push the image to GHCR:
   ```
   Image: ghcr.io/seaser0/otc-pricing-mcp:v0.2.0
   ```

3. **Update the image tag** in `deploy/kubernetes/kustomization.yaml`:
   ```yaml
   images:
   - name: ghcr.io/seaser0/otc-pricing-mcp
     newTag: v0.2.0  # Update this
   ```

4. **Commit and push**:
   ```bash
   git add deploy/kubernetes/kustomization.yaml
   git commit -m "Deploy v0.2.0"
   git push origin main
   ```

5. **ArgoCD automatically syncs** (usually within 3 minutes)

6. **Verify deployment**:
   ```bash
   # Watch pods rolling out
   kubectl rollout status deployment/otc-pricing-mcp -n mcp-otc-pricing

   # Verify new version is running
   kubectl get pods -n mcp-otc-pricing -o jsonpath='{.items[*].spec.containers[*].image}'
   # Should show v0.2.0
   ```

### Update Configuration

To change LOG_LEVEL or other environment variables:

Edit `deploy/kubernetes/kustomization.yaml`:

```yaml
configMapGenerator:
- name: otc-pricing-mcp-config
  literals:
  - LOG_LEVEL=DEBUG  # Change from INFO to DEBUG
  - METRICS_PORT=8080
```

Commit and push — ArgoCD will automatically:
1. Update the ConfigMap (creates new ConfigMap with hashed suffix)
2. Restart pods (to pick up new config)

```bash
# Watch pods restart
kubectl get pods -n mcp-otc-pricing --watch
```

## Troubleshooting

### Pods Not Starting

```bash
# Check pod events and logs
kubectl describe pod -n mcp-otc-pricing -l app=otc-pricing-mcp

# Get detailed logs
kubectl logs -n mcp-otc-pricing -l app=otc-pricing-mcp --tail=100 -f
```

**Common issues:**
- ImagePullBackOff: Image doesn't exist or pull secret missing
- CrashLoopBackOff: Application error (check logs)
- Pending: Resource requests not available (check node capacity)

### Ingress Not Working

```bash
# Check if ingress resource exists
kubectl get ingress -n mcp-otc-pricing

# Check ingress details
kubectl describe ingress -n mcp-otc-pricing otc-pricing-mcp

# Check TLS certificate
kubectl get certificate -n mcp-otc-pricing otc-pricing-mcp-tls
kubectl describe certificate -n mcp-otc-pricing otc-pricing-mcp-tls

# Check cert-manager logs
kubectl logs -n cert-manager -l app=cert-manager --tail=50
```

**Common issues:**
- ClusterIssuer not found: Verify `letsencrypt-prod` exists
- Certificate pending: cert-manager may be issuing cert (takes 1-2 minutes)
- Ingress shows no address: Check nginx ingress controller is running

### Metrics Not Being Scraped

```bash
# Check ServiceMonitor was created
kubectl get servicemonitor -n mcp-otc-pricing

# Verify ServiceMonitor selector matches pods
kubectl get pods -n mcp-otc-pricing -L app

# Check Prometheus targets
# (Requires access to Prometheus UI or kubectl port-forward)
kubectl port-forward -n monitoring svc/prometheus-operated 9090:9090
# Then visit http://localhost:9090/targets
```

**Common issues:**
- ServiceMonitor label selector doesn't match pods
- Prometheus doesn't have permission to scrape namespace
- Prometheus Operator not installed

### Health Checks Failing

```bash
# Check readiness (API connectivity)
kubectl get endpoints -n mcp-otc-pricing otc-pricing-mcp

# Should show pod IPs

# Test readiness manually
kubectl port-forward -n mcp-otc-pricing svc/otc-pricing-mcp 8080:8080
curl http://localhost:8080/readyz
```

**Common issues:**
- OTC API unreachable (check egress NetworkPolicy)
- Pod thinks it's not ready (check readiness probe timeout)

## Rollback Procedures

### Option 1: ArgoCD Rollback (Recommended)

```bash
# View application history
argocd app history otc-pricing-mcp

# Rollback to previous revision
argocd app rollback otc-pricing-mcp <REVISION>

# Verify rollback
argocd app get otc-pricing-mcp
```

### Option 2: Git Revert

```bash
# Find the commit that caused the problem
git log --oneline -n 10

# Revert the commit
git revert <COMMIT_SHA>
git push origin main

# ArgoCD automatically syncs back to the previous state
```

### Option 3: Manual kubectl Rollback

```bash
# Rollback deployment to previous image
kubectl rollout undo deployment/otc-pricing-mcp -n mcp-otc-pricing

# Check rollout status
kubectl rollout status deployment/otc-pricing-mcp -n mcp-otc-pricing

# View rollout history
kubectl rollout history deployment/otc-pricing-mcp -n mcp-otc-pricing
```

**Note:** ArgoCD will eventually notice the manual change and correct it (self-heal), so git revert is safer for long-term consistency.

## Epic Acceptance Criteria Checklist

After deployment, verify all acceptance criteria are met:

```bash
# ✅ ArgoCD shows Synced + Healthy
argocd app get otc-pricing-mcp
# Health Status: Healthy
# Sync Status: Synced

# ✅ HTTPS endpoint returns 200
curl -I https://mcp-otc-pricing.nevit.ch/healthz
# HTTP/2 200 OK

# ✅ Pod logs show structured JSON
kubectl logs -n mcp-otc-pricing -l app=otc-pricing-mcp --tail=5 | jq .
# {"timestamp": "...", "event": "...", "request_id": "..."}

# ✅ HA: Service survives pod termination
kubectl delete pod -n mcp-otc-pricing $(kubectl get pods -n mcp-otc-pricing -o name | head -1)
curl -I https://mcp-otc-pricing.nevit.ch/healthz
# HTTP/2 200 OK (from surviving pod)

# ✅ NetworkPolicy blocks unauthorized egress
kubectl run -it --rm test -n mcp-otc-pricing --image=curlimages/curl -- curl -I https://google.com
# Timeout or connection refused (blocked)
```

## Security Best Practices

### Network Access

- **Ingress**: Only from nginx ingress controller (port 8080)
- **Egress**: Only to DNS (port 53) and HTTPS (port 443)
- **OTC API**: All HTTPS traffic to `calculator.otc-service.com` is allowed

Adjust NetworkPolicy in `deploy/kubernetes/network-policy.yaml` if:
- Your ingress controller is in a different namespace
- You need to restrict to specific OTC API IP ranges

### Image Updates

Always use **specific version tags** in production (not `latest`):

```yaml
images:
- name: ghcr.io/seaser0/otc-pricing-mcp
  newTag: v0.2.0  # Specific version (not "latest")
```

### Resource Limits

Current limits are conservative for development:
- CPU: 100m request, 500m limit
- Memory: 128Mi request, 512Mi limit

Monitor metrics and adjust if needed:

```bash
# Check current usage
kubectl top pods -n mcp-otc-pricing

# Edit deployment limits
kubectl edit deployment -n mcp-otc-pricing otc-pricing-mcp
```

## Monitoring & Observability

### View Metrics

Prometheus metrics are available at `/metrics` endpoint:

```bash
# Via ingress
curl https://mcp-otc-pricing.nevit.ch/metrics | head -20

# Via port-forward
kubectl port-forward -n mcp-otc-pricing svc/otc-pricing-mcp 8080:8080
curl http://localhost:8080/metrics | grep otc_pricing_mcp
```

### View Logs

Structured JSON logs are available via kubectl:

```bash
# All pods
kubectl logs -n mcp-otc-pricing -l app=otc-pricing-mcp -f

# Specific pod
kubectl logs -n mcp-otc-pricing <POD_NAME> -f

# Parse JSON
kubectl logs -n mcp-otc-pricing -l app=otc-pricing-mcp | jq 'select(.event == "tool_invocation_start")'
```

### Integration with Prometheus

Prometheus automatically scrapes metrics via ServiceMonitor:

```yaml
# Query request rate (requests per second)
rate(otc_pricing_mcp_requests_total[5m])

# Query p95 latency
histogram_quantile(0.95, rate(otc_pricing_mcp_request_duration_seconds_bucket[5m]))

# Query upstream error rate
rate(otc_pricing_mcp_upstream_requests_total{status="error"}[5m])
```

## Common Operations

### Scale Replicas

Temporarily increase replicas (note: ArgoCD will reset after syncing):

```bash
kubectl scale deployment otc-pricing-mcp -n mcp-otc-pricing --replicas=3
```

For permanent changes, edit `deploy/kubernetes/kustomization.yaml` or deployment.yaml:

```yaml
spec:
  replicas: 3
```

### Execute Commands in Pod

Distroless images have no shell, so use a debug pod:

```bash
kubectl run -it --rm debug -n mcp-otc-pricing --image=curlimages/curl -- /bin/sh

# Or just curl
kubectl run -it --rm debug -n mcp-otc-pricing --image=curlimages/curl -- \
  curl http://otc-pricing-mcp:8080/healthz
```

### Port-Forward for Testing

```bash
# Metrics endpoint
kubectl port-forward -n mcp-otc-pricing svc/otc-pricing-mcp 8080:8080

# Now accessible at http://localhost:8080
```

## Additional Resources

- [Kubernetes Deployment best practices](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/)
- [NetworkPolicy reference](https://kubernetes.io/docs/concepts/services-networking/network-policies/)
- [ArgoCD documentation](https://argo-cd.readthedocs.io/)
- [Kustomize reference](https://kustomize.io/)
- [cert-manager documentation](https://cert-manager.io/)
