from timekit import format_duration, parse_duration


def test_units():
    assert parse_duration("90s") == 90
    assert parse_duration("15m") == 900
    assert parse_duration("2h") == 7200


def test_format():
    assert format_duration(3900) == "1h5m"
