"""Tests for the CPython release table."""

from __future__ import annotations

from datetime import date

from packaging.version import Version

from dependency_support_policy_action.python_releases import python_series, table_may_be_stale


class TestPythonSeries:
    def test_contains_known_series_sorted(self) -> None:
        series = python_series()
        keys = [s.series for s in series]
        assert keys == sorted(keys)
        by_key = {s.series: s for s in series}
        assert by_key[(3, 12)].first_version == Version("3.12")
        assert by_key[(3, 12)].first_release_date == date(2023, 10, 2)

    def test_extra_series_merged(self) -> None:
        series = python_series({(3, 15): date(2026, 10, 1)})
        by_key = {s.series: s for s in series}
        assert by_key[(3, 15)].first_release_date == date(2026, 10, 1)

    def test_extra_series_overrides_builtin(self) -> None:
        series = python_series({(3, 14): date(2025, 12, 1)})
        by_key = {s.series: s for s in series}
        assert by_key[(3, 14)].first_release_date == date(2025, 12, 1)


class TestStaleness:
    def test_fresh_reference(self) -> None:
        assert not table_may_be_stale(date(2026, 7, 11))

    def test_stale_reference(self) -> None:
        assert table_may_be_stale(date(2027, 6, 1))

    def test_extra_release_extends_freshness(self) -> None:
        assert not table_may_be_stale(date(2027, 6, 1), {(3, 15): date(2026, 10, 1)})
