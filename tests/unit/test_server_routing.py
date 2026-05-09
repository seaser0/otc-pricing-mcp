"""Unit tests for server.py call_tool routing."""

from __future__ import annotations

import json
from unittest.mock import patch


def _run(coro):  # type: ignore[no-untyped-def]
    import asyncio

    return asyncio.run(coro)


class TestCallToolRouting:
    """Verify call_tool routes to implementations and returns valid JSON."""

    def setup_method(self) -> None:
        # Import lazily so observability is initialized first
        from otc_pricing_mcp.server import call_tool

        self._call_tool = call_tool

    def _invoke(self, name: str, arguments: dict) -> str:
        # call_tool always returns a CallToolResult (#12).
        result = _run(self._call_tool(name, arguments))
        assert len(result.content) == 1
        return result.content[0].text

    def _invoke_full(self, name: str, arguments: dict):  # type: ignore[no-untyped-def]
        """Return the whole CallToolResult so isError can be asserted."""
        return _run(self._call_tool(name, arguments))

    def test_list_services_not_stub(self) -> None:
        with patch("otc_pricing_mcp.server.list_services", return_value=["ecs", "evs"]):
            text = self._invoke("list_services", {})
        assert text != "Not yet implemented"
        parsed = json.loads(text)
        assert parsed == ["ecs", "evs"]

    def test_list_regions_not_stub(self) -> None:
        with patch("otc_pricing_mcp.server.list_regions", return_value=["eu-de", "eu-nl"]):
            text = self._invoke("list_regions", {})
        assert text != "Not yet implemented"
        parsed = json.loads(text)
        assert parsed == ["eu-de", "eu-nl"]

    def test_get_service_schema_not_stub(self) -> None:
        schema = {
            "service": "ecs",
            "columns": {},
            "filterable_columns": [],
            "returnable_columns": [],
        }
        with patch("otc_pricing_mcp.server.get_service_schema", return_value=schema):
            text = self._invoke("get_service_schema", {"service": "ecs"})
        assert text != "Not yet implemented"
        assert json.loads(text)["service"] == "ecs"

    def test_query_pricing_not_stub(self) -> None:
        result = {
            "services": {},
            "total_items": 0,
            "currency_breakdown": {},
            "regions_found": [],
            "warnings": [],
        }
        with patch("otc_pricing_mcp.server.query_pricing", return_value=result):
            text = self._invoke("query_pricing", {"services": ["ecs"]})
        assert text != "Not yet implemented"
        assert "total_items" in json.loads(text)

    def test_query_pricing_passes_region(self) -> None:
        result = {
            "services": {},
            "total_items": 0,
            "currency_breakdown": {},
            "regions_found": [],
            "warnings": [],
        }
        with patch("otc_pricing_mcp.server.query_pricing", return_value=result) as mock_qp:
            self._invoke(
                "query_pricing", {"services": ["ecs"], "region": "eu-de", "max_results": 10}
            )
        mock_qp.assert_called_once_with(["ecs"], "eu-de", 10)

    def test_find_compute_flavor_not_stub(self) -> None:
        # find_compute_flavor returns {matches, warnings, notes} (see pricing.py).
        fcf_result = {"matches": [], "warnings": [], "notes": []}
        with patch("otc_pricing_mcp.server.find_compute_flavor", return_value=fcf_result):
            text = self._invoke("find_compute_flavor", {"v_cpu": 4, "ram_gb": 8})
        assert text != "Not yet implemented"
        assert json.loads(text) == fcf_result

    def test_find_compute_flavor_defaults_region(self) -> None:
        fcf_result = {"matches": [], "warnings": [], "notes": []}
        with patch(
            "otc_pricing_mcp.server.find_compute_flavor", return_value=fcf_result
        ) as mock_fcf:
            self._invoke("find_compute_flavor", {"v_cpu": 2, "ram_gb": 4})
        # region should default to eu-de when not supplied; positional: v_cpu, ram_gb, os, region
        args = mock_fcf.call_args.args
        assert args[3] == "eu-de"

    def test_estimate_monthly_cost_not_stub(self) -> None:
        result = {
            "total_payg": 0.0,
            "total_reserved_12m": 0.0,
            "total_reserved_24m": 0.0,
            "total_reserved_36m": 0.0,
            "total_reserved_upfront_12m": 0.0,
            "total_reserved_upfront_24m": 0.0,
            "total_reserved_upfront_36m": 0.0,
            "currency": "EUR",
            "items": [],
        }
        with patch("otc_pricing_mcp.server.estimate_monthly_cost", return_value=result):
            text = self._invoke("estimate_monthly_cost", {"items": [{"id": "X"}]})
        assert text != "Not yet implemented"
        assert "total_payg" in json.loads(text)

    def test_compare_billing_models_not_stub(self) -> None:
        result = {
            "product_id": "X",
            "currency": "EUR",
            "quantity": 1.0,
            "hours_per_month": 730.0,
            "payg": {"monthly_cost": 0.0, "hourly_rate": 0.0},
            "reserved_12m": {},
            "reserved_24m": {},
            "reserved_36m": {},
        }
        with patch("otc_pricing_mcp.server.compare_billing_models", return_value=result):
            text = self._invoke("compare_billing_models", {"product_id": "X"})
        assert text != "Not yet implemented"
        assert json.loads(text)["product_id"] == "X"

    def test_compare_billing_models_defaults(self) -> None:
        result = {
            "product_id": "X",
            "currency": "EUR",
            "quantity": 1.0,
            "hours_per_month": 730.0,
            "payg": {},
            "reserved_12m": {},
            "reserved_24m": {},
            "reserved_36m": {},
        }
        with patch(
            "otc_pricing_mcp.server.compare_billing_models", return_value=result
        ) as mock_cbm:
            self._invoke("compare_billing_models", {"product_id": "X"})
        mock_cbm.assert_called_once_with("X", 1.0, 730.0)

    def test_unknown_tool_returns_error(self) -> None:
        text = self._invoke("nonexistent_tool", {})
        assert "Unknown tool" in text

    def test_tool_exception_returns_error_message(self) -> None:
        with patch("otc_pricing_mcp.server.list_services", side_effect=RuntimeError("api down")):
            text = self._invoke("list_services", {})
        assert "Error executing tool" in text
        assert "api down" in text

    def test_tool_exception_sets_isError_true(self) -> None:
        """Uncaught exceptions surface as isError=true on the CallToolResult (#12)."""
        with patch("otc_pricing_mcp.server.list_services", side_effect=RuntimeError("api down")):
            result = self._invoke_full("list_services", {})
        assert result.isError is True

    def test_success_sets_isError_false(self) -> None:
        """Happy-path calls return isError=false (#12)."""
        with patch("otc_pricing_mcp.server.list_services", return_value=["ecs"]):
            result = self._invoke_full("list_services", {})
        assert result.isError is False

    def test_query_pricing_upstream_error_sets_isError_true(self) -> None:
        """An empty result with warnings still propagates as isError=true (#4 contract preserved)."""
        bad_result = {
            "services": {},
            "total_items": 0,
            "currency_breakdown": {},
            "regions_found": [],
            "warnings": ["ecs: boom"],
            "notes": [],
        }
        with patch("otc_pricing_mcp.server.query_pricing", return_value=bad_result):
            result = self._invoke_full("query_pricing", {"services": ["ecs"]})
        assert result.isError is True

    def test_estimate_monthly_cost_all_unknown_sets_isError_true(self) -> None:
        """issue #31: all product IDs unknown → isError=true."""
        bad_result = {
            "total_payg": 0.0,
            "currency": "EUR",
            "items": [],
            "tiers_unavailable": ["reserved_12m", "reserved_24m", "reserved_36m"],
            "total_reserved_12m": None,
            "total_reserved_24m": None,
            "total_reserved_36m": None,
            "total_reserved_upfront_12m": None,
            "total_reserved_upfront_24m": None,
            "total_reserved_upfront_36m": None,
            "warnings": ["Product 'BOGUS' not found in catalog"],
            "unknown_product_ids": ["BOGUS"],
        }
        with patch("otc_pricing_mcp.server.estimate_monthly_cost", return_value=bad_result):
            result = self._invoke_full(
                "estimate_monthly_cost", {"items": [{"id": "BOGUS"}]}
            )
        assert result.isError is True

    def test_estimate_monthly_cost_partial_unknown_not_isError(self) -> None:
        """issue #31: partial result (some items priced) → isError=false."""
        partial_result = {
            "total_payg": 10.0,
            "currency": "EUR",
            "items": [{"id": "OTC_REAL", "payg": 10.0, "currency": "EUR"}],
            "tiers_unavailable": [],
            "total_reserved_12m": None,
            "total_reserved_24m": None,
            "total_reserved_36m": None,
            "total_reserved_upfront_12m": None,
            "total_reserved_upfront_24m": None,
            "total_reserved_upfront_36m": None,
            "warnings": ["Product 'BOGUS' not found in catalog"],
            "unknown_product_ids": ["BOGUS"],
        }
        with patch("otc_pricing_mcp.server.estimate_monthly_cost", return_value=partial_result):
            result = self._invoke_full(
                "estimate_monthly_cost",
                {"items": [{"id": "OTC_REAL"}, {"id": "BOGUS"}]},
            )
        assert result.isError is False
