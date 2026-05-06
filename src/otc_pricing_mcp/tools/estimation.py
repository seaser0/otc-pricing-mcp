"""Estimation tools: estimate_monthly_cost, compare_billing_models."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from otc_pricing_mcp.client import OTCPricingClient
from otc_pricing_mcp.normalize import parse_price


def estimate_monthly_cost(
    items: list[dict[str, Any]],
) -> dict[str, Any]:
    """Estimate monthly cost for a list of resources.

    Itemizes costs by product ID and sums to a total monthly cost.
    Supports both PAYG and reserved pricing models.

    Args:
        items: List of resource specifications. Each item is a dict with:
            - 'id': str (product ID, e.g., 'OTC_S3M1_LI'). Required.
            - 'quantity': float (number of instances, default: 1)
            - 'hours_per_month': float (default: 730, approximately 24/7)

    Returns:
        Dictionary with structure:
        {
            'total_payg': float,
            'total_reserved_12m': float,
            'total_reserved_24m': float,
            'total_reserved_36m': float,
            'total_reserved_upfront_12m': float,
            'total_reserved_upfront_24m': float,
            'total_reserved_upfront_36m': float,
            'currency': str,
            'items': [
                {
                    'id': str,
                    'quantity': float,
                    'hours_per_month': float,
                    'payg': float,
                    'reserved_12m': float,
                    'reserved_24m': float,
                    'reserved_36m': float,
                    'currency': str,
                },
                ...
            ]
        }

    Examples:
        # Single resource, 1 unit, default hours
        >>> estimate_monthly_cost([{'id': 'OTC_S3M1_LI'}])

        # Multiple resources with custom quantities
        >>> estimate_monthly_cost([
        ...     {'id': 'OTC_S3M1_LI', 'quantity': 2},
        ...     {'id': 'OTC_S3M2_LI', 'quantity': 1, 'hours_per_month': 168}
        ... ])
    """
    if not items:
        raise ValueError("At least one item is required")

    # Collect all unique product IDs
    product_ids = list({item["id"] for item in items if "id" in item})
    if not product_ids:
        raise ValueError("No valid product IDs found in items")

    # Fetch product data
    client = OTCPricingClient()
    product_data: dict[str, Any] = {}

    try:
        for product_id in product_ids:
            try:
                response = client.get(
                    {
                        "productType": "OTC",
                        "limitMax": "5000",
                    }
                )
                # Search through all services to find the product
                if isinstance(response.result, dict):
                    for service_items in response.result.values():
                        for item_dict in service_items:
                            if item_dict.get("id") == product_id:
                                product_data[product_id] = item_dict
                                break
                elif isinstance(response.result, list):
                    for item_dict in response.result:
                        if item_dict.get("id") == product_id:
                            product_data[product_id] = item_dict
                            break
            except Exception:
                continue
    finally:
        client.close()

    # Calculate costs
    item_results: list[dict[str, Any]] = []
    totals: dict[str, Decimal] = {
        "payg": Decimal("0"),
        "reserved_12m": Decimal("0"),
        "reserved_24m": Decimal("0"),
        "reserved_36m": Decimal("0"),
        "reserved_upfront_12m": Decimal("0"),
        "reserved_upfront_24m": Decimal("0"),
        "reserved_upfront_36m": Decimal("0"),
    }
    currency = "EUR"

    for item in items:
        product_id = item.get("id")
        if not product_id:
            continue

        quantity = Decimal(str(item.get("quantity", 1)))
        hours = Decimal(str(item.get("hours_per_month", 730)))

        if product_id not in product_data:
            continue

        product = product_data[product_id]
        currency = product.get("currency", "EUR")

        # Parse prices
        try:
            payg_amount, _ = parse_price(product.get("priceAmount", "0 EUR"))
            r12_amount, _ = parse_price(product.get("R12", "0 EUR"))
            r24_amount, _ = parse_price(product.get("R24", "0 EUR"))
            r36_amount, _ = parse_price(product.get("R36", "0 EUR"))
            ru12_amount, _ = parse_price(product.get("RU12", "0 EUR"))
            ru24_amount, _ = parse_price(product.get("RU24", "0 EUR"))
            ru36_amount, _ = parse_price(product.get("RU36", "0 EUR"))
        except Exception:
            continue

        # Calculate monthly costs
        payg_cost = payg_amount * hours * quantity
        r12_cost = r12_amount * quantity
        r24_cost = r24_amount * quantity
        r36_cost = r36_amount * quantity
        ru12_cost = ru12_amount * quantity
        ru24_cost = ru24_amount * quantity
        ru36_cost = ru36_amount * quantity

        item_results.append(
            {
                "id": product_id,
                "quantity": float(quantity),
                "hours_per_month": float(hours),
                "payg": float(payg_cost),
                "reserved_12m": float(r12_cost),
                "reserved_24m": float(r24_cost),
                "reserved_36m": float(r36_cost),
                "reserved_upfront_12m": float(ru12_cost),
                "reserved_upfront_24m": float(ru24_cost),
                "reserved_upfront_36m": float(ru36_cost),
                "currency": currency,
            }
        )

        totals["payg"] += payg_cost
        totals["reserved_12m"] += r12_cost
        totals["reserved_24m"] += r24_cost
        totals["reserved_36m"] += r36_cost
        totals["reserved_upfront_12m"] += ru12_cost
        totals["reserved_upfront_24m"] += ru24_cost
        totals["reserved_upfront_36m"] += ru36_cost

    return {
        "total_payg": float(totals["payg"]),
        "total_reserved_12m": float(totals["reserved_12m"]),
        "total_reserved_24m": float(totals["reserved_24m"]),
        "total_reserved_36m": float(totals["reserved_36m"]),
        "total_reserved_upfront_12m": float(totals["reserved_upfront_12m"]),
        "total_reserved_upfront_24m": float(totals["reserved_upfront_24m"]),
        "total_reserved_upfront_36m": float(totals["reserved_upfront_36m"]),
        "currency": currency,
        "items": item_results,
    }


def compare_billing_models(
    product_id: str,
    quantity: float = 1.0,
    hours_per_month: float = 730.0,
) -> dict[str, Any]:
    """Compare PAYG vs. Reserved billing models for a product.

    Shows the effective monthly cost under PAYG and reserved pricing options,
    enabling cost optimization decisions.

    Args:
        product_id: Product ID (e.g., 'OTC_S3M1_LI'). Required.
        quantity: Quantity (default: 1).
        hours_per_month: Hours per month (default: 730, approximately 24/7).

    Returns:
        Dictionary with structure:
        {
            'product_id': str,
            'currency': str,
            'payg': {
                'monthly_cost': float,
                'hourly_rate': float,
            },
            'reserved_12m': {
                'monthly_cost': float,
                'upfront_cost': float,
                'total_cost': float,
                'monthly_equivalent': float,
            },
            'reserved_24m': {...},
            'reserved_36m': {...},
            'savings': {
                '12m': float (percent),
                '24m': float (percent),
                '36m': float (percent),
            }
        }

    Examples:
        # Compare billing for single unit
        >>> compare_billing_models('OTC_S3M1_LI')

        # Compare for 2 units
        >>> compare_billing_models('OTC_S3M1_LI', quantity=2)
    """
    estimation = estimate_monthly_cost(
        [
            {
                "id": product_id,
                "quantity": quantity,
                "hours_per_month": hours_per_month,
            }
        ]
    )

    if not estimation["items"]:
        raise ValueError(f"Product '{product_id}' not found")

    item = estimation["items"][0]
    currency = item["currency"]

    payg_monthly = item["payg"]
    payg_hourly = payg_monthly / hours_per_month

    # Calculate reserved options (monthly + upfront)
    def calc_reserved(monthly: float, upfront: float, months: int) -> dict[str, float]:
        total = monthly * months + upfront
        monthly_equivalent = total / months
        savings = (
            ((payg_monthly - monthly_equivalent) / payg_monthly * 100) if payg_monthly > 0 else 0
        )
        return {
            "monthly_cost": monthly,
            "upfront_cost": upfront,
            "total_cost": total,
            "monthly_equivalent": monthly_equivalent,
            "savings_percent": max(0, savings),  # Negative savings should be 0
        }

    return {
        "product_id": product_id,
        "currency": currency,
        "quantity": quantity,
        "hours_per_month": hours_per_month,
        "payg": {
            "monthly_cost": payg_monthly,
            "hourly_rate": payg_hourly,
        },
        "reserved_12m": calc_reserved(
            item["reserved_12m"],
            item["reserved_upfront_12m"],
            12,
        ),
        "reserved_24m": calc_reserved(
            item["reserved_24m"],
            item["reserved_upfront_24m"],
            24,
        ),
        "reserved_36m": calc_reserved(
            item["reserved_36m"],
            item["reserved_upfront_36m"],
            36,
        ),
    }
