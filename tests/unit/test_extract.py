"""Unit tests for extract_items and normalize_response."""

from __future__ import annotations

import pytest

from otc_pricing_mcp.models import ApiResponse, ApiStats, PriceItem
from otc_pricing_mcp.normalize import extract_items, normalize_response


@pytest.fixture
def sample_price_item_dict() -> dict:
    """A sample price item dictionary (API response format with aliases)."""
    return {
        "id": "OTC_S3M1_LI",
        "_idGroup": "OTC_S3M1_LI",
        "idGroupTiered": "",
        "productId": "ECS",
        "productName": "Test",
        "productType": "OTC",
        "productFamily": "Compute",
        "productCategory": "General",
        "productIdParameter": "ecs",
        "productSection": "main",
        "serviceType": "s3",
        "opiFlavour": "s3.medium.1",
        "osUnit": "Linux",
        "vCpu": "1",
        "ram": "1 GiB",
        "storageType": "",
        "storageVolume": "",
        "currency": "EUR",
        "priceAmount": "0.051175 EUR",
        "unit": "h",
        "description": "VM",
        "region": "eu-de",
        "isMRC": False,
        "fromOn": 1,
        "upTo": 999999999999,
        "minAmount": 1,
        "maxAmount": 999999999999,
        "additionalText": "",
        "R12": "0.000000 EUR",
        "R24": "0.000000 EUR",
        "R36": "0.000000 EUR",
        "RU12": "0.000000 EUR",
        "RU24": "0.000000 EUR",
        "RU36": "0.000000 EUR",
    }


class TestExtractItems:
    """Tests for extract_items function."""

    def test_extract_from_dict_result(self, sample_price_item_dict: dict) -> None:
        """Extract items from dict-keyed result."""
        response = ApiResponse(
            cachedAt="2026-05-06 15:34:09",
            httpCode=200,
            url="https://example.com",
            parameters={"productType": "OTC", "serviceName": "ecs"},
            code="Success",
            message="OK",
            stats=ApiStats(
                count=100,
                recordsCount=1,
                maxPages=100,
                recordsPerPage=1,
                currentPage=1,
                currentUri="https://example.com",
            ),
            result={"ecs": [sample_price_item_dict]},
            columns={},
        )

        items = extract_items(response, "ecs")
        assert len(items) == 1
        assert isinstance(items[0], PriceItem)
        assert items[0].id == "OTC_S3M1_LI"

    def test_extract_from_list_result(self, sample_price_item_dict: dict) -> None:
        """Extract items from flat list result."""
        response = ApiResponse(
            cachedAt="2026-05-06 15:34:09",
            httpCode=200,
            url="https://example.com",
            parameters={"productType": "OTC", "filterBy": {"region": ["eu-de"]}},
            code="Success",
            message="OK",
            stats=ApiStats(
                count=1,
                recordsCount=1,
                maxPages=1,
                recordsPerPage=1,
                currentPage=1,
                currentUri="https://example.com",
            ),
            result=[sample_price_item_dict],
            columns={},
        )

        items = extract_items(response)
        assert len(items) == 1
        assert items[0].id == "OTC_S3M1_LI"

    def test_extract_empty_dict(self) -> None:
        """Extract from empty dict result."""
        response = ApiResponse(
            cachedAt="2026-05-06 15:34:09",
            httpCode=200,
            url="https://example.com",
            parameters={},
            code="Success",
            message="OK",
            stats=ApiStats(
                count=0,
                recordsCount=0,
                maxPages=0,
                recordsPerPage=0,
                currentPage=1,
                currentUri="https://example.com",
            ),
            result={"ecs": []},
            columns={},
        )

        items = extract_items(response, "ecs")
        assert items == []

    def test_extract_empty_list(self) -> None:
        """Extract from empty list result."""
        response = ApiResponse(
            cachedAt="2026-05-06 15:34:09",
            httpCode=200,
            url="https://example.com",
            parameters={},
            code="Success",
            message="OK",
            stats=ApiStats(
                count=0,
                recordsCount=0,
                maxPages=0,
                recordsPerPage=0,
                currentPage=1,
                currentUri="https://example.com",
            ),
            result=[],
            columns={},
        )

        items = extract_items(response)
        assert items == []

    def test_extract_from_dict_without_service(self) -> None:
        """Extract from dict result without specifying service returns empty."""
        response = ApiResponse(
            cachedAt="2026-05-06 15:34:09",
            httpCode=200,
            url="https://example.com",
            parameters={},
            code="Success",
            message="OK",
            stats=ApiStats(
                count=0,
                recordsCount=0,
                maxPages=0,
                recordsPerPage=0,
                currentPage=1,
                currentUri="https://example.com",
            ),
            result={"ecs": []},
            columns={},
        )

        items = extract_items(response, service=None)
        assert items == []

    def test_extract_missing_service_in_dict(self) -> None:
        """Extract from dict result with missing service returns empty."""
        response = ApiResponse(
            cachedAt="2026-05-06 15:34:09",
            httpCode=200,
            url="https://example.com",
            parameters={},
            code="Success",
            message="OK",
            stats=ApiStats(
                count=0,
                recordsCount=0,
                maxPages=0,
                recordsPerPage=0,
                currentPage=1,
                currentUri="https://example.com",
            ),
            result={"ecs": []},
            columns={},
        )

        items = extract_items(response, "evs")
        assert items == []


class TestNormalizeResponse:
    """Tests for normalize_response function."""

    def test_normalize_valid_response(self, sample_price_item_dict: dict) -> None:
        """Normalize a valid raw API response."""
        raw = {
            "response": {
                "cachedAt": "2026-05-06 15:34:09",
                "httpCode": 200,
                "url": "https://example.com",
                "parameters": {"productType": "OTC", "serviceName": "ecs"},
                "code": "Success",
                "message": "OK",
                "stats": {
                    "count": 100,
                    "recordsCount": 1,
                    "maxPages": 100,
                    "recordsPerPage": 1,
                    "currentPage": 1,
                    "currentUri": "https://example.com",
                },
                "result": {"ecs": [sample_price_item_dict]},
                "columns": {},
            }
        }

        items, response = normalize_response(raw, "ecs")
        assert len(items) == 1
        assert items[0].id == "OTC_S3M1_LI"
        assert response.code == "Success"

    def test_normalize_missing_response_key(self) -> None:
        """Fail on missing response key."""
        raw = {"data": {}}

        with pytest.raises(ValueError, match="Expected 'response' key"):
            normalize_response(raw)

    def test_normalize_list_result(self, sample_price_item_dict: dict) -> None:
        """Normalize response with list result."""
        raw = {
            "response": {
                "cachedAt": "2026-05-06 15:34:09",
                "httpCode": 200,
                "url": "https://example.com",
                "parameters": {},
                "code": "Success",
                "message": "OK",
                "stats": {
                    "count": 1,
                    "recordsCount": 1,
                    "maxPages": 1,
                    "recordsPerPage": 1,
                    "currentPage": 1,
                    "currentUri": "https://example.com",
                },
                "result": [sample_price_item_dict],
                "columns": {},
            }
        }

        items, response = normalize_response(raw)
        assert len(items) == 1
        assert items[0].id == "OTC_S3M1_LI"
