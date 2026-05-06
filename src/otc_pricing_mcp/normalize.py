"""Normalization and parsing utilities for OTC API responses.

Handles:
- Price string parsing ("0.051175 EUR" → Decimal + currency code)
- Result shape normalization (dict vs. list) to consistent internal format
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from .models import ApiResponse, PriceItem


def parse_price(price_string: str) -> tuple[Decimal, str]:
    """Parse a price string into (amount, currency_code).

    Args:
        price_string: A string like "0.051175 EUR" or "23.150000 CHF"

    Returns:
        A tuple (Decimal, str) representing the amount and currency code.

    Raises:
        ValueError: If the string cannot be parsed.

    Examples:
        >>> parse_price("0.051175 EUR")
        (Decimal('0.051175'), 'EUR')
        >>> parse_price("0.000000 CHF")
        (Decimal('0'), 'CHF')
    """
    parts = price_string.strip().split()

    if len(parts) != 2:
        raise ValueError(f"Expected 'amount currency' format, got: {price_string!r}")

    amount_str, currency = parts

    try:
        amount = Decimal(amount_str)
    except Exception as e:
        raise ValueError(f"Could not parse amount '{amount_str}' as Decimal: {e}") from e

    return (amount, currency)


def extract_items(response: ApiResponse, service: str | None = None) -> list[PriceItem]:
    """Extract and normalize price items from an API response.

    Handles the quirk that the API returns either:
    - dict keyed by service (when no filterBy is used)
    - flat list (when filterBy is used)

    This function normalizes both shapes and returns a consistent list.

    Args:
        response: Parsed ApiResponse object.
        service: Service name to extract. Only used if result is a dict.
                If None and result is a dict, returns empty list.

    Returns:
        List of parsed PriceItem objects.
    """
    if isinstance(response.result, dict):
        if service is None:
            return []
        items = response.result.get(service, [])
    elif isinstance(response.result, list):
        items = response.result
    else:
        return []

    parsed: list[PriceItem] = []
    for item in items:
        try:
            parsed.append(PriceItem(**item))
        except Exception:
            continue

    return parsed


def normalize_response(
    raw_dict: dict[str, Any], service: str | None = None
) -> tuple[list[PriceItem], ApiResponse]:
    """Parse and normalize a raw API response dict.

    Args:
        raw_dict: Raw JSON response from the API (top-level dict with "response" key).
        service: Service name to extract (only used if result is a dict).

    Returns:
        A tuple (items, response) where items is a list of PriceItem and response
        is the parsed ApiResponse envelope.

    Raises:
        ValueError: If the raw_dict doesn't have the expected structure.
    """
    if "response" not in raw_dict:
        raise ValueError("Expected 'response' key in API response")

    response_dict = raw_dict["response"]
    response = ApiResponse(**response_dict)
    items = extract_items(response, service)

    return (items, response)
