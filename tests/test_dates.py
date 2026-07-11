"""Tests for calendar arithmetic."""

from __future__ import annotations

from datetime import date

import pytest

from dependency_support_policy_action.dates import months_before, parse_iso_date
from dependency_support_policy_action.errors import ConfigError


class TestMonthsBefore:
    def test_same_day_previous_years(self) -> None:
        assert months_before(date(2025, 1, 1), 24) == date(2023, 1, 1)

    def test_zero_months(self) -> None:
        assert months_before(date(2025, 6, 15), 0) == date(2025, 6, 15)

    def test_year_wrap(self) -> None:
        assert months_before(date(2025, 1, 15), 3) == date(2024, 10, 15)

    def test_clamps_to_leap_february(self) -> None:
        assert months_before(date(2024, 3, 31), 1) == date(2024, 2, 29)

    def test_clamps_to_regular_february(self) -> None:
        assert months_before(date(2023, 3, 31), 1) == date(2023, 2, 28)

    def test_clamps_short_month(self) -> None:
        assert months_before(date(2025, 7, 31), 1) == date(2025, 6, 30)

    def test_multi_year_window(self) -> None:
        assert months_before(date(2026, 7, 11), 36) == date(2023, 7, 11)

    def test_negative_months_rejected(self) -> None:
        with pytest.raises(ValueError, match="non-negative"):
            months_before(date(2025, 1, 1), -1)


class TestParseIsoDate:
    def test_valid(self) -> None:
        assert parse_iso_date("2025-01-31") == date(2025, 1, 31)

    @pytest.mark.parametrize("text", ["2025-13-01", "not-a-date", "2025/01/01"])
    def test_invalid(self, text: str) -> None:
        with pytest.raises(ConfigError, match="expected YYYY-MM-DD"):
            parse_iso_date(text)
