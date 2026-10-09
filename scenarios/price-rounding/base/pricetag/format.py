"""Price formatting."""

import math

_SYMBOLS = {"USD": "$", "EUR": "€", "GBP": "£", "JPY": "¥"}
_MINOR_DIGITS = {"JPY": 0}


def _coerce(amount):
    value = float(amount)
    if not math.isfinite(value):
        raise ValueError("amount must be a finite number")
    return value


def format_price(amount, currency="USD"):
    """Format an amount for display, e.g. 1234.5 -> '$1,234.50'."""
    value = _coerce(amount)
    symbol = _SYMBOLS.get(currency, currency + " ")
    digits = _MINOR_DIGITS.get(currency, 2)
    rounded = round(value, digits)
    return f"{symbol}{rounded:,.{digits}f}"
