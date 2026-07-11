"""Tests for uv lockfile regeneration (using a stub uv executable)."""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from dependency_support_policy import lockfile
from dependency_support_policy.config import LockMode
from dependency_support_policy.errors import LockfileError
from dependency_support_policy.lockfile import regenerate_lockfile


def make_stub_uv(tmp_path: Path, script_body: str) -> str:
    """Create an executable shell script standing in for uv."""
    stub = tmp_path / "stub-uv"
    stub.write_text(f"#!/bin/sh\n{script_body}\n", encoding="utf-8")
    stub.chmod(stub.stat().st_mode | stat.S_IXUSR)
    return str(stub)


@pytest.fixture
def project_dir(tmp_path: Path) -> Path:
    directory = tmp_path / "project"
    directory.mkdir()
    return directory


class TestRegenerateLockfile:
    def test_off_mode_runs_nothing(self, project_dir: Path) -> None:
        assert regenerate_lockfile(project_dir, LockMode.OFF, uv_executable="/nonexistent/uv") is False

    def test_lock_content_changed(self, tmp_path: Path, project_dir: Path) -> None:
        (project_dir / "uv.lock").write_text("old\n", encoding="utf-8")
        uv = make_stub_uv(tmp_path, 'printf "new\\n" > uv.lock')
        assert regenerate_lockfile(project_dir, LockMode.MINIMAL, uv_executable=uv) is True

    def test_lock_content_unchanged(self, tmp_path: Path, project_dir: Path) -> None:
        (project_dir / "uv.lock").write_text("same\n", encoding="utf-8")
        uv = make_stub_uv(tmp_path, 'printf "same\\n" > uv.lock')
        assert regenerate_lockfile(project_dir, LockMode.MINIMAL, uv_executable=uv) is False

    def test_upgrade_mode_passes_flag(self, tmp_path: Path, project_dir: Path) -> None:
        uv = make_stub_uv(tmp_path, 'printf "%s\\n" "$@" > args.txt')
        regenerate_lockfile(project_dir, LockMode.UPGRADE, uv_executable=uv)
        assert (project_dir / "args.txt").read_text(encoding="utf-8").split() == ["lock", "--upgrade"]

    def test_minimal_mode_has_no_upgrade_flag(self, tmp_path: Path, project_dir: Path) -> None:
        uv = make_stub_uv(tmp_path, 'printf "%s\\n" "$@" > args.txt')
        regenerate_lockfile(project_dir, LockMode.MINIMAL, uv_executable=uv)
        assert (project_dir / "args.txt").read_text(encoding="utf-8").split() == ["lock"]

    def test_failure_raises_with_stderr(self, tmp_path: Path, project_dir: Path) -> None:
        uv = make_stub_uv(tmp_path, 'echo "no solution for numpy" >&2; exit 1')
        with pytest.raises(LockfileError, match="no solution for numpy"):
            regenerate_lockfile(project_dir, LockMode.MINIMAL, uv_executable=uv)

    def test_missing_executable(self, project_dir: Path) -> None:
        missing = os.path.join(os.sep, "definitely", "missing", "uv")
        with pytest.raises(LockfileError, match="uv executable not found"):
            regenerate_lockfile(project_dir, LockMode.MINIMAL, uv_executable=missing)

    def test_timeout(self, tmp_path: Path, project_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(lockfile, "_UV_TIMEOUT_SECONDS", 0.2)
        uv = make_stub_uv(tmp_path, "sleep 2")
        with pytest.raises(LockfileError, match="timed out"):
            regenerate_lockfile(project_dir, LockMode.MINIMAL, uv_executable=uv)
