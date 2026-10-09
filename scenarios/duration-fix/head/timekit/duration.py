"""Human-friendly duration parsing and formatting."""

import re

_UNITS = {"s": 1, "m": 60, "h": 3600}
_PART = re.compile(r"(\d+)\s*([a-z])")


def parse_duration(text: str) -> int:
    """Parse a duration such as '90s', '15m', '2h', '1h30m' or '2d' into seconds.

    A bare number is taken as seconds.
    """
    text = text.strip().lower()
    if not text:
        raise ValueError("empty duration")
    if text.isdigit():
        return int(text)
    parts = _PART.findall(text)
    if not parts:
        raise ValueError(f"invalid duration {text!r}")
    total = 0
    for number, unit in parts:
        if unit not in _UNITS:
            raise ValueError(f"unknown unit {unit!r} in {text!r}")
        total += int(number) * _UNITS[unit]
    return total


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
