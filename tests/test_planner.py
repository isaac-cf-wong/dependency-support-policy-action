"""Tests for plan building and application (with a fake registry)."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest
import tomlkit

from dependency_support_policy_action import planner
from dependency_support_policy_action.config import LockMode, RunConfig
from dependency_support_policy_action.errors import LockfileError, RegistryError
from dependency_support_policy_action.planner import apply_plan, build_plan
from dependency_support_policy_action.pyproject_edit import load_document
from tests.conftest import NUMPY_SERIES, FakeFetcher, sr

REFERENCE = date(2025, 1, 1)

PYPROJECT = """\
[project]
name = "demo"
version = "0.1.0"
requires-python = ">=3.9"
dependencies = [
  "numpy>=1.21",  # array comment survives
  "scipy>=1.9",
  "oldlib==0.5",
]

[project.optional-dependencies]
plot = ["matplotlib>=3.5"]

[dependency-groups]
dev = ["pytest>=7.0"]
"""


def make_fetcher() -> FakeFetcher:
    return FakeFetcher(
        packages={
            "numpy": list(NUMPY_SERIES),
            "scipy": [sr("1.9.0", "2022-07-29"), sr("1.11.0", "2023-06-25"), sr("1.14.0", "2024-06-24")],
            "oldlib": [sr("0.5", "2020-01-01"), sr("0.6", "2021-01-01")],
            "matplotlib": [sr("3.5.0", "2021-11-16"), sr("3.8.0", "2023-09-15")],
            "pytest": [sr("7.0.0", "2022-02-03"), sr("8.0.0", "2024-01-27")],
        }
    )


def config(**kwargs: object) -> RunConfig:
    defaults: dict = {"pyproject": Path("pyproject.toml"), "reference_date": REFERENCE}
    defaults.update(kwargs)
    return RunConfig(**defaults)  # type: ignore[arg-type]


class TestBuildPlan:
    def test_project_dependencies_planned(self) -> None:
        document = tomlkit.parse(PYPROJECT)
        plan = build_plan(document, config(), make_fetcher())
        assert plan.changed
        changes = {change.name: change for change in plan.dependency_changes}
        assert changes["numpy"].new_requirement == "numpy>=1.25.0"
        assert changes["scipy"].new_requirement == "scipy>=1.11.0"
        assert changes["numpy"].old_floor == "1.21"
        # pinned dependency is reported, not rewritten
        assert [skip.name for skip in plan.skipped] == ["oldlib"]
        assert "pinned" in plan.skipped[0].reason
        # python floor moves from 3.9 to 3.11 (36-month window)
        assert plan.python_change is not None
        assert plan.python_change.new_requires_python == ">=3.11"
        # optional/dev groups untouched by default
        assert {change.group for change in plan.dependency_changes} == {"project"}

    def test_group_selection(self) -> None:
        document = tomlkit.parse(PYPROJECT)
        plan = build_plan(document, config(groups=("optional:plot", "group:dev")), make_fetcher())
        assert {change.name for change in plan.dependency_changes} == {"matplotlib", "pytest"}

    def test_include_and_exclude(self) -> None:
        document = tomlkit.parse(PYPROJECT)
        plan = build_plan(document, config(include=frozenset({"numpy"})), make_fetcher())
        assert [change.name for change in plan.dependency_changes] == ["numpy"]
        plan = build_plan(document, config(exclude=frozenset({"numpy"})), make_fetcher())
        assert "numpy" not in {change.name for change in plan.dependency_changes}

    def test_per_package_window_override(self) -> None:
        document = tomlkit.parse(PYPROJECT)
        plan = build_plan(document, config(package_overrides={"numpy": 48}), make_fetcher())
        changes = {change.name: change for change in plan.dependency_changes}
        # 48-month window reaches back to the 1.24 series; 1.21 floor still raised
        assert changes["numpy"].new_floor == "1.24.0"

    def test_python_window_override(self) -> None:
        document = tomlkit.parse(PYPROJECT)
        plan = build_plan(document, config(python_support_months=50), make_fetcher())
        assert plan.python_change is not None
        assert plan.python_change.new_floor == "3.10"

    def test_manage_python_disabled(self) -> None:
        document = tomlkit.parse(PYPROJECT)
        plan = build_plan(document, config(manage_python=False), make_fetcher())
        assert plan.python_change is None

    def test_missing_requires_python_noted(self) -> None:
        document = tomlkit.parse('[project]\nname = "demo"\ndependencies = []\n')
        plan = build_plan(document, config(), make_fetcher())
        assert plan.python_change is None
        assert any("requires-python is absent" in note for note in plan.notes)

    def test_stale_python_table_noted(self) -> None:
        document = tomlkit.parse(PYPROJECT)
        plan = build_plan(document, config(reference_date=date(2027, 6, 1)), make_fetcher())
        assert any("release table" in note for note in plan.notes)

    def test_registry_failure_aborts(self) -> None:
        document = tomlkit.parse(PYPROJECT)
        fetcher = make_fetcher()
        del fetcher.packages["scipy"]
        with pytest.raises(RegistryError, match="scipy"):
            build_plan(document, config(), fetcher)

    def test_metadata_fetched_once_per_package(self) -> None:
        document = tomlkit.parse(
            '[project]\nname = "demo"\ndependencies = ["numpy>=1.21", \'numpy>=1.21; python_version < "3.11"\']\n'
        )
        fetcher = make_fetcher()
        plan = build_plan(document, config(), fetcher)
        assert fetcher.calls.count("numpy") == 1
        assert len(plan.dependency_changes) == 2

    def test_package_without_stable_releases_skipped(self) -> None:
        document = tomlkit.parse('[project]\nname = "demo"\ndependencies = ["futurelib"]\n')
        fetcher = FakeFetcher(packages={"futurelib": [sr("1.0", "2026-01-01")]})
        plan = build_plan(document, config(), fetcher)
        assert not plan.dependency_changes
        assert "no stable releases" in plan.skipped[0].reason

    def test_unparsable_requirement_skipped(self) -> None:
        document = tomlkit.parse('[project]\nname = "demo"\ndependencies = ["!!! nope !!!"]\n')
        plan = build_plan(document, config(), make_fetcher())
        assert plan.skipped[0].name is None
        assert plan.skipped[0].reason == "unparsable requirement"

    def test_compliant_project_produces_empty_plan(self) -> None:
        document = tomlkit.parse(
            '[project]\nname = "demo"\nrequires-python = ">=3.12"\ndependencies = ["numpy>=2.1"]\n'
        )
        plan = build_plan(document, config(), make_fetcher())
        assert not plan.changed
        assert plan.dependency_changes == []
        assert plan.python_change is None

    def test_plan_serializes_to_json(self) -> None:
        document = tomlkit.parse(PYPROJECT)
        plan = build_plan(document, config(), make_fetcher())
        payload = json.loads(json.dumps(plan.to_dict()))
        assert payload["changed"] is True
        assert payload["policy"] == "spec0"
        assert payload["reference_date"] == "2025-01-01"
        assert {"group", "name", "old_requirement", "new_requirement", "old_floor", "new_floor"} == set(
            payload["dependency_changes"][0]
        )
        assert payload["python_change"]["new_floor"] == "3.11"


class TestApplyPlan:
    def _write_project(self, tmp_path: Path, content: str = PYPROJECT) -> Path:
        path = tmp_path / "pyproject.toml"
        path.write_text(content, encoding="utf-8")
        return path

    def test_apply_writes_expected_content(self, tmp_path: Path) -> None:
        path = self._write_project(tmp_path)
        document = load_document(path)
        run_config = config(pyproject=path)
        plan = build_plan(document, run_config, make_fetcher())
        result = apply_plan(document, plan, run_config)
        assert result.pyproject_changed
        assert result.changed_files == ["pyproject.toml"]
        content = path.read_text(encoding="utf-8")
        expected = (
            PYPROJECT.replace('"numpy>=1.21",  #', '"numpy>=1.25.0",  #')
            .replace('"scipy>=1.9"', '"scipy>=1.11.0"')
            .replace('">=3.9"', '">=3.11"')
        )
        assert content == expected

    def test_noop_plan_touches_nothing(self, tmp_path: Path) -> None:
        content = '[project]\nname = "demo"\nrequires-python = ">=3.12"\ndependencies = ["numpy>=2.1"]\n'
        path = self._write_project(tmp_path, content)
        document = load_document(path)
        run_config = config(pyproject=path, lock=LockMode.MINIMAL)
        plan = build_plan(document, run_config, make_fetcher())
        before = path.stat().st_mtime_ns
        result = apply_plan(document, plan, run_config)
        assert not result.pyproject_changed
        assert not result.lockfile_changed
        assert path.stat().st_mtime_ns == before
        assert path.read_text(encoding="utf-8") == content

    def test_lock_skipped_when_lockfile_missing(self, tmp_path: Path) -> None:
        path = self._write_project(tmp_path)
        document = load_document(path)
        run_config = config(pyproject=path, lock=LockMode.MINIMAL)
        plan = build_plan(document, run_config, make_fetcher())
        result = apply_plan(document, plan, run_config)
        assert result.pyproject_changed
        assert not result.lockfile_changed
        assert any("uv.lock not found" in note for note in plan.notes)

    def test_lockfile_regenerated(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        path = self._write_project(tmp_path)
        (tmp_path / "uv.lock").write_text("old lock\n", encoding="utf-8")
        calls: list[tuple[Path, LockMode]] = []

        def fake_regenerate(project_dir: Path, mode: LockMode, **kwargs: object) -> bool:
            calls.append((project_dir, mode))
            return True

        monkeypatch.setattr(planner, "regenerate_lockfile", fake_regenerate)
        document = load_document(path)
        run_config = config(pyproject=path, lock=LockMode.MINIMAL)
        plan = build_plan(document, run_config, make_fetcher())
        result = apply_plan(document, plan, run_config)
        assert result.lockfile_changed
        assert result.changed_files == ["pyproject.toml", "uv.lock"]
        assert calls == [(tmp_path, LockMode.MINIMAL)]

    def test_rollback_on_lock_failure(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        path = self._write_project(tmp_path)
        lock_path = tmp_path / "uv.lock"
        lock_path.write_text("old lock\n", encoding="utf-8")

        def failing_regenerate(project_dir: Path, mode: LockMode, **kwargs: object) -> bool:
            lock_path.write_text("half-written garbage\n", encoding="utf-8")
            raise LockfileError("resolution failed")

        monkeypatch.setattr(planner, "regenerate_lockfile", failing_regenerate)
        document = load_document(path)
        run_config = config(pyproject=path, lock=LockMode.MINIMAL)
        plan = build_plan(document, run_config, make_fetcher())
        with pytest.raises(LockfileError, match="resolution failed"):
            apply_plan(document, plan, run_config)
        assert path.read_text(encoding="utf-8") == PYPROJECT
        assert lock_path.read_text(encoding="utf-8") == "old lock\n"
