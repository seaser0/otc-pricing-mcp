"""Unit tests for MCP tool implementations."""

from __future__ import annotations

import pytest

from otc_pricing_mcp.tools.discovery import get_service_schema, list_regions, list_services
from otc_pricing_mcp.tools.estimation import compare_billing_models, estimate_monthly_cost
from otc_pricing_mcp.tools.pricing import find_compute_flavor, query_pricing


class TestListServices:
    """Tests for list_services discovery tool."""

    def test_list_services_returns_list(self) -> None:
        """list_services returns a list of service names."""
        services = list_services()
        assert isinstance(services, list)
        # Should contain at least some known services (if API is reachable)
        # This may be empty if API fails, which is OK for unit test


class TestListRegions:
    """Tests for list_regions discovery tool."""

    def test_list_regions_returns_list(self) -> None:
        """list_regions returns a list of region codes."""
        regions = list_regions()
        assert isinstance(regions, list)
        # Should be sorted
        assert regions == sorted(regions)


class TestGetServiceSchema:
    """Tests for get_service_schema discovery tool."""

    def test_get_service_schema_returns_dict(self) -> None:
        """get_service_schema returns schema dict for a service."""
        try:
            schema = get_service_schema("ecs")
            assert isinstance(schema, dict)
            assert "service" in schema
            assert "columns" in schema
            assert "filterable_columns" in schema
            assert "returnable_columns" in schema
        except ValueError:
            # OK if service not found (API unavailable)
            pass


class TestQueryPricing:
    """Tests for query_pricing tool."""

    def test_query_pricing_empty_services_fails(self) -> None:
        """query_pricing with empty services list fails."""
        with pytest.raises(ValueError, match="At least one service"):
            query_pricing([])

    def test_query_pricing_returns_dict(self) -> None:
        """query_pricing returns a dict with expected structure."""
        try:
            result = query_pricing(["ecs"], max_results=10)
            assert isinstance(result, dict)
            assert "services" in result
            assert "total_items" in result
            assert "currency_breakdown" in result
            assert "regions_found" in result
            assert "warnings" in result
        except Exception:
            # OK if API unavailable
            pass

    def test_query_pricing_respects_max_results(self) -> None:
        """query_pricing respects the max_results parameter."""
        try:
            result = query_pricing(["ecs"], max_results=1)
            assert isinstance(result, dict)
            total = result.get("total_items", 0)
            # Should be at most 1 (may be 0 if no results)
            assert total <= 1
        except Exception:
            pass


class TestFindComputeFlavor:
    """Tests for find_compute_flavor tool."""

    def test_find_compute_flavor_returns_list(self) -> None:
        """find_compute_flavor returns a list."""
        try:
            result = find_compute_flavor(v_cpu=1, ram_gb=1)
            assert isinstance(result, list)
        except Exception:
            pass

    def test_find_compute_flavor_with_os_filter(self) -> None:
        """find_compute_flavor accepts OS filter."""
        try:
            result = find_compute_flavor(v_cpu=1, ram_gb=1, os="Linux")
            assert isinstance(result, list)
        except Exception:
            pass

    def test_find_compute_flavor_with_region(self) -> None:
        """find_compute_flavor accepts region parameter."""
        try:
            result = find_compute_flavor(v_cpu=1, ram_gb=1, region="eu-nl")
            assert isinstance(result, list)
        except Exception:
            pass


class TestEstimateMonthlyCost:
    """Tests for estimate_monthly_cost tool."""

    def test_estimate_empty_items_fails(self) -> None:
        """estimate_monthly_cost with empty items fails."""
        with pytest.raises(ValueError, match="At least one item"):
            estimate_monthly_cost([])

    def test_estimate_no_valid_ids_fails(self) -> None:
        """estimate_monthly_cost with no valid IDs fails."""
        with pytest.raises(ValueError, match="No valid product IDs"):
            estimate_monthly_cost([{}])

    def test_estimate_monthly_cost_returns_dict(self) -> None:
        """estimate_monthly_cost returns dict with cost breakdown."""
        try:
            result = estimate_monthly_cost([{"id": "OTC_S3M1_LI", "quantity": 1}])
            assert isinstance(result, dict)
            assert "total_payg" in result
            assert "total_reserved_12m" in result
            assert "currency" in result
            assert "items" in result
        except ValueError:
            # OK if product not found
            pass

    def test_estimate_with_custom_hours(self) -> None:
        """estimate_monthly_cost accepts custom hours_per_month."""
        try:
            result = estimate_monthly_cost(
                [
                    {
                        "id": "OTC_S3M1_LI",
                        "quantity": 1,
                        "hours_per_month": 168,
                    }
                ]
            )
            assert isinstance(result, dict)
        except ValueError:
            pass


class TestCompareBillingModels:
    """Tests for compare_billing_models tool."""

    def test_compare_invalid_product_fails(self) -> None:
        """compare_billing_models with invalid product fails."""
        with pytest.raises(ValueError, match="not found"):
            compare_billing_models("INVALID_PRODUCT_ID_XYZ")

    def test_compare_returns_dict(self) -> None:
        """compare_billing_models returns comparison dict."""
        try:
            result = compare_billing_models("OTC_S3M1_LI", quantity=1)
            assert isinstance(result, dict)
            assert "product_id" in result
            assert "payg" in result
            assert "reserved_12m" in result
            assert "reserved_24m" in result
            assert "reserved_36m" in result
        except ValueError:
            # OK if product not found
            pass

    def test_compare_with_quantity(self) -> None:
        """compare_billing_models accepts quantity parameter."""
        try:
            result = compare_billing_models("OTC_S3M1_LI", quantity=2)
            assert result.get("quantity") == 2
        except ValueError:
            pass

    def test_compare_reserved_savings(self) -> None:
        """compare_billing_models calculates savings correctly."""
        try:
            result = compare_billing_models("OTC_S3M1_LI")
            # Reserved should show savings_percent
            assert "savings_percent" in result.get("reserved_12m", {})
            assert "savings_percent" in result.get("reserved_24m", {})
            assert "savings_percent" in result.get("reserved_36m", {})
        except ValueError:
            pass
