"""Estimation tools: estimate_monthly_cost, compare_billing_models."""

from __future__ import annotations

from typing import Any


def estimate_monthly_cost(
    items: list[dict[str, Any]],
) -> dict[str, Any]:
    """Estimate monthly cost for a list of resources.

    Args:
        items: List of resources, each with 'id' and optional 'quantity' and 'hours_per_month'.
               Example: [{'id': 'OTC_S3M1_LI', 'quantity': 2, 'hours_per_month': 730}]

    Returns:
        Dictionary with total cost, breakdown by item, and currency.
    """
    raise NotImplementedError("Story 2 implementation pending")


def compare_billing_models(
    product_id: str,
    quantity: float = 1.0,
    hours_per_month: float = 730.0,
) -> dict[str, Any]:
    """Compare PAYG vs. Reserved billing models for a product.

    Args:
        product_id: Product ID (e.g., 'OTC_S3M1_LI').
        quantity: Quantity (default: 1).
        hours_per_month: Hours per month (default: 730).

    Returns:
        Dictionary comparing PAYG and Reserved (12/24/36 month) costs.
    """
    raise NotImplementedError("Story 2 implementation pending")
