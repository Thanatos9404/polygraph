"""Human-friendly duration parsing and formatting."""

_UNITS = {"s": 1, "m": 60, "h": 3600}


def parse_duration(text: str) -> int:
    """Parse a duration such as '90s', '15m' or '2h' into seconds.

    A bare number is taken as seconds.
    """
    text = text.strip().lower()
    unit = text[-1]
    if unit.isdigit():
        return int(text)
    if unit not in _UNITS:
        raise ValueError(f"unknown unit {unit!r} in {text!r}")
    number = text[:-1].strip()
    if not number.isdigit():
        raise ValueError(f"invalid number {number!r} in {text!r}")
    return int(number) * _UNITS[unit]


def format_duration(seconds: int) -> str:
    """Format seconds as a compact string such as '1h5m' or '45s'."""
    if seconds < 0:
        raise ValueError("negative durations are not supported")
    hours, rem = divmod(int(seconds), 3600)
    minutes, secs = divmod(rem, 60)
    parts = []
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    if secs or not parts:
        parts.append(f"{secs}s")
    return "".join(parts)
