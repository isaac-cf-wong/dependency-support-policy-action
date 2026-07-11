"""Build and apply change plans: the orchestration layer.

``build_plan`` is pure (no file writes); ``apply_plan`` performs the edits,
optionally regenerates uv.lock, and rolls everything back if that fails.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from tomlkit import TOMLDocument

from .config import LockMode, RunConfig
from .errors import PolicyError, RegistryError
from .lockfile import regenerate_lockfile
from .policies import compute_floor, get_policy
from .pyproject_edit import (
    DependencyItem,
    dump_document,
    get_requires_python,
    iter_dependency_items,
    set_requires_python,
    write_text_atomic,
)
from .python_releases import python_series, table_may_be_stale
from .registry import ReleaseFetcher, SeriesRelease
from .requirements import (
    RewriteStatus,
    requirement_name,
    rewrite_requirement_lower_bound,
    rewrite_specifier_lower_bound,
)


@dataclass(frozen=True)
class DependencyChange:
    """A dependency whose lower bound the policy raises."""

    group: str
    name: str
    old_requirement: str
    new_requirement: str
    old_floor: str | None
    new_floor: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "group": self.group,
            "name": self.name,
            "old_requirement": self.old_requirement,
            "new_requirement": self.new_requirement,
            "old_floor": self.old_floor,
            "new_floor": self.new_floor,
        }


@dataclass(frozen=True)
class SkippedDependency:
    """A dependency the policy could not (or should not) rewrite."""

    group: str
    name: str | None
    requirement: str
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {"group": self.group, "name": self.name, "requirement": self.requirement, "reason": self.reason}


@dataclass(frozen=True)
class PythonFloorChange:
    """A change to ``requires-python``."""

    old_requires_python: str
    new_requires_python: str
    old_floor: str | None
    new_floor: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "old_requires_python": self.old_requires_python,
            "new_requires_python": self.new_requires_python,
            "old_floor": self.old_floor,
            "new_floor": self.new_floor,
        }


@dataclass
class ChangePlan:
    """Everything one evaluation decided, machine-readable."""

    reference_date: date
    policy: str
    dependency_changes: list[DependencyChange] = field(default_factory=list)
    skipped: list[SkippedDependency] = field(default_factory=list)
    python_change: PythonFloorChange | None = None
    notes: list[str] = field(default_factory=list)
    _item_updates: list[tuple[DependencyItem, str]] = field(default_factory=list, repr=False)

    @property
    def changed(self) -> bool:
        return bool(self.dependency_changes) or self.python_change is not None

    def to_dict(self) -> dict[str, Any]:
        return {
            "reference_date": self.reference_date.isoformat(),
            "policy": self.policy,
            "changed": self.changed,
            "dependency_changes": [change.to_dict() for change in self.dependency_changes],
            "python_change": self.python_change.to_dict() if self.python_change else None,
            "skipped": [skip.to_dict() for skip in self.skipped],
            "notes": list(self.notes),
        }


def build_plan(document: TOMLDocument, config: RunConfig, fetcher: ReleaseFetcher) -> ChangePlan:
    """Evaluate the policy against ``document`` and return the change plan."""
    policy = get_policy(config.policy_name)
    windows = policy.windows()
    package_months_default = config.package_support_months or windows.package_months
    python_months = config.python_support_months or windows.python_months
    plan = ChangePlan(reference_date=config.reference_date, policy=policy.name)

    series_cache: dict[str, list[SeriesRelease]] = {}
    for item in iter_dependency_items(document, config.groups):
        name = requirement_name(item.text)
        if name is None:
            plan.skipped.append(
                SkippedDependency(group=item.group, name=None, requirement=item.text, reason="unparsable requirement")
            )
            continue
        if config.include is not None and name not in config.include:
            continue
        if name in config.exclude:
            continue
        if name not in series_cache:
            try:
                series_cache[name] = list(fetcher.fetch_series(name))
            except RegistryError as exc:
                raise RegistryError(f"failed to resolve releases for dependency {name!r}: {exc}") from exc
        months = config.package_overrides.get(name, package_months_default)
        try:
            floor = compute_floor(series_cache[name], config.reference_date, months)
        except PolicyError as exc:
            plan.skipped.append(SkippedDependency(group=item.group, name=name, requirement=item.text, reason=str(exc)))
            continue
        result = rewrite_requirement_lower_bound(item.text, floor)
        if result.status is RewriteStatus.UPDATED:
            plan.dependency_changes.append(
                DependencyChange(
                    group=item.group,
                    name=name,
                    old_requirement=item.text,
                    new_requirement=result.text,
                    old_floor=str(result.old_floor) if result.old_floor else None,
                    new_floor=str(floor),
                )
            )
            plan._item_updates.append((item, result.text))
        elif result.status is RewriteStatus.SKIPPED:
            plan.skipped.append(
                SkippedDependency(group=item.group, name=name, requirement=item.text, reason=result.reason or "skipped")
            )

    if config.manage_python:
        _plan_python_floor(document, config, python_months, plan)

    return plan


def _plan_python_floor(document: TOMLDocument, config: RunConfig, python_months: int, plan: ChangePlan) -> None:
    requires_python = get_requires_python(document)
    if requires_python is None:
        plan.notes.append("project.requires-python is absent; Python floor not managed")
        return
    if table_may_be_stale(config.reference_date, config.python_releases):
        plan.notes.append(
            "the built-in CPython release table may be missing recent series; "
            "configure [tool.dependency-support-policy.python-releases] to extend it"
        )
    floor = compute_floor(python_series(config.python_releases), config.reference_date, python_months)
    result = rewrite_specifier_lower_bound(requires_python, floor)
    if result.status is RewriteStatus.UPDATED:
        plan.python_change = PythonFloorChange(
            old_requires_python=requires_python,
            new_requires_python=result.text,
            old_floor=str(result.old_floor) if result.old_floor else None,
            new_floor=str(floor),
        )
    elif result.status is RewriteStatus.SKIPPED:
        plan.notes.append(f"requires-python not updated: {result.reason}")


@dataclass(frozen=True)
class ApplyResult:
    """Files touched when a plan was applied."""

    pyproject_changed: bool
    lockfile_changed: bool

    @property
    def changed_files(self) -> list[str]:
        files = []
        if self.pyproject_changed:
            files.append("pyproject.toml")
        if self.lockfile_changed:
            files.append("uv.lock")
        return files


def apply_plan(document: TOMLDocument, plan: ChangePlan, config: RunConfig) -> ApplyResult:
    """Write the planned edits to disk, regenerating uv.lock if configured.

    If lockfile regeneration fails, both pyproject.toml and uv.lock are
    restored to their prior contents before the error propagates.
    """
    if not plan.changed:
        return ApplyResult(pyproject_changed=False, lockfile_changed=False)

    for item, new_text in plan._item_updates:
        item.set_text(new_text)
    if plan.python_change is not None:
        set_requires_python(document, plan.python_change.new_requires_python)

    pyproject_path = config.pyproject
    project_dir = pyproject_path.parent
    lock_path = project_dir / "uv.lock"

    pyproject_before = pyproject_path.read_bytes()
    lock_before = lock_path.read_bytes() if lock_path.exists() else None

    write_text_atomic(pyproject_path, dump_document(document))

    lock_mode = config.lock
    if lock_mode is not LockMode.OFF and lock_before is None:
        plan.notes.append("uv.lock not found; lockfile regeneration skipped")
        lock_mode = LockMode.OFF

    try:
        lockfile_changed = regenerate_lockfile(project_dir, lock_mode)
    except Exception:
        write_text_atomic(pyproject_path, pyproject_before.decode("utf-8"))
        if lock_before is not None:
            lock_path.write_bytes(lock_before)
        raise
    return ApplyResult(pyproject_changed=True, lockfile_changed=lockfile_changed)
