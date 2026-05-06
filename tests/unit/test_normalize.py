"""Unit tests for normalize.py."""

from __future__ import annotations

from decimal import Decimal

import pytest

from otc_pricing_mcp.normalize import parse_price


class TestParsePrice:
    """Tests for parse_price function."""

    def test_valid_price_eur(self) -> None:
        """Parse a valid EUR price string."""
        amount, currency = parse_price("0.051175 EUR")
        assert amount == Decimal("0.051175")
        assert currency == "EUR"

    def test_valid_price_chf(self) -> None:
        """Parse a valid CHF price string."""
        amount, currency = parse_price("23.150000 CHF")
        assert amount == Decimal("23.150000")
        assert currency == "CHF"

    def test_zero_price(self) -> None:
        """Parse a zero price."""
        amount, currency = parse_price("0.000000 EUR")
        assert amount == Decimal("0")
        assert currency == "EUR"

    def test_large_price(self) -> None:
        """Parse a large price."""
        amount, currency = parse_price("1234.567890 EUR")
        assert amount == Decimal("1234.567890")
        assert currency == "EUR"

    def test_missing_currency(self) -> None:
        """Fail when currency is missing."""
        with pytest.raises(ValueError, match="Expected 'amount currency' format"):
            parse_price("0.051175")

    def test_missing_amount(self) -> None:
        """Fail when amount is missing."""
        with pytest.raises(ValueError, match="Expected 'amount currency' format"):
            parse_price("EUR")

    def test_invalid_amount(self) -> None:
        """Fail when amount is not a valid decimal."""
        with pytest.raises(ValueError, match="Could not parse amount"):
            parse_price("abc EUR")

    def test_extra_whitespace(self) -> None:
        """Handle extra whitespace."""
        amount, currency = parse_price("  0.051175   EUR  ")
        assert amount == Decimal("0.051175")
        assert currency == "EUR"

    def test_empty_string(self) -> None:
        """Fail on empty string."""
        with pytest.raises(ValueError):
            parse_price("")
