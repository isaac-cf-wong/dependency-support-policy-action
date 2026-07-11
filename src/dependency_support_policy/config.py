"""Run configuration: defaults, the pyproject tool table, and CLI overrides."""

from __future__ import annotations

import datetime as dt
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from packaging.utils import NormalizedName, canonicalize_name

from .dates import parse_iso_date
from .errors import ConfigError

TOOL_TABLE = "dependency-support-policy"

_PYTHON_SERIES_RE = re.compile(r"^(\d+)\.(\d+)$")


class LockMode(Enum):
    """How to treat uv.lock after pyproject.toml changes."""

    OFF = "off"
    MINIMAL = "minimal"
    UPGRADE = "upgrade"


@dataclass(frozen=True)
class RunConfig:
    """Fully resolved configuration for one evaluation run."""

    pyproject: Path
    reference_date: dt.date
    policy_name: str = "spec0"
    python_support_months: int | None = None
    package_support_months: int | None = None
    package_overrides: Mapping[NormalizedName, int] = field(default_factory=dict)
    include: frozenset[NormalizedName] | None = None
    exclude: frozenset[NormalizedName] = frozenset()
    groups: tuple[str, ...] = ("project",)
    manage_python: bool = True
    lock: LockMode = LockMode.OFF
    python_releases: Mapping[tuple[int, int], dt.date] = field(default_factory=dict)


def _require(value: Any, expected: type, key: str) -> Any:
    if expected is int and isinstance(value, bool):
        raise ConfigError(f"invalid value for {key!r}: expected {expected.__name__}, got bool")
    if not isinstance(value, expected):
        raise ConfigError(f"invalid value for {key!r}: expected {expected.__name__}, got {type(value).__name__}")
    return value


def _positive_months(value: Any, key: str) -> int:
    months = int(_require(value, int, key))
    if months <= 0:
        raise ConfigError(f"invalid value for {key!r}: months must be positive")
    return months


def _name_list(value: Any, key: str) -> frozenset[NormalizedName]:
    if not isinstance(value, (list, tuple)):
        raise ConfigError(f"invalid value for {key!r}: expected an array of package names")
    return frozenset(canonicalize_name(_require(item, str, key)) for item in value)


def _parse_python_releases(value: Any, key: str) -> dict[tuple[int, int], dt.date]:
    if not isinstance(value, Mapping):
        raise ConfigError(f"invalid value for {key!r}: expected a table of '<major>.<minor>' = date")
    releases: dict[tuple[int, int], dt.date] = {}
    for series_text, raw_date in value.items():
        match = _PYTHON_SERIES_RE.match(str(series_text))
        if match is None:
            raise ConfigError(f"invalid Python series {series_text!r} in {key!r}: expected '<major>.<minor>'")
        if isinstance(raw_date, dt.date) and not isinstance(raw_date, dt.datetime):
            released = raw_date
        elif isinstance(raw_date, str):
            released = parse_iso_date(raw_date)
        else:
            raise ConfigError(f"invalid release date for {series_text!r} in {key!r}: expected a date")
        releases[(int(match.group(1)), int(match.group(2)))] = released
    return releases


def _parse_lock_mode(value: Any, key: str) -> LockMode:
    text = _require(value, str, key)
    try:
        return LockMode(text)
    except ValueError:
        options = ", ".join(mode.value for mode in LockMode)
        raise ConfigError(f"invalid value for {key!r}: expected one of {options}") from None


def parse_package_overrides(pairs: Mapping[str, Any]) -> dict[NormalizedName, int]:
    """Parse a ``name -> months`` mapping, canonicalizing names."""
    overrides: dict[NormalizedName, int] = {}
    for name, months in pairs.items():
        overrides[canonicalize_name(name)] = _positive_months(months, f"package-support.{name}")
    return overrides


def load_config(
    pyproject: Path,
    document: Mapping[str, Any],
    reference_date: dt.date,
    cli_overrides: Mapping[str, Any] | None = None,
) -> RunConfig:
    """Merge tool-table settings with CLI overrides (CLI wins) into a RunConfig.

    ``cli_overrides`` keys mirror RunConfig field names; only keys with
    non-None values participate.
    """
    overrides = {key: value for key, value in (cli_overrides or {}).items() if value is not None}
    tool = document.get("tool", {})
    table = tool.get(TOOL_TABLE, {}) if isinstance(tool, Mapping) else {}
    if not isinstance(table, Mapping):
        raise ConfigError(f"[tool.{TOOL_TABLE}] must be a table")
    known_keys = {
        "policy",
        "python-support-months",
        "package-support-months",
        "package-support",
        "include",
        "exclude",
        "groups",
        "manage-python",
        "lock",
        "python-releases",
    }
    unknown = sorted(set(table) - known_keys)
    if unknown:
        raise ConfigError(f"unknown key(s) in [tool.{TOOL_TABLE}]: {', '.join(unknown)}")

    def setting(cli_key: str, table_key: str) -> Any:
        if cli_key in overrides:
            return overrides[cli_key]
        return table.get(table_key)

    policy_name = setting("policy_name", "policy")
    python_months = setting("python_support_months", "python-support-months")
    package_months = setting("package_support_months", "package-support-months")
    package_support = setting("package_overrides", "package-support")
    include = setting("include", "include")
    exclude = setting("exclude", "exclude")
    groups = setting("groups", "groups")
    manage_python = setting("manage_python", "manage-python")
    lock = setting("lock", "lock")
    python_releases = table.get("python-releases")

    if groups is not None:
        groups_tuple = tuple(_require(item, str, "groups") for item in _require_list(groups, "groups"))
        if not groups_tuple:
            raise ConfigError("'groups' must not be empty")
    else:
        groups_tuple = ("project",)

    return RunConfig(
        pyproject=pyproject,
        reference_date=reference_date,
        policy_name=_require(policy_name, str, "policy") if policy_name is not None else "spec0",
        python_support_months=(
            _positive_months(python_months, "python-support-months") if python_months is not None else None
        ),
        package_support_months=(
            _positive_months(package_months, "package-support-months") if package_months is not None else None
        ),
        package_overrides=(
            parse_package_overrides(_require_mapping(package_support, "package-support"))
            if package_support is not None
            else {}
        ),
        include=_name_list(include, "include") if include is not None else None,
        exclude=_name_list(exclude, "exclude") if exclude is not None else frozenset(),
        groups=groups_tuple,
        manage_python=bool(_require(manage_python, bool, "manage-python")) if manage_python is not None else True,
        lock=_parse_lock_mode(lock, "lock") if lock is not None else LockMode.OFF,
        python_releases=_parse_python_releases(python_releases, "python-releases")
        if python_releases is not None
        else {},
    )


def _require_list(value: Any, key: str) -> list[Any]:
    if not isinstance(value, (list, tuple)):
        raise ConfigError(f"invalid value for {key!r}: expected an array")
    return list(value)


def _require_mapping(value: Any, key: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ConfigError(f"invalid value for {key!r}: expected a table")
    return value
