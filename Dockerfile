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

# Stage 2: Runtime with distroless
# distroless provides minimal attack surface: no shell, no package manager
FROM gcr.io/distroless/python3-debian12:nonroot

# Copy virtual environment and source from builder
# --chown ensures correct permissions (nonroot user is UID 65532)
COPY --from=builder --chown=nonroot:nonroot /app/.venv /app/.venv
COPY --from=builder --chown=nonroot:nonroot /app/src /app/src

# Set working directory and Python path
WORKDIR /app
ENV PYTHONPATH=/app/src
ENV PATH="/app/.venv/bin:${PATH}"
# Disable Python bytecode generation for slightly smaller image
ENV PYTHONDONTWRITEBYTECODE=1
# Ensure Python output is sent straight to logs without buffering
ENV PYTHONUNBUFFERED=1

# Run as non-root user (UID 65532, built into distroless)
USER nonroot

# Expose metrics/health port
# Port 8080: HTTP server for /healthz, /readyz, /metrics endpoints
EXPOSE 8080

# MCP server via STDIO transport + HTTP metrics server
# STDIO: stdin/stdout for MCP protocol
# HTTP: port 8080 for health checks and Prometheus metrics
CMD ["/app/.venv/bin/python", "-m", "otc_pricing_mcp"]
