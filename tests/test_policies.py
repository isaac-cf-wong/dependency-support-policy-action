"""Tests for policy lookup and support-window floor calculations."""

from __future__ import annotations

from datetime import date

import pytest
from packaging.version import Version

from dependency_support_policy_action.errors import ConfigError, PolicyError
from dependency_support_policy_action.policies import available_policies, compute_floor, get_policy
from tests.conftest import NUMPY_SERIES, sr


class TestPolicyRegistry:
    def test_spec0_windows(self) -> None:
        windows = get_policy("spec0").windows()
        assert windows.python_months == 36
        assert windows.package_months == 24

    def test_spec0_available(self) -> None:
        assert "spec0" in available_policies()

    def test_unknown_policy(self) -> None:
        with pytest.raises(ConfigError, match="unknown policy 'nope'"):
            get_policy("nope")


class TestComputeFloor:
    def test_oldest_eligible_series_wins(self) -> None:
        floor = compute_floor(NUMPY_SERIES, date(2025, 1, 1), 24)
        assert floor == Version("1.25.0")

    def test_window_boundary_is_inclusive(self) -> None:
        series = [sr("1.0.0", "2022-12-31"), sr("1.1.0", "2023-01-01"), sr("1.2.0", "2024-01-01")]
        assert compute_floor(series, date(2025, 1, 1), 24) == Version("1.1.0")

    def test_release_one_day_before_cutoff_excluded(self) -> None:
        series = [sr("1.0.0", "2022-12-31"), sr("1.1.0", "2023-06-01")]
        assert compute_floor(series, date(2025, 1, 1), 24) == Version("1.1.0")

    def test_all_series_stale_falls_back_to_newest(self) -> None:
        series = [sr("1.0.0", "2019-01-01"), sr("1.1.0", "2020-01-01")]
        assert compute_floor(series, date(2025, 1, 1), 24) == Version("1.1.0")

    def test_series_released_after_reference_ignored(self) -> None:
        series = [sr("1.0.0", "2024-06-01"), sr("2.0.0", "2025-06-01")]
        assert compute_floor(series, date(2025, 1, 1), 24) == Version("1.0.0")

    def test_wider_window_lowers_floor(self) -> None:
        assert compute_floor(NUMPY_SERIES, date(2025, 1, 1), 48) == Version("1.24.0")

    def test_narrow_window_raises_floor(self) -> None:
        assert compute_floor(NUMPY_SERIES, date(2025, 1, 1), 6) == Version("2.1.0")

    def test_no_releases_before_reference(self) -> None:
        with pytest.raises(PolicyError, match="no stable releases"):
            compute_floor([sr("1.0.0", "2025-06-01")], date(2025, 1, 1), 24)

    def test_empty_series(self) -> None:
        with pytest.raises(PolicyError, match="no stable releases"):
            compute_floor([], date(2025, 1, 1), 24)
