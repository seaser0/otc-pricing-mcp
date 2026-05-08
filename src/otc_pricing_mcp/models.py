"""Pydantic models for OTC Price Calculator API responses.

Covers the API response envelope and the PriceItem schema.
Schema verified against probe results from 2026-05-06.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class PriceItem(BaseModel):
    """A pricing record from the OTC Price Calculator API.

    Covers all 34 documented fields plus forward-compatibility with `extra="allow"`.
    Field descriptions come from the API's `columns` metadata.
    """

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    id: str
    id_group: str = Field(alias="_idGroup")
    id_group_tiered: str = Field(alias="idGroupTiered")
    product_id: str = Field(alias="productId")
    product_name: str = Field(alias="productName")
    product_type: str = Field(alias="productType")
    product_family: str = Field(alias="productFamily")
    product_category: str = Field(alias="productCategory")
    product_id_parameter: str = Field(alias="productIdParameter")
    product_section: str = Field(alias="productSection")

    service_type: str = Field(alias="serviceType")
    opi_flavour: str = Field(alias="opiFlavour")

    os_unit: str = Field(alias="osUnit")
    v_cpu: str = Field(alias="vCpu")
    ram: str
    storage_type: str = Field(alias="storageType")
    storage_volume: str = Field(alias="storageVolume")

    currency: str
    price_amount: str = Field(alias="priceAmount")
    unit: str
    description: str

    region: str
    is_mrc: bool = Field(alias="isMRC")
    from_on: int = Field(alias="fromOn")
    up_to: int = Field(alias="upTo")
    min_amount: int = Field(alias="minAmount")
    max_amount: int = Field(alias="maxAmount")

    additional_text: str = Field(alias="additionalText")

    r12: str = Field(alias="R12")
    r24: str = Field(alias="R24")
    r36: str = Field(alias="R36")
    ru12: str = Field(alias="RU12")
    ru24: str = Field(alias="RU24")
    ru36: str = Field(alias="RU36")

    def dict_with_snake_case(self) -> dict[str, Any]:
        """Return model as dict with snake_case keys (matching Python field names)."""
        return self.model_dump(by_alias=False)


class ApiStats(BaseModel):
    """Statistics metadata from API response."""

    count: int
    records_count: int = Field(alias="recordsCount")
    max_pages: int = Field(alias="maxPages", default=0)
    records_per_page: int = Field(alias="recordsPerPage")
    current_page: int = Field(alias="currentPage")
    current_uri: str = Field(alias="currentUri")


class ApiResponse(BaseModel):
    """Wrapper for OTC Price Calculator API responses.

    The top-level response structure includes metadata, the result (which varies
    in shape), columns, and pagination info.
    """

    model_config = ConfigDict(extra="allow")

    cached_at: str | None = Field(alias="cachedAt", default=None)
    http_code: int = Field(alias="httpCode")
    url: str
    parameters: dict[str, Any]
    code: str
    message: str
    stats: ApiStats
    result: dict[str, list[dict[str, Any]]] | list[dict[str, Any]]
    columns: dict[str, str] = Field(default_factory=dict)
    filters: list[Any] = Field(default_factory=list)
    services: dict[str, Any] = Field(default_factory=dict)
    pagination: dict[str, Any] = Field(default_factory=dict)
