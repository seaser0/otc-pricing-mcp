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

# Build a clean production-only venv (no dev extras) so the SBOM reflects
# what is actually shipped in the Docker image.
uv sync --frozen --no-dev

# Run cyclonedx-py via uvx so it is isolated from the production venv.
# cyclonedx-bom v4+ uses 'cyclonedx-py environment <python>' instead of
# the old 'cyclonedx-bom generate ... pyproject.toml' interface.
uvx --from cyclonedx-bom cyclonedx-py environment \
    --of JSON \
    --sv 1.5 \
    -o sbom.json \
    .venv/bin/python

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
