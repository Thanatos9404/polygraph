"""Price formatting."""

import math
from decimal import ROUND_HALF_UP, Decimal, localcontext

_SYMBOLS = {"USD": "$", "EUR": "€", "GBP": "£", "JPY": "¥"}
_MINOR_DIGITS = {"JPY": 0}


def _coerce(amount):
    value = float(amount)
    if not math.isfinite(value):
        raise ValueError("amount must be a finite number")
    return value


def format_price(amount, currency="USD"):
    """Format an amount for display, e.g. 1234.5 -> '$1,234.50'.

    Halves round up to the currency's minor unit: 2.675 -> '$2.68'.
    """
    value = _coerce(amount)
    symbol = _SYMBOLS.get(currency, currency + " ")
    digits = _MINOR_DIGITS.get(currency, 2)
    with localcontext() as ctx:
        ctx.prec = 400
        rounded = Decimal(repr(value)).quantize(Decimal(1).scaleb(-digits), rounding=ROUND_HALF_UP)
    return f"{symbol}{rounded:,.{digits}f}"
