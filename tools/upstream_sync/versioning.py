"""Kodi-oriented numeric version comparison and downstream revision policy."""

import re
from functools import total_ordering


TOKEN = re.compile(r"[A-Za-z]+|[0-9]+")


def _tokens(value):
    return tuple(
        (0, int(token)) if token.isdigit() else (1, token.lower())
        for token in TOKEN.findall(value)
    )


@total_ordering
class KodiVersion:
    def __init__(self, value):
        self.value = str(value)
        base, separator, suffix = self.value.partition("~")
        if not base or any(not part.isdigit() for part in base.split(".")):
            raise ValueError("unsupported Kodi version: %r" % self.value)
        self.numeric = tuple(int(part) for part in base.split("."))
        self.prerelease = _tokens(suffix) if separator else None

    def _numeric_pair(self, other):
        width = max(len(self.numeric), len(other.numeric))
        return (
            self.numeric + (0,) * (width - len(self.numeric)),
            other.numeric + (0,) * (width - len(other.numeric)),
        )

    def __eq__(self, other):
        if not isinstance(other, KodiVersion):
            try:
                other = KodiVersion(other)
            except (TypeError, ValueError):
                return NotImplemented
        left, right = self._numeric_pair(other)
        return left == right and self.prerelease == other.prerelease

    def __lt__(self, other):
        if not isinstance(other, KodiVersion):
            other = KodiVersion(other)
        left, right = self._numeric_pair(other)
        if left != right:
            return left < right
        if self.prerelease is None:
            return False
        if other.prerelease is None:
            return True
        return self.prerelease < other.prerelease

    def __str__(self):
        return self.value


def next_downstream_version(upstream_version, current_version=None):
    """Return upstream.revision, resetting the revision on a new upstream."""

    upstream = KodiVersion(upstream_version)
    base = ".".join(str(part) for part in upstream.numeric)
    if current_version is None:
        return base + ".1"
    current = KodiVersion(current_version)
    if len(current.numeric) < len(upstream.numeric) + 1:
        return base + ".1"
    current_base = current.numeric[: len(upstream.numeric)]
    if current_base != upstream.numeric:
        return base + ".1"
    return base + "." + str(current.numeric[len(upstream.numeric)] + 1)


def require_strictly_newer(candidate, *published):
    parsed = KodiVersion(candidate)
    for existing in published:
        if existing is not None and parsed <= KodiVersion(existing):
            raise ValueError("%s is not newer than %s" % (candidate, existing))
    return candidate
