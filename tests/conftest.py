"""Shared test helpers: fake registry fetcher and series builders."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from packaging.utils import canonicalize_name
from packaging.version import Version

from dependency_support_policy_action.errors import RegistryError
from dependency_support_policy_action.registry import SeriesRelease, series_key


def sr(version: str, released: str) -> SeriesRelease:
    """Build a SeriesRelease from a version string and ISO date."""
    parsed = Version(version)
    return SeriesRelease(
        series=series_key(parsed),
        first_version=parsed,
        first_release_date=date.fromisoformat(released),
    )


# numpy-like release history reused across tests
NUMPY_SERIES = [
    sr("1.24.0", "2022-12-18"),
    sr("1.25.0", "2023-06-17"),
    sr("1.26.0", "2023-09-16"),
    sr("2.0.0", "2024-06-16"),
    sr("2.1.0", "2024-08-18"),
]


@dataclass
class FakeFetcher:
    """In-memory ReleaseFetcher; unknown packages raise RegistryError."""

    packages: dict[str, list[SeriesRelease]] = field(default_factory=dict)
    calls: list[str] = field(default_factory=list)

    def fetch_series(self, package: str) -> list[SeriesRelease]:
        name = canonicalize_name(package)
        self.calls.append(name)
        if name not in self.packages:
            raise RegistryError(f"package {name!r} not found on the registry")
        return self.packages[name]
