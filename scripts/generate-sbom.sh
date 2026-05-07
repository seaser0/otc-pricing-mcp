#!/usr/bin/env bash
# Generate CycloneDX Software Bill of Materials (SBOM) from dependencies
# Usage: bash scripts/generate-sbom.sh
# Output: sbom.json

set -euo pipefail

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_ROOT"

echo "Generating CycloneDX SBOM from locked dependencies..."

# Generate SBOM from pyproject.toml and uv.lock
# Format: CycloneDX JSON (machine-readable)
# Includes all runtime dependencies (no dev dependencies)
uv run --dev cyclonedx-bom generate \
    --format json \
    --output sbom.json \
    --specVersion 1.5 \
    pyproject.toml

# Verify the SBOM was created
if [ -f sbom.json ]; then
    COMPONENT_COUNT=$(jq '.components | length' sbom.json)
    echo "✓ SBOM generated successfully: sbom.json"
    echo "  Components included: $COMPONENT_COUNT"
    exit 0
else
    echo "✗ SBOM generation failed" >&2
    exit 1
fi
