"""Tests for PyPI payload parsing and the HTTP fetcher."""

from __future__ import annotations

import io
import json
import urllib.error
from datetime import date
from typing import Any, ClassVar

import pytest
from packaging.version import Version

from dependency_support_policy.errors import RegistryError
from dependency_support_policy.registry import (
    PyPIReleaseFetcher,
    build_series,
    parse_pypi_payload,
    series_key,
)


def _file(uploaded: str, yanked: bool = False) -> dict[str, Any]:
    return {"upload_time_iso_8601": uploaded, "yanked": yanked}


class TestSeriesKey:
    def test_major_minor(self) -> None:
        assert series_key(Version("1.24.3")) == (1, 24)

    def test_major_only(self) -> None:
        assert series_key(Version("2")) == (2, 0)


class TestBuildSeries:
    def test_first_version_and_earliest_date_per_series(self) -> None:
        series = build_series(
            {
                Version("1.24.1"): date(2022, 12, 1),
                Version("1.24.0"): date(2022, 12, 18),
                Version("1.25.0"): date(2023, 6, 17),
            }
        )
        assert [(s.series, str(s.first_version), s.first_release_date) for s in series] == [
            ((1, 24), "1.24.0", date(2022, 12, 1)),
            ((1, 25), "1.25.0", date(2023, 6, 17)),
        ]


class TestParsePyPIPayload:
    def test_full_payload(self) -> None:
        payload = {
            "releases": {
                "1.0.0": [_file("2023-01-01T10:00:00Z"), _file("2023-01-02T10:00:00Z")],
                "1.0.1": [_file("2023-02-01T10:00:00Z")],
                "1.1.0rc1": [_file("2023-05-01T10:00:00Z")],
                "1.1.0.dev0": [_file("2023-05-02T10:00:00Z")],
                "1.1.0": [_file("2023-06-01T10:00:00Z")],
                "1.2.0": [_file("2023-08-01T10:00:00Z", yanked=True)],
                "1.3.0": [_file("2023-09-01T10:00:00Z", yanked=True), _file("2023-09-02T10:00:00Z")],
                "1.4.0": [],
                "not-a-version": [_file("2023-10-01T10:00:00Z")],
                "2.0.0.post1": [_file("2024-01-01T10:00:00Z")],
            }
        }
        series = parse_pypi_payload(payload)
        assert [(s.series, str(s.first_version), s.first_release_date) for s in series] == [
            ((1, 0), "1.0.0", date(2023, 1, 1)),  # earliest upload of the earliest version
            ((1, 1), "1.1.0", date(2023, 6, 1)),  # prereleases and dev releases ignored
            ((1, 3), "1.3.0", date(2023, 9, 2)),  # yanked file ignored, non-yanked one counts
            ((2, 0), "2.0.0.post1", date(2024, 1, 1)),  # post releases are stable
        ]

    def test_missing_upload_time_ignored(self) -> None:
        payload = {"releases": {"1.0.0": [{"yanked": False}]}}
        assert parse_pypi_payload(payload) == []

    def test_malformed_payload(self) -> None:
        with pytest.raises(RegistryError, match="malformed registry payload"):
            parse_pypi_payload({"info": {}})


class _FakeResponse(io.BytesIO):
    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()


class TestPyPIReleaseFetcher:
    PAYLOAD: ClassVar[dict[str, Any]] = {"releases": {"1.0.0": [_file("2023-01-01T10:00:00Z")]}}

    def _fetcher(self, responses: list[Any], monkeypatch: pytest.MonkeyPatch) -> tuple[PyPIReleaseFetcher, list[str]]:
        urls: list[str] = []

        def fake_urlopen(request: Any, timeout: float = 0) -> _FakeResponse:
            urls.append(request.full_url)
            result = responses.pop(0)
            if isinstance(result, Exception):
                raise result
            return _FakeResponse(json.dumps(result).encode())

        monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
        return PyPIReleaseFetcher(sleep=lambda _: None), urls

    def test_success_and_cache(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fetcher, urls = self._fetcher([self.PAYLOAD], monkeypatch)
        first = fetcher.fetch_series("My_Package")
        second = fetcher.fetch_series("my-package")
        assert [str(s.first_version) for s in first] == ["1.0.0"]
        assert second == first
        assert urls == ["https://pypi.org/pypi/my-package/json"]

    def test_not_found_no_retry(self, monkeypatch: pytest.MonkeyPatch) -> None:
        error = urllib.error.HTTPError("url", 404, "Not Found", {}, None)  # type: ignore[arg-type]
        fetcher, urls = self._fetcher([error], monkeypatch)
        with pytest.raises(RegistryError, match="not found"):
            fetcher.fetch_series("missing")
        assert len(urls) == 1

    def test_transient_failure_retried(self, monkeypatch: pytest.MonkeyPatch) -> None:
        responses: list[Any] = [
            urllib.error.URLError("connection reset"),
            urllib.error.HTTPError("url", 503, "Unavailable", {}, None),  # type: ignore[arg-type]
            self.PAYLOAD,
        ]
        fetcher, urls = self._fetcher(responses, monkeypatch)
        series = fetcher.fetch_series("pkg")
        assert [str(s.first_version) for s in series] == ["1.0.0"]
        assert len(urls) == 3

    def test_persistent_failure(self, monkeypatch: pytest.MonkeyPatch) -> None:
        responses: list[Any] = [urllib.error.URLError("down")] * 3
        fetcher, urls = self._fetcher(responses, monkeypatch)
        with pytest.raises(RegistryError, match="failed to fetch release metadata"):
            fetcher.fetch_series("pkg")
        assert len(urls) == 3

    def test_non_dict_payload(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fetcher, _ = self._fetcher([["not", "a", "dict"]] * 3, monkeypatch)
        with pytest.raises(RegistryError):
            fetcher.fetch_series("pkg")
