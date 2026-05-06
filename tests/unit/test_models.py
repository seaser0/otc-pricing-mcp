"""Unit tests for models.py."""

from __future__ import annotations

from otc_pricing_mcp.models import ApiResponse, ApiStats, PriceItem


class TestPriceItem:
    """Tests for PriceItem model."""

    def test_create_price_item_minimal(self) -> None:
        """Create a minimal valid PriceItem with Python field names."""
        item = PriceItem(
            id="OTC_S3M1_LI",
            id_group="OTC_S3M1_LI",
            id_group_tiered="",
            product_id="ECS",
            product_name="Test",
            product_type="OTC",
            product_family="Compute",
            product_category="General",
            product_id_parameter="ecs",
            product_section="main",
            service_type="s3",
            opi_flavour="s3.medium.1",
            os_unit="Linux",
            v_cpu="1",
            ram="1 GiB",
            storage_type="",
            storage_volume="",
            currency="EUR",
            price_amount="0.051175 EUR",
            unit="h",
            description="VM",
            region="eu-de",
            is_mrc=False,
            from_on=1,
            up_to=999999999999,
            min_amount=1,
            max_amount=999999999999,
            additional_text="",
            r12="0.000000 EUR",
            r24="0.000000 EUR",
            r36="0.000000 EUR",
            ru12="0.000000 EUR",
            ru24="0.000000 EUR",
            ru36="0.000000 EUR",
        )

        assert item.id == "OTC_S3M1_LI"
        assert item.currency == "EUR"
        assert item.region == "eu-de"

    def test_price_item_extra_allow(self) -> None:
        """PriceItem accepts extra fields for forward compatibility."""
        item = PriceItem(
            id="OTC_S3M1_LI",
            id_group="OTC_S3M1_LI",
            id_group_tiered="",
            product_id="ECS",
            product_name="Test",
            product_type="OTC",
            product_family="Compute",
            product_category="General",
            product_id_parameter="ecs",
            product_section="main",
            service_type="s3",
            opi_flavour="s3.medium.1",
            os_unit="Linux",
            v_cpu="1",
            ram="1 GiB",
            storage_type="",
            storage_volume="",
            currency="EUR",
            price_amount="0.051175 EUR",
            unit="h",
            description="VM",
            region="eu-de",
            is_mrc=False,
            from_on=1,
            up_to=999999999999,
            min_amount=1,
            max_amount=999999999999,
            additional_text="",
            r12="0.000000 EUR",
            r24="0.000000 EUR",
            r36="0.000000 EUR",
            ru12="0.000000 EUR",
            ru24="0.000000 EUR",
            ru36="0.000000 EUR",
            future_field="value",  # type: ignore[call-arg]
        )

        assert getattr(item, "future_field", None) == "value"


class TestApiStats:
    """Tests for ApiStats model."""

    def test_create_api_stats(self) -> None:
        """Create a valid ApiStats."""
        stats = ApiStats(
            count=828,
            recordsCount=100,
            maxPages=10,
            recordsPerPage=100,
            currentPage=1,
            currentUri="https://example.com",
        )

        assert stats.count == 828
        assert stats.records_count == 100


class TestApiResponse:
    """Tests for ApiResponse model."""

    def test_create_api_response_with_dict_result(self) -> None:
        """Create a valid ApiResponse with dict result."""
        response = ApiResponse(
            cachedAt="2026-05-06 15:34:09",
            httpCode=200,
            url="https://example.com",
            parameters={"productType": "OTC", "serviceName": "ecs"},
            code="Success",
            message="OK",
            stats=ApiStats(
                count=100,
                recordsCount=5,
                maxPages=20,
                recordsPerPage=5,
                currentPage=1,
                currentUri="https://example.com",
            ),
            result={"ecs": []},
            columns={},
        )

        assert response.code == "Success"
        assert isinstance(response.result, dict)
        assert "ecs" in response.result

    def test_create_api_response_with_list_result(self) -> None:
        """Create a valid ApiResponse with list result."""
        response = ApiResponse(
            cachedAt="2026-05-06 15:34:09",
            httpCode=200,
            url="https://example.com",
            parameters={"productType": "OTC"},
            code="Success",
            message="OK",
            stats=ApiStats(
                count=10,
                recordsCount=10,
                maxPages=1,
                recordsPerPage=10,
                currentPage=1,
                currentUri="https://example.com",
            ),
            result=[],
            columns={},
        )

        assert isinstance(response.result, list)
