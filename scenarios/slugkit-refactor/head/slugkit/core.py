"""URL slug generation."""

import re
import unicodedata

_NON_WORD = re.compile(r"[^\w]+")


def _ascii_fold(text):
    normalized = unicodedata.normalize("NFKD", text)
    return normalized.encode("ascii", "ignore").decode("ascii")


def slugify(text, separator="-", max_length=None, lowercase=True):
    """Turn arbitrary text into a URL slug.

    Words are split on whitespace and punctuation, folded to ASCII, and joined with
    ``separator``. When ``max_length`` is set the slug is cut to fit.
    """
    if text is None:
        raise TypeError("slugify() expected str, got None")
    text = _ascii_fold(str(text))
    if lowercase:
        text = text.lower()
    slug = _NON_WORD.sub(separator, text).strip(separator)
    if max_length is not None:
        slug = slug[:max_length].rstrip(separator)
    return slug


def unique_slug(text, existing, **kwargs):
    """Slugify ``text`` and add a numeric suffix until it is not in ``existing``."""
    base = slugify(text, **kwargs)
    if base not in existing:
        return base
    n = 2
    while f"{base}-{n}" in existing:
        n += 1
    return f"{base}-{n}"
