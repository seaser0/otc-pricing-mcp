"""Estimation tools: estimate_monthly_cost, compare_billing_models."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from otc_pricing_mcp.client import OTCPricingClient
from otc_pricing_mcp.normalize import parse_price

# Reserved-tier identifiers and their term lengths (months).
_RESERVED_TIERS: tuple[tuple[str, int], ...] = (
    ("reserved_12m", 12),
    ("reserved_24m", 24),
    ("reserved_36m", 36),
)


def _tier_unavailable(monthly: Decimal, upfront: Decimal) -> bool:
    """Return True if a reserved tier is not offered for this product.

    The OTC price-calculator returns 0.0 for both the monthly (Rxx) and the
    upfront (RUxx) field when a term is not on offer for a given product —
    indistinguishable from a real price unless we treat that combination as
    'missing'. Documented in #7.
    """
    return monthly == 0 and upfront == 0


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
            'total_reserved_12m': float | None,   # None if any item lacks the tier
            'total_reserved_24m': float | None,
            'total_reserved_36m': float | None,
            'total_reserved_upfront_12m': float | None,
            'total_reserved_upfront_24m': float | None,
            'total_reserved_upfront_36m': float | None,
            'tiers_unavailable': [str, ...],      # tiers that are None at the total
            'currency': str,
            'items': [
                {
                    'id': str,
                    'quantity': float,
                    'hours_per_month': float,
                    'payg': float,
                    'reserved_12m': float | None,            # None if not offered
                    'reserved_24m': float | None,
                    'reserved_36m': float | None,
                    'reserved_upfront_12m': float | None,
                    'reserved_upfront_24m': float | None,
                    'reserved_upfront_36m': float | None,
                    'tiers_available': [str, ...],           # always includes 'payg'
                    'currency': str,
                },
                ...
            ]
        }

    A reserved tier (12m / 24m / 36m) is considered 'not offered' when both
    its monthly (Rxx) and upfront (RUxx) prices are 0.0 — see #7. The fields
    are nulled rather than reported as 0.0 so a 100% savings recommendation
    isn't synthesised on a non-existent tier.

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

    # Validate quantity / hours upfront so a fat-fingered LLM doesn't get back
    # a negative-cost "estimate" silently (#36).
    for idx, item in enumerate(items):
        if "quantity" in item and float(item["quantity"]) < 1:
            raise ValueError(f"items[{idx}].quantity must be >= 1 (got {item['quantity']})")
        if "hours_per_month" in item and float(item["hours_per_month"]) < 0:
            raise ValueError(
                f"items[{idx}].hours_per_month must be >= 0 (got {item['hours_per_month']})"
            )

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
    payg_total = Decimal("0")
    # Per-tier accumulators: sum of items that DO offer the tier; counter of
    # items that DON'T (so totals can be nulled when any item lacks the tier).
    tier_totals: dict[str, Decimal] = {tier: Decimal("0") for tier, _ in _RESERVED_TIERS}
    tier_upfront_totals: dict[str, Decimal] = {tier: Decimal("0") for tier, _ in _RESERVED_TIERS}
    tier_unavailable_count: dict[str, int] = {tier: 0 for tier, _ in _RESERVED_TIERS}
    n_priced_items = 0
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
            tier_amounts: dict[str, Decimal] = {}
            tier_upfront_amounts: dict[str, Decimal] = {}
            tier_amounts["reserved_12m"], _ = parse_price(product.get("R12", "0 EUR"))
            tier_amounts["reserved_24m"], _ = parse_price(product.get("R24", "0 EUR"))
            tier_amounts["reserved_36m"], _ = parse_price(product.get("R36", "0 EUR"))
            tier_upfront_amounts["reserved_12m"], _ = parse_price(product.get("RU12", "0 EUR"))
            tier_upfront_amounts["reserved_24m"], _ = parse_price(product.get("RU24", "0 EUR"))
            tier_upfront_amounts["reserved_36m"], _ = parse_price(product.get("RU36", "0 EUR"))
        except Exception:
            continue

        n_priced_items += 1
        payg_cost = payg_amount * hours * quantity
        payg_total += payg_cost

        item_record: dict[str, Any] = {
            "id": product_id,
            "quantity": float(quantity),
            "hours_per_month": float(hours),
            "payg": float(payg_cost),
            "currency": currency,
        }
        tiers_available_for_item: list[str] = ["payg"]

        for tier, _months in _RESERVED_TIERS:
            monthly_amt = tier_amounts[tier]
            upfront_amt = tier_upfront_amounts[tier]
            upfront_key = f"reserved_upfront_{tier.split('_')[1]}"

            if _tier_unavailable(monthly_amt, upfront_amt):
                item_record[tier] = None
                item_record[upfront_key] = None
                tier_unavailable_count[tier] += 1
            else:
                monthly_cost = monthly_amt * quantity
                upfront_cost = upfront_amt * quantity
                item_record[tier] = float(monthly_cost)
                item_record[upfront_key] = float(upfront_cost)
                tier_totals[tier] += monthly_cost
                tier_upfront_totals[tier] += upfront_cost
                tiers_available_for_item.append(tier)

        item_record["tiers_available"] = tiers_available_for_item
        item_results.append(item_record)

    # Track product IDs that the user asked for but the upstream catalog did
    # not return. Without this, an unknown id silently produces total_payg=0
    # (#31) — the same anti-pattern issues #4/#6 caught for query_pricing.
    requested_ids = [item["id"] for item in items if item.get("id")]
    unknown_product_ids = sorted({pid for pid in requested_ids if pid not in product_data})
    warnings = [f"Product '{pid}' not found in OTC catalog" for pid in unknown_product_ids]

    # A tier total is None when at least one priced item lacks that tier —
    # mixing apples and pears into a single 'total' would be misleading.
    result: dict[str, Any] = {
        "total_payg": float(payg_total),
        "currency": currency,
    }
    tiers_unavailable: list[str] = []
    for tier, _months in _RESERVED_TIERS:
        upfront_key = f"reserved_upfront_{tier.split('_')[1]}"
        if n_priced_items > 0 and tier_unavailable_count[tier] == 0:
            result[f"total_{tier}"] = float(tier_totals[tier])
            result[f"total_{upfront_key}"] = float(tier_upfront_totals[tier])
        else:
            result[f"total_{tier}"] = None
            result[f"total_{upfront_key}"] = None
            tiers_unavailable.append(tier)

    result["tiers_unavailable"] = tiers_unavailable
    result["unknown_product_ids"] = unknown_product_ids
    result["warnings"] = warnings
    result["items"] = item_results
    return result


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
            'quantity': float,
            'hours_per_month': float,
            'tiers_available': [str, ...],   # always includes 'payg'
            'payg': {
                'monthly_cost': float,
                'hourly_rate': float,
            },
            # Each reserved tier is either:
            #   {'available': False}                       (tier not offered)
            # or:
            #   {'available': True, 'monthly_cost': ..., 'upfront_cost': ...,
            #    'total_cost': ..., 'monthly_equivalent': ...,
            #    'savings_percent': ...}                   (tier is on offer)
            'reserved_12m': {...},
            'reserved_24m': {...},
            'reserved_36m': {...},
        }

    A reserved tier is treated as not offered when both Rxx and RUxx are 0.0
    in the upstream payload — without this distinction the tool was reporting
    100% savings on tiers that don't exist (#7).

    Examples:
        # Compare billing for single unit
        >>> compare_billing_models('OTC_S3M1_LI')

        # Compare for 2 units
        >>> compare_billing_models('OTC_S3M1_LI', quantity=2)
    """
    if quantity < 1:
        raise ValueError(f"quantity must be >= 1 (got {quantity})")
    if hours_per_month < 0:
        raise ValueError(f"hours_per_month must be >= 0 (got {hours_per_month})")

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
    payg_hourly = payg_monthly / hours_per_month if hours_per_month > 0 else 0.0

    def calc_reserved(monthly: float | None, upfront: float | None, months: int) -> dict[str, Any]:
        if monthly is None or upfront is None:
            return {"available": False}
        total = monthly * months + upfront
        monthly_equivalent = total / months
        # Report the true savings_percent (may be negative if reserved is more
        # expensive than PAYG at this usage level — see #32). The previous
        # max(0.0, ...) clamp hid the case where reserved is a bad fit.
        savings: float
        if payg_monthly > 0:
            savings = (payg_monthly - monthly_equivalent) / payg_monthly * 100
        else:
            savings = 0.0  # PAYG = 0 → savings ratio is undefined; report 0.
        return {
            "available": True,
            "monthly_cost": monthly,
            "upfront_cost": upfront,
            "total_cost": total,
            "monthly_equivalent": monthly_equivalent,
            "savings_percent": savings,
            "reserved_more_expensive_than_payg": savings < 0,
        }

    return {
        "product_id": product_id,
        "currency": currency,
        "quantity": quantity,
        "hours_per_month": hours_per_month,
        "tiers_available": list(item["tiers_available"]),
        "payg": {
            "monthly_cost": payg_monthly,
            "hourly_rate": payg_hourly,
        },
        "reserved_12m": calc_reserved(item["reserved_12m"], item["reserved_upfront_12m"], 12),
        "reserved_24m": calc_reserved(item["reserved_24m"], item["reserved_upfront_24m"], 24),
        "reserved_36m": calc_reserved(item["reserved_36m"], item["reserved_upfront_36m"], 36),
    }
