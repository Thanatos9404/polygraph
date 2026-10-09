from pricetag import format_price


def test_usd():
    assert format_price(1234.5) == "$1,234.50"


def test_jpy():
    assert format_price(1200, "JPY") == "¥1,200"
