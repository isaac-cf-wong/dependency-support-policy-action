"""Tests for GitHub Actions python-version editing."""

from __future__ import annotations

from pathlib import Path

from packaging.version import Version

from dependency_support_policy.workflow import find_workflow_files, update_workflow_text

FLOOR = Version("3.13")


def update(text: str) -> tuple[str, list[str], list[str]]:
    new, change = update_workflow_text(text, FLOOR)
    return new, change.removed, change.raised


def test_inline_list_drops_stale_and_keeps_formatting() -> None:
    text = "        python-version: ['3.12', \"3.13\", 3.14]  # c\n"
    new, removed, raised = update(text)
    assert new == '        python-version: ["3.13", 3.14]  # c\n'
    assert removed == ["3.12"]
    assert raised == []


def test_inline_list_all_stale_keeps_floor() -> None:
    new, removed, _ = update("python-version: ['3.11', '3.12']\n")
    assert new == "python-version: ['3.13']\n"
    assert removed == ["3.11", "3.12"]


def test_block_list() -> None:
    text = "python-version:\n  - '3.12'\n  - '3.13'  # keep\n  - '3.14'\nos: x\n"
    new, removed, _ = update(text)
    assert new == "python-version:\n  - '3.13'  # keep\n  - '3.14'\nos: x\n"
    assert removed == ["3.12"]


def test_block_list_all_stale_keeps_floor() -> None:
    new, _, _ = update("python-version:\n  - '3.11'\n  - '3.12'\n")
    assert new == "python-version:\n  - '3.13'\n"


def test_scalar_in_include_entry_is_raised() -> None:
    text = "- os: ubuntu-latest\n  python-version: '3.12'\n  resolution: lowest-direct\n"
    new, removed, raised = update(text)
    assert new == "- os: ubuntu-latest\n  python-version: '3.13'\n  resolution: lowest-direct\n"
    assert (removed, raised) == ([], ["3.12"])


def test_dash_prefixed_scalar_and_unquoted() -> None:
    new, _, raised = update("- python-version: 3.10\n")
    assert new == "- python-version: 3.13\n"
    assert raised == ["3.10"]


def test_leaves_expressions_and_non_numeric_alone() -> None:
    text = (
        "python-version: ${{ matrix.python-version }}\n"
        "python-version: 3.x\n"
        "python-version: pypy3.10\n"
        "python-version: '3.14'\n"
        "python-version: ['3.13', 'pypy3.10']\n"
    )
    new, removed, raised = update(text)
    assert new == text
    assert removed == raised == []


def test_crlf_preserved() -> None:
    new, _, _ = update("python-version: '3.12'\r\nnext: 1\r\n")
    assert new == "python-version: '3.13'\r\nnext: 1\r\n"


def test_find_workflow_files(tmp_path: Path) -> None:
    assert find_workflow_files(tmp_path) == []
    wf = tmp_path / ".github" / "workflows"
    wf.mkdir(parents=True)
    (wf / "b.yaml").write_text("x")
    (wf / "a.yml").write_text("x")
    (wf / "c.txt").write_text("x")
    assert [p.name for p in find_workflow_files(tmp_path)] == ["a.yml", "b.yaml"]
