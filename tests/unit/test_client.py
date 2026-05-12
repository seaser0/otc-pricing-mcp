"""Unit tests for the OTC HTTP client wrapper (client.py)."""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from otc_pricing_mcp.client import OTCPricingClient, _strip_ghost_eu_ch2_rows
from otc_pricing_mcp.models import ApiResponse, ApiStats


def _make_api_response(
    result: dict[str, list[dict]] | list[dict],
) -> ApiResponse:
    """Build a minimal ApiResponse around a fake `result` payload."""
    stats = ApiStats(
        count=0,
        recordsCount=0,
        recordsPerPage=0,
        currentPage=0,
        currentUri="",
    )
    return ApiResponse(
        httpCode=200,
        url="",
        parameters={},
        code="ok",
        message="",
        stats=stats,
        result=result,
        columns={},
    )


class TestStripGhostEuCh2Rows:
    """Issue #52 — drop region=eu-ch2 rows from client=1 responses."""

    def test_dict_payload_drops_eu_ch2_rows(self) -> None:
        """Per-service dict: eu-ch2 rows go, other regions stay."""
        resp = _make_api_response(
            {
                "coss": [
                    {"id": "OTC_OBSCD_SP_1-eu-ch2", "region": "eu-ch2", "currency": "EUR"},
                    {"id": "OTC_OBSCD_SP_1", "region": "eu-de", "currency": "EUR"},
                ],
                "apig": [
                    {"id": "OTC_APIG_D_BAS-eu-ch2", "region": "eu-ch2", "currency": "EUR"},
                ],
                "ecs": [
                    {"id": "OTC_S3M1_LI", "region": "eu-de", "currency": "EUR"},
                ],
            }
        )

        dropped = _strip_ghost_eu_ch2_rows(resp)

        assert dropped == 2
        assert resp.result["coss"] == [
            {"id": "OTC_OBSCD_SP_1", "region": "eu-de", "currency": "EUR"}
        ]
        assert resp.result["apig"] == []
        assert resp.result["ecs"] == [
            {"id": "OTC_S3M1_LI", "region": "eu-de", "currency": "EUR"}
        ]

    def test_list_payload_drops_eu_ch2_rows(self) -> None:
        """Flat list payload: eu-ch2 rows go, other regions stay."""
        resp = _make_api_response(
            [
                {"id": "OTC_X-eu-ch2", "region": "eu-ch2"},
                {"id": "OTC_X", "region": "eu-de"},
                {"id": "OTC_Y", "region": "eu-nl"},
            ]
        )

        dropped = _strip_ghost_eu_ch2_rows(resp)

        assert dropped == 1
        assert resp.result == [
            {"id": "OTC_X", "region": "eu-de"},
            {"id": "OTC_Y", "region": "eu-nl"},
        ]

    def test_no_ghosts_is_no_op(self) -> None:
        """A response without any eu-ch2 rows is returned unchanged."""
        resp = _make_api_response(
            {"ecs": [{"id": "OTC_S3M1_LI", "region": "eu-de"}]}
        )

        dropped = _strip_ghost_eu_ch2_rows(resp)

        assert dropped == 0
        assert resp.result == {"ecs": [{"id": "OTC_S3M1_LI", "region": "eu-de"}]}

    def test_empty_payload(self) -> None:
        """Empty dict / list / missing-service entries don't crash."""
        resp = _make_api_response({"ecs": [], "evs": []})
        assert _strip_ghost_eu_ch2_rows(resp) == 0
        assert resp.result == {"ecs": [], "evs": []}

        resp_list = _make_api_response([])
        assert _strip_ghost_eu_ch2_rows(resp_list) == 0
        assert resp_list.result == []


def _fake_upstream_payload(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Wrap rows in the full upstream JSON envelope shape."""
    return {
        "response": {
            "httpCode": 200,
            "url": "https://example/",
            "parameters": {},
            "code": "ok",
            "message": "",
            "stats": {
                "count": len(rows),
                "recordsCount": len(rows),
                "recordsPerPage": len(rows),
                "currentPage": 1,
                "currentUri": "",
            },
            "result": {"coss": rows},
            "columns": {},
        }
    }


class TestClientGetGhostFilterIntegration:
    """Issue #52 — `OTCPricingClient.get()` strips ghost rows for client=1 only."""

    _ROWS = [
        {"id": "OTC_OBSCD_SP_1-eu-ch2", "region": "eu-ch2", "currency": "EUR"},
        {"id": "OTC_OBSCD_SP_1", "region": "eu-de", "currency": "EUR"},
    ]

    def _patch_httpx(self, monkeypatch: pytest.MonkeyPatch) -> None:
        rows = self._ROWS

        def _fake_get(self: httpx.Client, url: str, params: dict | None = None) -> httpx.Response:
            return httpx.Response(
                200,
                json=_fake_upstream_payload(rows),
                request=httpx.Request("GET", "https://example/"),
            )

        monkeypatch.setattr(httpx.Client, "get", _fake_get)

    def test_client_1_response_strips_ghost_rows(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Without `client=2`, eu-ch2 rows are removed from the parsed response (#52)."""
        self._patch_httpx(monkeypatch)
        c = OTCPricingClient()
        try:
            resp = c.get({"serviceName": "coss"})
        finally:
            c.close()

        assert isinstance(resp.result, dict)
        assert resp.result["coss"] == [
            {"id": "OTC_OBSCD_SP_1", "region": "eu-de", "currency": "EUR"}
        ]

    def test_client_2_response_keeps_eu_ch2_rows(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """With `client=2`, eu-ch2 rows pass through untouched (#51 regression guard)."""
        self._patch_httpx(monkeypatch)
        c = OTCPricingClient()
        try:
            resp = c.get({"serviceName": "coss", "client": "2"})
        finally:
            c.close()

        assert isinstance(resp.result, dict)
        ids = [r["id"] for r in resp.result["coss"]]
        assert "OTC_OBSCD_SP_1-eu-ch2" in ids
        assert "OTC_OBSCD_SP_1" in ids
