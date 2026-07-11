"""Package release metadata retrieval.

The planner only needs, for every minor release series of a package, the
version and date of the first stable (non-prerelease, non-yanked) release in
that series. :class:`ReleaseFetcher` is the seam used to mock the registry in
tests; :class:`PyPIReleaseFetcher` is the production implementation backed by
the PyPI JSON API.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Protocol
from urllib.parse import quote

from packaging.utils import canonicalize_name
from packaging.version import InvalidVersion, Version

from . import __version__
from .errors import RegistryError

_USER_AGENT = f"dependency-support-policy/{__version__}"


@dataclass(frozen=True, order=True)
class SeriesRelease:
    """The first stable release of one minor release series of a package."""

    series: tuple[int, int]
    first_version: Version
    first_release_date: date


class ReleaseFetcher(Protocol):
    """Retrieves per-minor-series first-release information for a package."""

    def fetch_series(self, package: str) -> Sequence[SeriesRelease]:
        """Return all stable minor series of ``package``, sorted by series."""
        ...


def series_key(version: Version) -> tuple[int, int]:
    """Group a version into its (major, minor) series; ``2`` groups as ``(2, 0)``."""
    release = version.release
    return (release[0], release[1] if len(release) > 1 else 0)


def build_series(version_dates: Mapping[Version, date]) -> list[SeriesRelease]:
    """Collapse per-version release dates into per-minor-series first releases."""
    first_version: dict[tuple[int, int], Version] = {}
    first_date: dict[tuple[int, int], date] = {}
    for version, released in version_dates.items():
        key = series_key(version)
        if key not in first_version or version < first_version[key]:
            first_version[key] = version
        if key not in first_date or released < first_date[key]:
            first_date[key] = released
    return [
        SeriesRelease(series=key, first_version=first_version[key], first_release_date=first_date[key])
        for key in sorted(first_version)
    ]


def parse_pypi_payload(payload: Mapping[str, Any]) -> list[SeriesRelease]:
    """Extract stable minor series from a PyPI JSON API response.

    Prereleases and dev releases are ignored; a release counts only if it has
    at least one non-yanked file, and its date is the earliest upload time of
    those files.
    """
    releases = payload.get("releases")
    if not isinstance(releases, Mapping):
        raise RegistryError("malformed registry payload: missing 'releases' mapping")
    version_dates: dict[Version, date] = {}
    for version_text, files in releases.items():
        try:
            version = Version(version_text)
        except InvalidVersion:
            continue
        if version.is_prerelease or version.is_devrelease:
            continue
        upload_dates = []
        for file_info in files or []:
            if file_info.get("yanked", False):
                continue
            uploaded = file_info.get("upload_time_iso_8601")
            if not uploaded:
                continue
            upload_dates.append(datetime.fromisoformat(uploaded.replace("Z", "+00:00")).date())
        if upload_dates:
            version_dates[version] = min(upload_dates)
    return build_series(version_dates)


class PyPIReleaseFetcher:
    """Fetch release metadata from the PyPI JSON API, with retries and caching."""

    def __init__(
        self,
        base_url: str = "https://pypi.org/pypi",
        *,
        timeout: float = 30.0,
        retries: int = 3,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._retries = retries
        self._sleep = sleep
        self._cache: dict[str, list[SeriesRelease]] = {}

    def fetch_series(self, package: str) -> Sequence[SeriesRelease]:
        name = canonicalize_name(package)
        if name not in self._cache:
            self._cache[name] = parse_pypi_payload(self._fetch_payload(name))
        return self._cache[name]

    def _fetch_payload(self, name: str) -> dict[str, Any]:
        url = f"{self._base_url}/{quote(name)}/json"
        request = urllib.request.Request(  # noqa: S310 - fixed https base URL
            url,
            headers={"User-Agent": _USER_AGENT, "Accept": "application/json"},
        )
        last_error: Exception | None = None
        for attempt in range(self._retries):
            try:
                with urllib.request.urlopen(request, timeout=self._timeout) as response:  # noqa: S310
                    payload = json.loads(response.read().decode("utf-8"))
                    if not isinstance(payload, dict):
                        raise RegistryError(f"malformed registry response for {name!r}")
                    return payload
            except urllib.error.HTTPError as exc:
                if exc.code == 404:  # noqa: PLR2004 - HTTP status code
                    raise RegistryError(f"package {name!r} not found on the registry") from exc
                last_error = exc
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
                last_error = exc
            if attempt < self._retries - 1:
                self._sleep(2.0**attempt)
        raise RegistryError(f"failed to fetch release metadata for {name!r}: {last_error}") from last_error
