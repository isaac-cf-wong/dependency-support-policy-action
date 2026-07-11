"""Tests for the CLI: modes, exit codes, outputs, and error handling."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from dependency_support_policy_action import cli
from dependency_support_policy_action.cli import EXIT_DRIFT, EXIT_ERROR, EXIT_OK, main
from dependency_support_policy_action.errors import LockfileError
from tests.conftest import FakeFetcher
from tests.test_planner import PYPROJECT, make_fetcher

COMPLIANT = '[project]\nname = "demo"\nrequires-python = ">=3.12"\ndependencies = ["numpy>=2.1"]\n'


@pytest.fixture(autouse=True)
def no_github_output(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)


@pytest.fixture
def outdated_project(tmp_path: Path) -> Path:
    path = tmp_path / "pyproject.toml"
    path.write_text(PYPROJECT, encoding="utf-8")
    return path


@pytest.fixture
def compliant_project(tmp_path: Path) -> Path:
    path = tmp_path / "pyproject.toml"
    path.write_text(COMPLIANT, encoding="utf-8")
    return path


def run(mode: str, pyproject: Path, *extra: str, fetcher: FakeFetcher | None = None) -> int:
    argv = [mode, "--pyproject", str(pyproject), "--reference-date", "2025-01-01", *extra]
    return main(argv, fetcher=fetcher if fetcher is not None else make_fetcher())


class TestCheckMode:
    def test_compliant_exits_zero(self, compliant_project: Path, capsys: pytest.CaptureFixture[str]) -> None:
        assert run("check", compliant_project) == EXIT_OK
        assert "comply with the policy" in capsys.readouterr().out

    def test_drift_exits_one(self, outdated_project: Path, capsys: pytest.CaptureFixture[str]) -> None:
        assert run("check", outdated_project) == EXIT_DRIFT
        out = capsys.readouterr().out
        assert "'numpy>=1.21' -> 'numpy>=1.25.0'" in out
        assert "requires-python" in out

    def test_check_never_writes(self, outdated_project: Path) -> None:
        run("check", outdated_project)
        assert outdated_project.read_text(encoding="utf-8") == PYPROJECT

    def test_quiet_suppresses_summary(self, outdated_project: Path, capsys: pytest.CaptureFixture[str]) -> None:
        assert run("check", outdated_project, "--quiet") == EXIT_DRIFT
        assert capsys.readouterr().out == ""


class TestPlanMode:
    def test_prints_json_plan(self, outdated_project: Path, capsys: pytest.CaptureFixture[str]) -> None:
        assert run("plan", outdated_project) == EXIT_OK
        payload = json.loads(capsys.readouterr().out)
        assert payload["changed"] is True
        assert payload["python_change"]["new_requires_python"] == ">=3.11"
        assert outdated_project.read_text(encoding="utf-8") == PYPROJECT

    def test_output_json_file(self, outdated_project: Path, tmp_path: Path) -> None:
        target = tmp_path / "plan.json"
        assert run("plan", outdated_project, "--output-json", str(target)) == EXIT_OK
        assert json.loads(target.read_text(encoding="utf-8"))["changed"] is True


class TestUpdateMode:
    def test_applies_changes(self, outdated_project: Path, capsys: pytest.CaptureFixture[str]) -> None:
        assert run("update", outdated_project) == EXIT_OK
        content = outdated_project.read_text(encoding="utf-8")
        assert '"numpy>=1.25.0",  # array comment survives' in content
        assert 'requires-python = ">=3.11"' in content
        assert "updated files: pyproject.toml" in capsys.readouterr().out

    def test_update_is_idempotent(self, outdated_project: Path, capsys: pytest.CaptureFixture[str]) -> None:
        assert run("update", outdated_project) == EXIT_OK
        content = outdated_project.read_text(encoding="utf-8")
        assert run("update", outdated_project) == EXIT_OK
        assert outdated_project.read_text(encoding="utf-8") == content
        assert "no files changed" in capsys.readouterr().out

    def test_lock_failure_rolls_back_and_fails(
        self, outdated_project: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        lock_path = outdated_project.parent / "uv.lock"
        lock_path.write_text("old lock\n", encoding="utf-8")

        def failing_regenerate(*args: object, **kwargs: object) -> bool:
            raise LockfileError("resolution failed")

        monkeypatch.setattr("dependency_support_policy_action.planner.regenerate_lockfile", failing_regenerate)
        assert run("update", outdated_project, "--lock", "minimal") == EXIT_ERROR
        assert "resolution failed" in capsys.readouterr().err
        assert outdated_project.read_text(encoding="utf-8") == PYPROJECT
        assert lock_path.read_text(encoding="utf-8") == "old lock\n"


class TestFilters:
    def test_exclude(self, outdated_project: Path) -> None:
        assert run("check", outdated_project, "--exclude", "numpy,scipy", "--manage-python", "false") == EXIT_OK

    def test_include(self, outdated_project: Path, capsys: pytest.CaptureFixture[str]) -> None:
        assert run("check", outdated_project, "--include", "scipy", "--manage-python", "false") == EXIT_DRIFT
        assert "numpy" not in capsys.readouterr().out

    def test_package_override_window(self, outdated_project: Path, capsys: pytest.CaptureFixture[str]) -> None:
        assert run("plan", outdated_project, "--package-override", "numpy=48") == EXIT_OK
        payload = json.loads(capsys.readouterr().out)
        floors = {c["name"]: c["new_floor"] for c in payload["dependency_changes"]}
        assert floors["numpy"] == "1.24.0"


class TestErrors:
    def test_invalid_reference_date(self, outdated_project: Path, capsys: pytest.CaptureFixture[str]) -> None:
        assert main(["check", "--pyproject", str(outdated_project), "--reference-date", "not-a-date"]) == EXIT_ERROR
        assert "error:" in capsys.readouterr().err

    def test_missing_pyproject(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        assert run("check", tmp_path / "absent.toml") == EXIT_ERROR
        assert "not found" in capsys.readouterr().err

    def test_registry_failure(self, outdated_project: Path, capsys: pytest.CaptureFixture[str]) -> None:
        assert run("check", outdated_project, fetcher=FakeFetcher()) == EXIT_ERROR
        assert "failed to resolve releases" in capsys.readouterr().err

    def test_invalid_package_override_flag(self, outdated_project: Path) -> None:
        assert run("check", outdated_project, "--package-override", "numpy") == EXIT_ERROR
        assert run("check", outdated_project, "--package-override", "numpy=soon") == EXIT_ERROR

    def test_invalid_tool_table(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        path = tmp_path / "pyproject.toml"
        path.write_text('[tool.dependency-support-policy]\nlock = "nope"\n', encoding="utf-8")
        assert run("check", path) == EXIT_ERROR
        assert "invalid value for 'lock'" in capsys.readouterr().err

    def test_unknown_mode_rejected_by_argparse(self) -> None:
        with pytest.raises(SystemExit):
            main(["destroy"])


class TestGitHubOutputs:
    def _parse_outputs(self, path: Path) -> dict[str, str]:
        text = path.read_text(encoding="utf-8")
        outputs: dict[str, str] = {}
        for match in re.finditer(r"(?ms)^([\w-]+)<<(\S+)\n(.*?)\n\2\n", text):
            outputs[match.group(1)] = match.group(3)
        return outputs

    def test_outputs_written_when_env_set(
        self, outdated_project: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        output_file = tmp_path / "github_output"
        monkeypatch.setenv("GITHUB_OUTPUT", str(output_file))
        assert run("check", outdated_project, "--quiet") == EXIT_DRIFT
        outputs = self._parse_outputs(output_file)
        assert outputs["changed"] == "true"
        assert outputs["python-floor-changed"] == "true"
        floors = json.loads(outputs["dependency-floors-changed"])
        assert {"name": "numpy", "group": "project", "old": "1.21", "new": "1.25.0"} in floors
        assert json.loads(outputs["plan"])["policy"] == "spec0"
        assert json.loads(outputs["files-changed"]) == []

    def test_update_reports_files_changed(
        self, outdated_project: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        output_file = tmp_path / "github_output"
        monkeypatch.setenv("GITHUB_OUTPUT", str(output_file))
        assert run("update", outdated_project, "--quiet") == EXIT_OK
        outputs = self._parse_outputs(output_file)
        assert json.loads(outputs["files-changed"]) == ["pyproject.toml"]

    def test_no_output_file_without_env(self, compliant_project: Path) -> None:
        assert run("check", compliant_project, "--quiet") == EXIT_OK  # simply must not crash


class TestVersionFlag:
    def test_version(self, capsys: pytest.CaptureFixture[str]) -> None:
        with pytest.raises(SystemExit) as excinfo:
            main(["--version"])
        assert excinfo.value.code == 0
        assert "dependency-support-policy" in capsys.readouterr().out


def test_cli_module_importable_as_main() -> None:
    assert callable(cli.main)
