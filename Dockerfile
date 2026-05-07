# Multi-stage Dockerfile for OTC Pricing MCP server
# Stage 1: Build dependencies
FROM python:3.12-slim AS builder

# Install uv for fast dependency resolution
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Copy dependency definitions
COPY pyproject.toml uv.lock README.md ./

# Install dependencies to virtual environment
# --frozen prevents uv from modifying the lock file
# --no-dev excludes development dependencies (bandit, mypy, pytest, etc.)
RUN uv sync --frozen --no-dev

# Copy source code
COPY src/ ./src/

# Stage 2: Runtime — python:3.12-slim matches the builder's Python version.
# distroless/python3-debian12 ships Python 3.11, which is incompatible with
# a venv and native extensions (pydantic-core, cryptography) built for 3.12.
FROM python:3.12-slim

# Create a non-root user with the same UID (65532) used by distroless nonroot,
# so Kubernetes securityContext runAsUser values stay consistent.
RUN useradd --no-create-home --no-log-init --uid 65532 --gid 0 nonroot

# Copy virtual environment and source from builder
COPY --from=builder --chown=65532:0 /app/.venv /app/.venv
COPY --from=builder --chown=65532:0 /app/src /app/src

# Set working directory and Python path
WORKDIR /app
ENV PYTHONPATH=/app/src
ENV PATH="/app/.venv/bin:${PATH}"
# Disable Python bytecode generation for slightly smaller image
ENV PYTHONDONTWRITEBYTECODE=1
# Ensure Python output is sent straight to logs without buffering
ENV PYTHONUNBUFFERED=1

# Run as non-root user (UID 65532)
USER nonroot

# Expose metrics/health port
# Port 8080: HTTP server for /healthz, /readyz, /metrics endpoints
EXPOSE 8080

# MCP server via STDIO transport + HTTP metrics server
# STDIO: stdin/stdout for MCP protocol
# HTTP: port 8080 for health checks and Prometheus metrics
CMD ["/app/.venv/bin/python", "-m", "otc_pricing_mcp"]
