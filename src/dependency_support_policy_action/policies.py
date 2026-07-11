"""Support-policy definitions and support-window floor calculations."""

from __future__ import annotations

import abc
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import ClassVar

from packaging.version import Version

from .dates import months_before
from .errors import ConfigError, PolicyError
from .registry import SeriesRelease


@dataclass(frozen=True)
class SupportWindows:
    """Default support windows (in calendar months) defined by a policy."""

    python_months: int
    package_months: int


class SupportPolicy(abc.ABC):
    """A named policy providing default support windows.

    Additional policies can be added by subclassing and registering in
    :data:`_POLICIES`.
    """

    name: ClassVar[str]
    description: ClassVar[str]

    @abc.abstractmethod
    def windows(self) -> SupportWindows:
        """Return the default support windows for this policy."""


class Spec0Policy(SupportPolicy):
    """Scientific Python SPEC 0: drop Python after 3 years, packages after 2."""

    name = "spec0"
    description = "Scientific Python SPEC 0 (36-month Python window, 24-month package window)"

    def windows(self) -> SupportWindows:
        return SupportWindows(python_months=36, package_months=24)


_POLICIES: dict[str, SupportPolicy] = {Spec0Policy.name: Spec0Policy()}


def available_policies() -> tuple[str, ...]:
    """Names of all registered policies."""
    return tuple(sorted(_POLICIES))


def get_policy(name: str) -> SupportPolicy:
    """Look up a policy by name, raising :class:`ConfigError` if unknown."""
    try:
        return _POLICIES[name]
    except KeyError:
        known = ", ".join(available_policies())
        raise ConfigError(f"unknown policy {name!r}; available policies: {known}") from None


def compute_floor(series: Sequence[SeriesRelease], reference: date, window_months: int) -> Version:
    """Return the minimum supported version under a rolling support window.

    A minor series is supported if its first stable release happened within
    ``window_months`` calendar months before ``reference`` (window boundary
    inclusive). The floor is the first version of the oldest supported series.
    If every series is older than the window, the newest series is the floor,
    so at least one release line is always supported.

    Series first released after ``reference`` are ignored so that evaluation
    with a historical reference date is reproducible.
    """
    released = [s for s in series if s.first_release_date <= reference]
    if not released:
        raise PolicyError(f"no stable releases on or before {reference.isoformat()}")
    cutoff = months_before(reference, window_months)
    eligible = [s for s in released if s.first_release_date >= cutoff]
    chosen = min(eligible, key=lambda s: s.series) if eligible else max(released, key=lambda s: s.series)
    return chosen.first_version
