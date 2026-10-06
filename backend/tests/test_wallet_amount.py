from decimal import Decimal

import pytest

from app.services.wallet_service import parse_wallet_amount


@pytest.mark.parametrize(
    "raw, amount, currency",
    [
        ("250,00 ₴", "250.00", "UAH"),
        ("₴250.00", "250.00", "UAH"),
        ("1 250,50 ₴", "1250.50", "UAH"),
        ("1 250,50 ₴", "1250.50", "UAH"),   # неразривний пробіл
        ("1 250,50 ₴", "1250.50", "UAH"),   # вузький неразривний пробіл
        ("12,99 €", "12.99", "EUR"),
        ("$5.00", "5.00", "USD"),
        ("1,250.50 $", "1250.50", "USD"),
        ("1.250,50 €", "1250.50", "EUR"),
        ("250 грн", "250", "UAH"),
        ("99.9", "99.9", "UAH"),                      # без валюти → UAH
        ("-45,10 ₴", "45.10", "UAH"),
        ("  7 ₴ ", "7", "UAH"),
    ],
)
def test_parse_valid(raw, amount, currency):
    assert parse_wallet_amount(raw) == (Decimal(amount), currency)


@pytest.mark.parametrize("raw", ["", "   ", "₴", "abc", "0,00 ₴", "12 ₴ 34 ₴ x 5", None])
def test_parse_invalid(raw):
    with pytest.raises(ValueError):
        parse_wallet_amount(raw)
