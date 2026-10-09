"""URL slug generation."""

import re
import unicodedata

_SEPARATORS = re.compile(r"[\s\-_./\\]+")

# Letters that Unicode normalization cannot decompose into ASCII.
_TRANSLIT = {
    "ß": "ss", "æ": "ae", "Æ": "AE", "ø": "o", "Ø": "O", "đ": "d", "Đ": "D",
    "ł": "l", "Ł": "L", "œ": "oe", "Œ": "OE", "þ": "th", "Þ": "Th",
}


def _ascii_fold(text):
    text = "".join(_TRANSLIT.get(ch, ch) for ch in text)
    normalized = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def slugify(text, separator="-", max_length=None, lowercase=True):
    """Turn arbitrary text into a URL slug.

    Words are split on whitespace and punctuation, folded to ASCII, and joined with
    ``separator``. When ``max_length`` is set the slug is cut at a word boundary.
    """
    if text is None:
        raise TypeError("slugify() expected str, got None")
    text = _ascii_fold(str(text))
    if lowercase:
        text = text.lower()

    words = []
    for chunk in _SEPARATORS.split(text):
        word = "".join(ch for ch in chunk if ch.isascii() and ch.isalnum())
        if word:
            words.append(word)

    if max_length is None:
        return separator.join(words)

    out = ""
    for word in words:
        candidate = word if not out else out + separator + word
        if len(candidate) > max_length:
            break
        out = candidate
    return out or (words[0][:max_length] if words else "")


def unique_slug(text, existing, **kwargs):
    """Slugify ``text`` and add a numeric suffix until it is not in ``existing``."""
    base = slugify(text, **kwargs)
    if base not in existing:
        return base
    n = 2
    while f"{base}-{n}" in existing:
        n += 1
    return f"{base}-{n}"
