"""Version handling for third-party plugins.

Plugin authors publish whatever version strings they like, so everything here has
to cope with the strings found in the wild, not only well-formed releases.
"""

from packaging.specifiers import SpecifierSet
from packaging.version import parse


def sort_versions(versions):
    """Return plugin versions from oldest to newest."""
    return sorted(versions, key=parse)


def newest(versions):
    """Return the newest version string, or None for an empty list."""
    if not versions:
        return None
    return max(versions, key=parse)


def is_compatible(plugin_version, requirement):
    """True when ``plugin_version`` satisfies a requirement such as '>=1.2,<2'."""
    return parse(plugin_version) in SpecifierSet(requirement)
