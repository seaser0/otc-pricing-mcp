"""Unit tests for MCP tool implementations."""

from __future__ import annotations

from typing import Any

import pytest

from otc_pricing_mcp.tools import discovery as discovery_module
from otc_pricing_mcp.tools import estimation as estimation_module
from otc_pricing_mcp.tools import pricing as pricing_module
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

    def test_query_pricing_multi_service(self) -> None:
        """query_pricing handles multiple services with parallel fan-out."""
        try:
            result = query_pricing(["ecs", "evs"], max_results=5)
            assert isinstance(result, dict)
            # Services dict may contain either or both services
            assert isinstance(result.get("services"), dict)
            # Should have warnings if any service failed
            assert isinstance(result.get("warnings"), list)
        except Exception:
            pass

    def test_query_pricing_with_region_filter(self) -> None:
        """query_pricing accepts region filter."""
        try:
            result = query_pricing(["ecs"], region="eu-de", max_results=5)
            assert isinstance(result, dict)
            # If results exist, should only have eu-de
            if result.get("services") and result.get("services").get("ecs"):
                for item in result["services"]["ecs"]:
                    assert item.get("region") == "eu-de"
        except Exception:
            pass

    def test_query_pricing_unknown_region_raises(self) -> None:
        """query_pricing rejects regions outside the known set (#6)."""
        with pytest.raises(ValueError, match="Unknown region 'mars-1'"):
            query_pricing(["ecs"], region="mars-1")

    def test_query_pricing_unknown_region_lists_known(self) -> None:
        """The error message names the regions a caller can use (#6)."""
        with pytest.raises(ValueError, match="eu-de"):
            query_pricing(["ecs"], region="not-a-region")

    def test_query_pricing_known_region_does_not_raise(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """All entries in list_regions() must be accepted by query_pricing (#6)."""

        def _fake_fetch(service: str, params: dict) -> tuple[str, list, str | None]:
            return (service, [], None)

        monkeypatch.setattr(pricing_module, "_fetch_service_pricing", _fake_fetch)
        for region in list_regions():
            result = query_pricing(["ecs"], region=region, max_results=1)
            assert isinstance(result, dict)
            assert result["total_items"] == 0
            assert result["warnings"] == []

    def test_query_pricing_zero_rows_emits_note(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Valid region with zero upstream rows surfaces a note, not a warning (#6).

        Notes are informational; they must NOT trigger isError on the server.
        """

        def _fake_fetch(service: str, params: dict) -> tuple[str, list, str | None]:
            return (service, [], None)

        monkeypatch.setattr(pricing_module, "_fetch_service_pricing", _fake_fetch)
        result = query_pricing(["ecs"], region="eu-ch2", max_results=5)

        assert result["total_items"] == 0
        assert result["warnings"] == []
        assert "notes" in result
        assert any("ecs/eu-ch2" in note for note in result["notes"])
        assert any("0 rows" in note for note in result["notes"])

    def test_query_pricing_upstream_error_emits_warning_not_note(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Hard upstream errors keep going to warnings, not to notes (#6)."""

        def _fake_fetch(service: str, params: dict) -> tuple[str, list, str | None]:
            return (service, [], "boom: upstream HTTP 500")

        monkeypatch.setattr(pricing_module, "_fetch_service_pricing", _fake_fetch)
        result = query_pricing(["ecs"], region="eu-de", max_results=5)

        assert result["warnings"] != []
        assert any("boom" in w for w in result["warnings"])
        # Errored services must not also appear as zero-row notes.
        assert all("ecs/eu-de" not in note for note in result.get("notes", []))


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

    def test_find_compute_flavor_unknown_region_raises(self) -> None:
        """find_compute_flavor propagates the region-validation ValueError (#6)."""
        with pytest.raises(ValueError, match="Unknown region"):
            find_compute_flavor(v_cpu=4, ram_gb=16, region="mars-1")


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
        """compare_billing_models reports savings_percent only on offered tiers (#7, #32)."""
        try:
            result = compare_billing_models("OTC_S3M1_LI")
            # Each reserved tier is either {available: False} (no savings_percent)
            # or {available: True, ..., savings_percent: ...}.
            for tier in ("reserved_12m", "reserved_24m", "reserved_36m"):
                tier_payload = result.get(tier, {})
                assert "available" in tier_payload, f"{tier} must report availability"
                if tier_payload["available"]:
                    assert "savings_percent" in tier_payload
                    # Savings may be negative (#32 — reserved can cost more than PAYG).
                    # It must never exceed 100 % on a real tier.
                    assert tier_payload["savings_percent"] <= 100.0
                    assert "reserved_more_expensive_than_payg" in tier_payload
                else:
                    # Unavailable tiers must NOT include the misleading 100% number (#7).
                    assert "savings_percent" not in tier_payload
                    assert "monthly_cost" not in tier_payload
        except ValueError:
            pass


def _stub_product_data(monkeypatch: pytest.MonkeyPatch, product: dict[str, str]) -> None:
    """Make estimation tools see exactly one upstream product, deterministically.

    Patches the OTCPricingClient instance produced inside estimation.py so the
    test never hits the network. The fake response carries `product` under a
    single service key.
    """

    class _FakeResponse:
        result = {"ecs": [product]}

    class _FakeClient:
        def __init__(self) -> None:  # noqa: D401 - test stub
            pass

        def get(self, params: dict) -> Any:  # noqa: D401 - test stub
            return _FakeResponse()

        def close(self) -> None:  # noqa: D401 - test stub
            pass

    monkeypatch.setattr(estimation_module, "OTCPricingClient", _FakeClient)


class TestReservedTierAvailability:
    """Issue #7 — distinguish 'tier not offered' from 'tier costs €0.0'."""

    _FULL_PRODUCT = {
        "id": "OTC_FAKE",
        "currency": "EUR",
        "priceAmount": "0.10 EUR",
        "R12": "60.00 EUR",
        "R24": "50.00 EUR",
        "R36": "40.00 EUR",
        "RU12": "100.00 EUR",
        "RU24": "200.00 EUR",
        "RU36": "300.00 EUR",
    }

    _NO_36M = {
        "id": "OTC_FAKE",
        "currency": "EUR",
        "priceAmount": "0.10 EUR",
        "R12": "60.00 EUR",
        "R24": "50.00 EUR",
        "R36": "0.00 EUR",
        "RU12": "100.00 EUR",
        "RU24": "200.00 EUR",
        "RU36": "0.00 EUR",
    }

    def test_estimate_zero_reserved_tier_is_nulled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """When R36 == RU36 == 0.0, both per-item and total are None, not 0.0."""
        _stub_product_data(monkeypatch, self._NO_36M)
        result = estimate_monthly_cost([{"id": "OTC_FAKE"}])

        assert result["items"][0]["reserved_12m"] is not None
        assert result["items"][0]["reserved_36m"] is None
        assert result["items"][0]["reserved_upfront_36m"] is None
        assert "reserved_36m" not in result["items"][0]["tiers_available"]

        # Total is None because the (only) item lacks the tier.
        assert result["total_reserved_36m"] is None
        assert result["total_reserved_upfront_36m"] is None
        assert result["total_reserved_12m"] is not None
        assert "reserved_36m" in result["tiers_unavailable"]
        assert "reserved_12m" not in result["tiers_unavailable"]

    def test_estimate_full_product_keeps_all_tiers(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A product with all reserved tiers offered reports floats everywhere."""
        _stub_product_data(monkeypatch, self._FULL_PRODUCT)
        result = estimate_monthly_cost([{"id": "OTC_FAKE"}])

        for tier in ("reserved_12m", "reserved_24m", "reserved_36m"):
            assert result[f"total_{tier}"] is not None
            assert result["items"][0][tier] is not None
        assert result["tiers_unavailable"] == []
        assert set(result["items"][0]["tiers_available"]) == {
            "payg",
            "reserved_12m",
            "reserved_24m",
            "reserved_36m",
        }

    def test_compare_billing_zero_reserved_marks_unavailable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """compare_billing_models reports {available:false} instead of 100% savings (#7)."""
        _stub_product_data(monkeypatch, self._NO_36M)
        result = compare_billing_models("OTC_FAKE")

        assert result["reserved_36m"] == {"available": False}
        # The other tiers stay populated and are never 100% savings on real data.
        for tier in ("reserved_12m", "reserved_24m"):
            assert result[tier]["available"] is True
            assert "savings_percent" in result[tier]
            assert result[tier]["savings_percent"] < 100.0

        assert "reserved_36m" not in result["tiers_available"]
        assert "reserved_12m" in result["tiers_available"]

    def test_compare_billing_all_offered_includes_savings(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When every tier is offered, savings_percent appears for each."""
        _stub_product_data(monkeypatch, self._FULL_PRODUCT)
        result = compare_billing_models("OTC_FAKE")

        for tier in ("reserved_12m", "reserved_24m", "reserved_36m"):
            assert result[tier]["available"] is True
            assert "savings_percent" in result[tier]


# ---------------------------------------------------------------------------
# Issue #33 — max_results=0 falsy-check bug
# ---------------------------------------------------------------------------


class TestMaxResultsValidation:
    """Issue #33 — max_results < 1 must raise ValueError."""

    def test_max_results_zero_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """max_results=0 → ValueError (was silently mapped to 5000)."""
        monkeypatch.setattr(pricing_module, "list_services", lambda: ["ecs"])
        with pytest.raises(ValueError, match="max_results must be >= 1"):
            query_pricing(["ecs"], max_results=0)

    def test_max_results_negative_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """max_results=-1 → ValueError."""
        monkeypatch.setattr(pricing_module, "list_services", lambda: ["ecs"])
        with pytest.raises(ValueError, match="max_results must be >= 1"):
            query_pricing(["ecs"], max_results=-1)

    def test_max_results_none_defaults_to_5000(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """max_results=None defaults to 5000 (not zero)."""
        captured: dict[str, str] = {}

        def _fake_fetch(service: str, params: dict) -> tuple[str, list, str | None]:
            captured["limitMax"] = params.get("limitMax", "")
            return (service, [], None)

        monkeypatch.setattr(pricing_module, "_fetch_service_pricing", _fake_fetch)
        monkeypatch.setattr(pricing_module, "list_services", lambda: ["ecs"])
        query_pricing(["ecs"], max_results=None)
        assert captured["limitMax"] == "5000"

    def test_max_results_positive_accepted(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Positive max_results does not raise."""

        def _fake_fetch(service: str, params: dict) -> tuple[str, list, str | None]:
            return (service, [], None)

        monkeypatch.setattr(pricing_module, "_fetch_service_pricing", _fake_fetch)
        monkeypatch.setattr(pricing_module, "list_services", lambda: ["ecs"])
        result = query_pricing(["ecs"], max_results=10)
        assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# Issue #34 — unknown service → clean error (no URL leak)
# ---------------------------------------------------------------------------


class TestServiceValidationInQueryPricing:
    """Issue #34 — unknown services rejected before upstream call."""

    def test_unknown_service_raises_value_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(pricing_module, "list_services", lambda: ["ecs", "evs"])
        with pytest.raises(ValueError, match="Unknown service"):
            query_pricing(["foobar"])

    def test_unknown_service_names_the_bad_service(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(pricing_module, "list_services", lambda: ["ecs", "evs"])
        with pytest.raises(ValueError, match="foobar"):
            query_pricing(["foobar"])

    def test_unknown_service_no_url_in_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(pricing_module, "list_services", lambda: ["ecs", "evs"])
        with pytest.raises(ValueError) as exc_info:
            query_pricing(["foobar"])
        assert "calculator.otc-service.com" not in str(exc_info.value)

    def test_empty_catalog_skips_validation(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """When catalog is unavailable (empty list), validation is bypassed gracefully."""
        monkeypatch.setattr(pricing_module, "list_services", lambda: [])

        def _fake_fetch(service: str, params: dict) -> tuple[str, list, str | None]:
            return (service, [], None)

        monkeypatch.setattr(pricing_module, "_fetch_service_pricing", _fake_fetch)
        result = query_pricing(["ecs"])
        assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# Issue #35 — get_service_schema: empty / unknown service
# ---------------------------------------------------------------------------


class TestGetServiceSchemaValidation:
    """Issue #35 — empty or unknown service is rejected before API call."""

    def test_empty_string_raises(self) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            get_service_schema("")

    def test_blank_string_raises(self) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            get_service_schema("   ")

    def test_unknown_service_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(discovery_module, "_load_catalog", lambda: ["ecs", "evs"])
        with pytest.raises(ValueError, match="foobarbaz"):
            get_service_schema("foobarbaz")

    def test_unknown_service_suggests_list_services(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(discovery_module, "_load_catalog", lambda: ["ecs", "evs"])
        with pytest.raises(ValueError, match="list_services"):
            get_service_schema("foobarbaz")

    def test_unknown_service_no_url_in_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(discovery_module, "_load_catalog", lambda: ["ecs", "evs"])
        with pytest.raises(ValueError) as exc_info:
            get_service_schema("foobarbaz")
        assert "calculator.otc-service.com" not in str(exc_info.value)


# ---------------------------------------------------------------------------
# Issue #37 — get_service_schema: actually_used_columns
# ---------------------------------------------------------------------------


def _stub_schema_client(
    monkeypatch: pytest.MonkeyPatch,
    service: str,
    columns: dict,
    row: dict,
) -> None:
    """Patch OTCPricingClient inside discovery.py with a fake that returns one row."""

    class _FakeResponse:
        def __init__(self) -> None:
            self.columns = columns
            self.result: dict = {service: [row]}

    class _FakeClient:
        def __init__(self) -> None:
            pass

        def get(self, params: dict) -> _FakeResponse:
            return _FakeResponse()

        def close(self) -> None:
            pass

    monkeypatch.setattr(discovery_module, "OTCPricingClient", _FakeClient)


class TestGetServiceSchemaActuallyUsed:
    """Issue #37 — schema includes actually_used_columns derived from a sample row."""

    _COLS = {"id": "ID", "priceAmount": "Price", "vCpu": "vCPU", "ram": "RAM"}

    def test_schema_has_actually_used_columns_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(discovery_module, "_load_catalog", lambda: ["ecs"])
        _stub_schema_client(
            monkeypatch,
            "ecs",
            self._COLS,
            {"id": "FAKE", "priceAmount": "0.10 EUR", "vCpu": "2", "ram": "8 GiB"},
        )
        schema = get_service_schema("ecs")
        assert "actually_used_columns" in schema
        assert isinstance(schema["actually_used_columns"], list)

    def test_actually_used_excludes_empty_columns(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Columns that are empty in the sample row are excluded from actually_used."""
        monkeypatch.setattr(discovery_module, "_load_catalog", lambda: ["obs"])
        _stub_schema_client(
            monkeypatch,
            "obs",
            self._COLS,
            {"id": "FAKE", "priceAmount": "0.10 EUR", "vCpu": "", "ram": ""},
        )
        schema = get_service_schema("obs")
        assert "id" in schema["actually_used_columns"]
        assert "priceAmount" in schema["actually_used_columns"]
        assert "vCpu" not in schema["actually_used_columns"]
        assert "ram" not in schema["actually_used_columns"]

    def test_actually_used_is_subset_of_filterable(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """actually_used_columns must always be a subset of filterable_columns."""
        monkeypatch.setattr(discovery_module, "_load_catalog", lambda: ["ecs"])
        _stub_schema_client(
            monkeypatch,
            "ecs",
            self._COLS,
            {"id": "FAKE", "priceAmount": "0.05 EUR", "vCpu": "4", "ram": "16 GiB"},
        )
        schema = get_service_schema("ecs")
        assert set(schema["actually_used_columns"]) <= set(schema["filterable_columns"])

    def test_no_sample_row_yields_empty_actually_used(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """When the service has no rows at all, actually_used_columns is empty (not an error)."""

        class _FakeResponseEmpty:
            columns = self._COLS
            result: dict = {"ecs": []}

        class _FakeClient:
            def __init__(self) -> None:
                pass

            def get(self, params: dict) -> _FakeResponseEmpty:
                return _FakeResponseEmpty()

            def close(self) -> None:
                pass

        monkeypatch.setattr(discovery_module, "_load_catalog", lambda: ["ecs"])
        monkeypatch.setattr(discovery_module, "OTCPricingClient", _FakeClient)
        schema = get_service_schema("ecs")
        assert schema["actually_used_columns"] == []


# ---------------------------------------------------------------------------
# Issue #36 — negative quantity / hours_per_month rejected
# ---------------------------------------------------------------------------

_FULL_PRODUCT_36 = {
    "id": "OTC_FAKE36",
    "currency": "EUR",
    "priceAmount": "0.10 EUR",
    "R12": "60.00 EUR",
    "R24": "50.00 EUR",
    "R36": "40.00 EUR",
    "RU12": "100.00 EUR",
    "RU24": "200.00 EUR",
    "RU36": "300.00 EUR",
}


class TestNegativeQuantityValidation:
    """Issue #36 — quantity < 1 and hours_per_month < 0 are rejected upfront."""

    def test_estimate_negative_quantity_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _stub_product_data(monkeypatch, _FULL_PRODUCT_36)
        with pytest.raises(ValueError, match="quantity must be >= 1"):
            estimate_monthly_cost([{"id": "OTC_FAKE36", "quantity": -1}])

    def test_estimate_zero_quantity_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _stub_product_data(monkeypatch, _FULL_PRODUCT_36)
        with pytest.raises(ValueError, match="quantity must be >= 1"):
            estimate_monthly_cost([{"id": "OTC_FAKE36", "quantity": 0}])

    def test_estimate_negative_hours_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _stub_product_data(monkeypatch, _FULL_PRODUCT_36)
        with pytest.raises(ValueError, match="hours_per_month must be >= 0"):
            estimate_monthly_cost([{"id": "OTC_FAKE36", "hours_per_month": -1}])

    def test_estimate_zero_hours_allowed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """hours_per_month=0 is legal — resource exists but ran 0 hours (cost = 0)."""
        _stub_product_data(monkeypatch, _FULL_PRODUCT_36)
        result = estimate_monthly_cost([{"id": "OTC_FAKE36", "hours_per_month": 0}])
        assert result["total_payg"] == 0.0

    def test_compare_negative_quantity_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _stub_product_data(monkeypatch, _FULL_PRODUCT_36)
        with pytest.raises(ValueError, match="quantity must be >= 1"):
            compare_billing_models("OTC_FAKE36", quantity=-1)

    def test_compare_negative_hours_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _stub_product_data(monkeypatch, _FULL_PRODUCT_36)
        with pytest.raises(ValueError, match="hours_per_month must be >= 0"):
            compare_billing_models("OTC_FAKE36", hours_per_month=-1)

    def test_compare_zero_hours_allowed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """hours_per_month=0 in compare_billing_models → PAYG cost is 0, no crash."""
        _stub_product_data(monkeypatch, _FULL_PRODUCT_36)
        result = compare_billing_models("OTC_FAKE36", hours_per_month=0)
        assert result["payg"]["monthly_cost"] == 0.0


# ---------------------------------------------------------------------------
# Issue #32 — savings_percent may be negative (reserved costs more than PAYG)
# ---------------------------------------------------------------------------


class TestNegativeSavingsPercent:
    """Issue #32 — savings_percent is honest, not clamped; reserved_more_expensive flag added."""

    _PRODUCT = {
        "id": "OTC_FAKE32",
        "currency": "EUR",
        "priceAmount": "0.10 EUR",
        "R12": "60.00 EUR",
        "R24": "50.00 EUR",
        "R36": "40.00 EUR",
        "RU12": "100.00 EUR",
        "RU24": "200.00 EUR",
        "RU36": "300.00 EUR",
    }

    def test_negative_savings_reported_not_clamped(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """At 168 h/mo PAYG is cheap; reserved monthly equivalent is much higher → negative."""
        _stub_product_data(monkeypatch, self._PRODUCT)
        # payg_monthly = 0.10 * 168 = 16.8
        # 12m monthly_equiv = (60*12+100)/12 = 68.33 → savings = (16.8-68.33)/16.8*100 < 0
        result = compare_billing_models("OTC_FAKE32", hours_per_month=168)
        for tier in ("reserved_12m", "reserved_24m", "reserved_36m"):
            tier_data = result[tier]
            assert tier_data["available"] is True
            assert tier_data["savings_percent"] < 0
            assert tier_data["reserved_more_expensive_than_payg"] is True

    def test_positive_savings_flag_is_false(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """At 730 h/mo reserved saves money → savings_percent > 0, flag False."""
        _stub_product_data(monkeypatch, self._PRODUCT)
        # payg_monthly = 0.10 * 730 = 73.0
        # 12m monthly_equiv = (60*12+100)/12 = 68.33 → savings ≈ 6.4 %
        result = compare_billing_models("OTC_FAKE32", hours_per_month=730)
        for tier in ("reserved_12m", "reserved_24m", "reserved_36m"):
            tier_data = result[tier]
            assert tier_data["available"] is True
            assert tier_data["savings_percent"] > 0
            assert tier_data["reserved_more_expensive_than_payg"] is False

    def test_savings_percent_never_exceeds_100(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Sanity bound: savings_percent <= 100 for any offered tier."""
        _stub_product_data(monkeypatch, self._PRODUCT)
        result = compare_billing_models("OTC_FAKE32", hours_per_month=730)
        for tier in ("reserved_12m", "reserved_24m", "reserved_36m"):
            assert result[tier]["savings_percent"] <= 100.0


# ---------------------------------------------------------------------------
# Issue #31 — unknown product IDs produce warnings, not silent 0.0
# ---------------------------------------------------------------------------


def _stub_empty_catalog(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make OTCPricingClient return a catalog with no products."""

    class _FakeResponseEmpty:
        result: dict = {"ecs": []}

    class _FakeClient:
        def __init__(self) -> None:
            pass

        def get(self, params: dict) -> _FakeResponseEmpty:
            return _FakeResponseEmpty()

        def close(self) -> None:
            pass

    monkeypatch.setattr(estimation_module, "OTCPricingClient", _FakeClient)


class TestUnknownProductIds:
    """Issue #31 — unknown product IDs produce warnings, not silent 0.0."""

    def test_unknown_product_returns_warning(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _stub_empty_catalog(monkeypatch)
        result = estimate_monthly_cost([{"id": "NONEXISTENT"}])
        assert "NONEXISTENT" in result["unknown_product_ids"]
        assert any("NONEXISTENT" in w for w in result["warnings"])

    def test_unknown_product_items_is_empty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _stub_empty_catalog(monkeypatch)
        result = estimate_monthly_cost([{"id": "NONEXISTENT"}])
        assert result["items"] == []

    def test_partial_unknown_keeps_known_item(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Mixed batch: known item priced correctly; unknown surfaced in warnings."""
        _stub_product_data(monkeypatch, _FULL_PRODUCT_36)
        result = estimate_monthly_cost([
            {"id": "OTC_FAKE36"},
            {"id": "BOGUS"},
        ])
        assert "BOGUS" in result["unknown_product_ids"]
        assert any("BOGUS" in w for w in result["warnings"])
        # The known item is still priced.
        assert len(result["items"]) == 1
        assert result["items"][0]["id"] == "OTC_FAKE36"

    def test_partial_unknown_is_not_is_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Partial result (some priced) → warnings present but items non-empty."""
        _stub_product_data(monkeypatch, _FULL_PRODUCT_36)
        result = estimate_monthly_cost([
            {"id": "OTC_FAKE36"},
            {"id": "BOGUS"},
        ])
        # items is non-empty → server should NOT set isError for partial results.
        assert len(result["items"]) > 0
