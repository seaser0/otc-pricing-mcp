"""Live API integration tests (marked with @pytest.mark.live).

These tests hit the real OTC Price Calculator API and use VCR cassettes to record
responses for offline replay in CI. Run with: pytest -m live

VCR configuration:
- Records requests/responses to tests/integration/cassettes/
- Strips sensitive data (none in this API, but configured for safety)
- Replays recorded cassettes if they exist
- Falls back to live API if cassette missing
"""

from __future__ import annotations

import pytest

from otc_pricing_mcp.client import OTCPricingClient
from otc_pricing_mcp.normalize import extract_items, parse_price
from otc_pricing_mcp.tools.discovery import get_service_schema, list_regions, list_services
from otc_pricing_mcp.tools.estimation import compare_billing_models, estimate_monthly_cost
from otc_pricing_mcp.tools.pricing import find_compute_flavor, query_pricing


class TestLiveDiscovery:
    """Live API tests for discovery tools."""

    @pytest.mark.live
    @pytest.mark.integration
    def test_list_services_returns_data(self, vcr) -> None:
        """list_services returns non-empty list of services."""
        services = list_services()
        assert isinstance(services, list)
        assert len(services) > 0
        # Should contain at least ecs (common service)
        assert "ecs" in services

    @pytest.mark.live
    @pytest.mark.integration
    def test_list_regions_returns_data(self, vcr) -> None:
        """list_regions returns expected OTC regions."""
        regions = list_regions()
        assert isinstance(regions, list)
        assert len(regions) > 0
        # Should contain at least eu-de (primary region)
        assert "eu-de" in regions

    @pytest.mark.live
    @pytest.mark.integration
    def test_get_service_schema_ecs(self, vcr) -> None:
        """get_service_schema returns valid schema for ecs."""
        schema = get_service_schema("ecs")
        assert isinstance(schema, dict)
        assert schema["service"] == "ecs"
        assert "columns" in schema
        assert isinstance(schema["columns"], dict)
        assert len(schema["columns"]) > 0


class TestLiveQueryPricing:
    """Live API tests for pricing tools."""

    @pytest.mark.live
    @pytest.mark.integration
    def test_query_pricing_single_service(self, vcr) -> None:
        """query_pricing returns results for single service."""
        result = query_pricing(["ecs"], max_results=10)
        assert isinstance(result, dict)
        assert "services" in result
        # Should have at least some ECS items
        assert "ecs" in result["services"]
        assert len(result["services"]["ecs"]) > 0
        # Check structure of first item
        item = result["services"]["ecs"][0]
        assert "id" in item
        assert "currency" in item
        assert "region" in item
        assert "priceAmount" in item

    @pytest.mark.live
    @pytest.mark.integration
    def test_query_pricing_region_filter(self, vcr) -> None:
        """query_pricing respects region filter."""
        result = query_pricing(["ecs"], region="eu-de", max_results=10)
        assert isinstance(result, dict)
        # All items should be eu-de
        for item in result["services"].get("ecs", []):
            assert item["region"] == "eu-de"

    @pytest.mark.live
    @pytest.mark.integration
    def test_query_pricing_multi_service(self, vcr) -> None:
        """query_pricing handles multiple services."""
        result = query_pricing(["ecs", "evs"], max_results=5)
        assert isinstance(result, dict)
        assert "services" in result
        # Should have results from at least one service
        assert len(result["services"]) > 0
        # Total items should be sum of all services
        total = result.get("total_items", 0)
        assert total > 0

    @pytest.mark.live
    @pytest.mark.integration
    def test_find_compute_flavor(self, vcr) -> None:
        """find_compute_flavor returns matching ECS instances."""
        # Find common flavor: 1 vCPU, 1 GB RAM
        result = find_compute_flavor(v_cpu=1, ram_gb=1, region="eu-de")
        assert isinstance(result, list)
        # Should find at least Linux variants
        if result:
            for item in result:
                assert int(item.get("vCpu", 0)) == 1
                assert float(item.get("ram", "0 GiB").split()[0]) == 1.0


class TestLiveEstimation:
    """Live API tests for estimation tools."""

    @pytest.mark.live
    @pytest.mark.integration
    def test_estimate_monthly_cost_single_item(self, vcr) -> None:
        """estimate_monthly_cost calculates costs for known product."""
        # Use ECS S3.medium.1 which we know exists
        result = estimate_monthly_cost([{"id": "OTC_S3M1_LI", "quantity": 1}])
        assert isinstance(result, dict)
        assert "total_payg" in result
        assert "currency" in result
        assert result["currency"] == "EUR"
        # PAYG cost should be positive
        assert result["total_payg"] > 0

    @pytest.mark.live
    @pytest.mark.integration
    def test_estimate_monthly_cost_multiple_items(self, vcr) -> None:
        """estimate_monthly_cost handles multiple products."""
        result = estimate_monthly_cost(
            [
                {"id": "OTC_S3M1_LI", "quantity": 1},
                {"id": "OTC_S3M1_LI", "quantity": 2},
            ]
        )
        assert isinstance(result, dict)
        assert len(result.get("items", [])) > 0

    @pytest.mark.live
    @pytest.mark.integration
    def test_compare_billing_models_single_product(self, vcr) -> None:
        """compare_billing_models shows cost comparison."""
        result = compare_billing_models("OTC_S3M1_LI", quantity=1)
        assert isinstance(result, dict)
        assert "payg" in result
        assert "reserved_12m" in result
        # PAYG should have monthly cost
        assert result["payg"]["monthly_cost"] > 0
        # Reserved should show savings
        assert "savings_percent" in result["reserved_12m"]


class TestLiveClientDirect:
    """Direct client tests against live API."""

    @pytest.mark.live
    @pytest.mark.integration
    def test_client_ecs_query(self, vcr) -> None:
        """OTCPricingClient can fetch ECS data."""
        client = OTCPricingClient()
        try:
            response = client.get(
                {
                    "serviceName": "ecs",
                    "limitMax": "10",
                }
            )
            assert response.code == "Success"
            assert response.stats.count > 0
            assert isinstance(response.result, dict)
            assert "ecs" in response.result
        finally:
            client.close()

    @pytest.mark.live
    @pytest.mark.integration
    def test_client_filter_region(self, vcr) -> None:
        """OTCPricingClient respects region filter."""
        client = OTCPricingClient()
        try:
            response = client.get(
                {
                    "serviceName": "ecs",
                    "filterBy[region]": "eu-de",
                    "limitMax": "10",
                }
            )
            assert response.code == "Success"
            # Result should be a list when filtered
            if response.result:
                if isinstance(response.result, list):
                    for item in response.result:
                        assert item.get("region") == "eu-de"
        finally:
            client.close()

    @pytest.mark.live
    @pytest.mark.integration
    def test_normalize_parse_price_from_api(self, vcr) -> None:
        """parse_price handles real API price strings."""
        client = OTCPricingClient()
        try:
            response = client.get({"serviceName": "ecs", "limitMax": "1"})
            items = extract_items(response, "ecs")
            if items:
                item = items[0]
                # Parse the real price string
                amount, currency = parse_price(item.price_amount)
                assert currency in ("EUR", "CHF")
                assert float(amount) >= 0
        finally:
            client.close()
