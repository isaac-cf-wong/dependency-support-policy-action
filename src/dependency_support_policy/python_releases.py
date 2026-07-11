"""CPython release history used to compute the Python support floor.

The table lists the initial (x.y.0) release date of each CPython minor
series. New series can be appended via configuration
(``[tool.dependency-support-policy.python-releases]``) without a new release
of this tool.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date, timedelta

from packaging.version import Version

from .registry import SeriesRelease

CPYTHON_RELEASES: Mapping[tuple[int, int], date] = {
    (3, 7): date(2018, 6, 27),
    (3, 8): date(2019, 10, 14),
    (3, 9): date(2020, 10, 5),
    (3, 10): date(2021, 10, 4),
    (3, 11): date(2022, 10, 24),
    (3, 12): date(2023, 10, 2),
    (3, 13): date(2024, 10, 7),
    (3, 14): date(2025, 10, 7),
}

# CPython releases annually; if the reference date is this far past the newest
# known release, the built-in table is probably missing a series.
_STALENESS_MARGIN = timedelta(days=430)


def python_series(extra: Mapping[tuple[int, int], date] | None = None) -> list[SeriesRelease]:
    """Return CPython minor series, merging configured extra releases."""
    merged = dict(CPYTHON_RELEASES)
    if extra:
        merged.update(extra)
    return [
        SeriesRelease(
            series=key,
            first_version=Version(f"{key[0]}.{key[1]}"),
            first_release_date=released,
        )
        for key, released in sorted(merged.items())
    ]


def table_may_be_stale(reference: date, extra: Mapping[tuple[int, int], date] | None = None) -> bool:
    """True if the reference date is far beyond the newest known CPython release."""
    merged = dict(CPYTHON_RELEASES)
    if extra:
        merged.update(extra)
    newest = max(merged.values())
    return reference > newest + _STALENESS_MARGIN
