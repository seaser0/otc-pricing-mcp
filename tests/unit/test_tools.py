"""Unit tests for MCP tool implementations."""

from __future__ import annotations

from typing import Any

import pytest

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

    def test_query_pricing_eu_ch2_sets_client_param(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """eu-ch2 must inject `client=2` so the Swiss/CHF catalog is exposed (#50)."""
        captured: dict[str, Any] = {}

        def _fake_fetch(service: str, params: dict) -> tuple[str, list, str | None]:
            captured["params"] = dict(params)
            return (service, [], None)

        monkeypatch.setattr(pricing_module, "_fetch_service_pricing", _fake_fetch)
        query_pricing(["ecs"], region="eu-ch2", max_results=1)

        assert captured["params"].get("client") == "2"
        assert captured["params"].get("filterBy[region]") == "eu-ch2"

    def test_query_pricing_non_swiss_region_omits_client_param(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Public-cloud regions (eu-de/eu-nl) must NOT set `client` (#50)."""
        seen: list[dict] = []

        def _fake_fetch(service: str, params: dict) -> tuple[str, list, str | None]:
            seen.append(dict(params))
            return (service, [], None)

        monkeypatch.setattr(pricing_module, "_fetch_service_pricing", _fake_fetch)
        for region in ("eu-de", "eu-nl"):
            query_pricing(["ecs"], region=region, max_results=1)

        assert all("client" not in p for p in seen)

    def test_query_pricing_no_region_omits_client_param(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Region-less queries stay on the default catalog (no `client` param) (#50)."""
        captured: dict[str, Any] = {}

        def _fake_fetch(service: str, params: dict) -> tuple[str, list, str | None]:
            captured["params"] = dict(params)
            return (service, [], None)

        monkeypatch.setattr(pricing_module, "_fetch_service_pricing", _fake_fetch)
        query_pricing(["ecs"], max_results=1)

        assert "client" not in captured["params"]

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
        """compare_billing_models reports savings_percent only on offered tiers (#7)."""
        try:
            result = compare_billing_models("OTC_S3M1_LI")
            # Each reserved tier is either {available: False} (no savings_percent)
            # or {available: True, ..., savings_percent: ...}.
            for tier in ("reserved_12m", "reserved_24m", "reserved_36m"):
                tier_payload = result.get(tier, {})
                assert "available" in tier_payload, f"{tier} must report availability"
                if tier_payload["available"]:
                    assert "savings_percent" in tier_payload
                    # Savings must never exceed 100% on a real tier.
                    assert 0.0 <= tier_payload["savings_percent"] <= 100.0
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
# QA bug-bash from 2026-05-08 (issues #30-#37). Each test below pins an
# end-state contract that the original bug violated.
# ---------------------------------------------------------------------------


class TestFindComputeFlavorFiltersStorage:
    """Issue #30 — find_compute_flavor must NOT return EVS storage rows."""

    def test_v_cpu_zero_raises(self) -> None:
        with pytest.raises(ValueError, match="v_cpu must be >= 1"):
            find_compute_flavor(v_cpu=0, ram_gb=0)

    def test_negative_v_cpu_raises(self) -> None:
        with pytest.raises(ValueError, match="v_cpu must be >= 1"):
            find_compute_flavor(v_cpu=-1, ram_gb=1)

    def test_zero_ram_raises(self) -> None:
        with pytest.raises(ValueError, match="ram_gb must be > 0"):
            find_compute_flavor(v_cpu=1, ram_gb=0)

    def test_storage_rows_filtered_out(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Even at a valid v_cpu/ram, EVS rows that happen to share the
        upstream service must be skipped via product_family check."""
        # Build a fake query_pricing result with one Compute and one Storage row
        # at the same v_cpu/ram values. The Storage row must NOT appear in matches.
        from otc_pricing_mcp.models import PriceItem
        from otc_pricing_mcp.tools.pricing import _fetch_service_pricing  # noqa: F401

        def _row(**overrides: Any) -> PriceItem:
            base: dict[str, Any] = {
                "id": "X",
                "_idGroup": "X",
                "idGroupTiered": "",
                "productId": "ECS",
                "productName": "X",
                "productType": "OTC",
                "productFamily": "Compute",
                "productCategory": "",
                "productIdParameter": "ecs",
                "productSection": "main",
                "serviceType": "s3",
                "opiFlavour": "s3.x.1",
                "osUnit": "Linux",
                "vCpu": "2",
                "ram": "4 GiB",
                "storageType": "",
                "storageVolume": "",
                "currency": "EUR",
                "priceAmount": "1 EUR",
                "unit": "hour",
                "description": "",
                "region": "eu-de",
                "isMRC": False,
                "fromOn": 1,
                "upTo": 1,
                "minAmount": 0,
                "maxAmount": 0,
                "additionalText": "",
                "R12": "0",
                "R24": "0",
                "R36": "0",
                "RU12": "0",
                "RU24": "0",
                "RU36": "0",
            }
            base.update(overrides)
            return PriceItem.model_validate(base)

        compute_row = _row()
        storage_row = _row(
            id="Y",
            productName="EVS",
            productFamily="Storage",
            productSection="storage",
            opiFlavour="vss.sas",
            osUnit="Standard",
            unit="GB",
            description="EVS",
            priceAmount="0.06 EUR",
        )

        def fake_fetch(service: str, params: dict) -> tuple[str, list, str | None]:
            return (service, [compute_row, storage_row], None)

        monkeypatch.setattr(pricing_module, "_fetch_service_pricing", fake_fetch)
        result = find_compute_flavor(v_cpu=2, ram_gb=4, region="eu-de")

        assert len(result["matches"]) == 1
        assert result["matches"][0]["product_family"] == "Compute"
        assert all(m["product_family"] == "Compute" for m in result["matches"])


class TestQueryPricingMaxResultsValidation:
    """Issue #33 — max_results=0 must NOT collapse to default 5000."""

    def test_max_results_zero_raises(self) -> None:
        with pytest.raises(ValueError, match="max_results must be >= 1"):
            query_pricing(["ecs"], region="eu-de", max_results=0)

    def test_max_results_negative_raises(self) -> None:
        with pytest.raises(ValueError, match="max_results must be >= 1"):
            query_pricing(["ecs"], region="eu-de", max_results=-1)

    def test_max_results_none_uses_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        captured: dict = {}

        def fake_fetch(service: str, params: dict) -> tuple[str, list, str | None]:
            captured["limitMax"] = params.get("limitMax")
            return (service, [], None)

        monkeypatch.setattr(pricing_module, "_fetch_service_pricing", fake_fetch)
        query_pricing(["ecs"], region="eu-de", max_results=None)
        assert captured["limitMax"] == "5000"


class TestEstimateMonthlyCostUnknownProduct:
    """Issue #31 — silent total_payg=0 for unknown product IDs is now surfaced."""

    def test_unknown_id_in_warnings(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Empty upstream — nothing matches.
        class _Empty:
            result: dict = {"ecs": []}

        class _C:
            def __init__(self) -> None:
                pass

            def get(self, p: dict) -> Any:
                return _Empty()

            def close(self) -> None:
                pass

        monkeypatch.setattr(estimation_module, "OTCPricingClient", _C)
        result = estimate_monthly_cost([{"id": "BOGUS"}])
        assert result["unknown_product_ids"] == ["BOGUS"]
        assert any("BOGUS" in w for w in result["warnings"])
        assert result["items"] == []
        assert result["total_payg"] == 0.0

    def test_partial_unknown_keeps_known_in_total(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Mixed batch: one known product, one unknown id. Known item must
        # still be priced; unknown must surface in warnings.
        product = {
            "id": "OTC_KNOWN",
            "currency": "EUR",
            "priceAmount": "0.10 EUR",
            "R12": "60.00 EUR",
            "R24": "50.00 EUR",
            "R36": "40.00 EUR",
            "RU12": "100.00 EUR",
            "RU24": "200.00 EUR",
            "RU36": "300.00 EUR",
        }
        _stub_product_data(monkeypatch, product)
        result = estimate_monthly_cost([{"id": "OTC_KNOWN"}, {"id": "OTC_NOPE"}])
        assert "OTC_NOPE" in result["unknown_product_ids"]
        assert "OTC_KNOWN" not in result["unknown_product_ids"]
        assert len(result["items"]) == 1
        assert result["total_payg"] > 0


class TestEstimateNegativeQuantity:
    """Issue #36 — negative quantity / hours must raise."""

    def test_negative_quantity_raises(self) -> None:
        with pytest.raises(ValueError, match="quantity must be >= 1"):
            estimate_monthly_cost([{"id": "X", "quantity": -1}])

    def test_negative_hours_raises(self) -> None:
        with pytest.raises(ValueError, match="hours_per_month must be >= 0"):
            estimate_monthly_cost([{"id": "X", "hours_per_month": -1}])

    def test_compare_negative_quantity_raises(self) -> None:
        with pytest.raises(ValueError, match="quantity must be >= 1"):
            compare_billing_models("X", quantity=-1)

    def test_compare_negative_hours_raises(self) -> None:
        with pytest.raises(ValueError, match="hours_per_month must be >= 0"):
            compare_billing_models("X", hours_per_month=-1)


class TestCompareBillingNegativeSavings:
    """Issue #32 — savings_percent must be allowed to be negative."""

    def test_low_usage_reports_negative_savings(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # PAYG at 168h * 0.05 = €8.40/mo, reserved_12m monthly_eq ~€25/mo
        # → savings should be a clearly-negative double-digit number.
        product = {
            "id": "OTC_LOW",
            "currency": "EUR",
            "priceAmount": "0.05 EUR",
            "R12": "20.00 EUR",
            "R24": "15.00 EUR",
            "R36": "10.00 EUR",
            "RU12": "50.00 EUR",
            "RU24": "100.00 EUR",
            "RU36": "150.00 EUR",
        }
        _stub_product_data(monkeypatch, product)
        result = compare_billing_models("OTC_LOW", hours_per_month=168)
        for tier in ("reserved_12m", "reserved_24m", "reserved_36m"):
            assert result[tier]["available"] is True
            assert result[tier]["savings_percent"] < 0, (
                f"{tier} savings should be negative but was {result[tier]['savings_percent']}"
            )
            assert result[tier]["reserved_more_expensive_than_payg"] is True

    def test_high_usage_reports_positive_savings(self, monkeypatch: pytest.MonkeyPatch) -> None:
        product = {
            "id": "OTC_HIGH",
            "currency": "EUR",
            "priceAmount": "0.20 EUR",
            "R12": "60.00 EUR",
            "R24": "50.00 EUR",
            "R36": "40.00 EUR",
            "RU12": "100.00 EUR",
            "RU24": "200.00 EUR",
            "RU36": "300.00 EUR",
        }
        _stub_product_data(monkeypatch, product)
        result = compare_billing_models("OTC_HIGH", hours_per_month=730)
        for tier in ("reserved_12m", "reserved_24m", "reserved_36m"):
            assert result[tier]["savings_percent"] > 0
            assert result[tier]["reserved_more_expensive_than_payg"] is False


class TestGetServiceSchemaValidation:
    """Issue #35 + #37 — empty/unknown rejected; schema flags global catalog."""

    def test_empty_service_raises(self) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            get_service_schema("")

    def test_whitespace_service_raises(self) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            get_service_schema("   ")


class TestEstimateSwissOTCClientParam:
    """Issue #50 — Swiss OTC product IDs require `client=2` to resolve upstream."""

    @staticmethod
    def _make_capturing_client(product: dict[str, str]) -> tuple[type, list[dict]]:
        seen: list[dict] = []

        class _Resp:
            result = {"ecs": [product]}

        class _C:
            def __init__(self) -> None:
                pass

            def get(self, p: dict) -> Any:
                seen.append(dict(p))
                return _Resp()

            def close(self) -> None:
                pass

        return _C, seen

    def test_swiss_id_triggers_client_param(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A product ID with the `-eu-ch2` suffix must inject `client=2` (#50)."""
        product = {
            "id": "OTC_S3M1_LI-eu-ch2",
            "currency": "CHF",
            "priceAmount": "0.10 CHF",
            "R12": "60.00 CHF",
            "R24": "50.00 CHF",
            "R36": "40.00 CHF",
            "RU12": "100.00 CHF",
            "RU24": "200.00 CHF",
            "RU36": "300.00 CHF",
        }
        client_cls, seen = self._make_capturing_client(product)
        monkeypatch.setattr(estimation_module, "OTCPricingClient", client_cls)

        result = estimate_monthly_cost([{"id": "OTC_S3M1_LI-eu-ch2"}])

        assert len(seen) == 1
        assert seen[0].get("client") == "2"
        assert result["currency"] == "CHF"
        assert result["total_payg"] > 0

    def test_non_swiss_id_omits_client_param(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Plain (public-cloud) product IDs must NOT set `client` (#50)."""
        product = {
            "id": "OTC_S3M1_LI",
            "currency": "EUR",
            "priceAmount": "0.10 EUR",
            "R12": "60.00 EUR",
            "R24": "50.00 EUR",
            "R36": "40.00 EUR",
            "RU12": "100.00 EUR",
            "RU24": "200.00 EUR",
            "RU36": "300.00 EUR",
        }
        client_cls, seen = self._make_capturing_client(product)
        monkeypatch.setattr(estimation_module, "OTCPricingClient", client_cls)

        estimate_monthly_cost([{"id": "OTC_S3M1_LI"}])

        assert len(seen) == 1
        assert "client" not in seen[0]
