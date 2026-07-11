"""Deterministic calendar arithmetic used by support-window calculations."""

from __future__ import annotations

import calendar
from datetime import date

from .errors import ConfigError


def months_before(reference: date, months: int) -> date:
    """Return the date ``months`` calendar months before ``reference``.

    The day of month is preserved, clamped to the length of the target month
    (e.g. 2024-03-31 minus one month is 2024-02-29).
    """
    if months < 0:
        raise ValueError("months must be non-negative")
    total = reference.year * 12 + reference.month - 1 - months
    year, month_index = divmod(total, 12)
    month = month_index + 1
    day = min(reference.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def parse_iso_date(text: str) -> date:
    """Parse a ``YYYY-MM-DD`` date, raising :class:`ConfigError` on bad input."""
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise ConfigError(f"invalid date {text!r}: expected YYYY-MM-DD") from exc
