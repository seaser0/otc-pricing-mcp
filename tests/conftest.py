"""Pytest configuration and fixtures for all tests."""

from __future__ import annotations

import os
from pathlib import Path

import pytest


def pytest_configure(config):
    """Configure pytest markers."""
    config.addinivalue_line("markers", "live: marks tests as live (require OTC_LIVE=1 to run)")
    config.addinivalue_line("markers", "integration: marks tests as integration tests")
    config.addinivalue_line("markers", "conformance: marks tests as MCP conformance tests")

    # Ensure cassettes directory exists
    cassettes_dir = Path(__file__).parent / "integration" / "cassettes"
    cassettes_dir.mkdir(parents=True, exist_ok=True)


def pytest_collection_modifyitems(config, items):
    """Skip live tests unless OTC_LIVE is set."""
    if os.getenv("OTC_LIVE") != "1":
        skip_live = pytest.mark.skip(reason="OTC_LIVE not set; use -m live to run")
        for item in items:
            if "live" in item.keywords:
                item.add_marker(skip_live)


@pytest.fixture
def vcr_config():
    """Configure pytest-vcr for recording API interactions."""
    return {
        "filter_headers": [],  # No sensitive headers to filter
        "decode_compressed_response": True,
        "record_mode": "once",  # Record if cassette missing, replay if exists
    }
