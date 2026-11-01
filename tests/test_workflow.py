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
    assert new == "- python-version: '3.13'\n"  # quoted: bare 3.10 would parse as the float 3.1
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


def test_multiline_flow_list_collapsed() -> None:
    text = "python-version: [\n  '3.12',\n  '3.13',\n]\nos: x\n"
    new, removed, _ = update(text)
    assert new == "python-version: ['3.13']\nos: x\n"
    assert removed == ["3.12"]


def test_multiline_flow_list_with_comment_is_reported_not_changed() -> None:
    text = "python-version: [\n  '3.12',  # old\n  '3.13',\n]\n"
    new, change = update_workflow_text(text, FLOOR)
    assert new == text
    assert change.unsupported


def test_block_list_comments_and_blank_lines_between_items() -> None:
    text = "python-version:\n  - '3.10'\n  # older\n\n  - '3.11'\n  - '3.12'\nnext: 1\n"
    new, removed, _ = update(text)
    assert new == "python-version:\n  - '3.13'\n  # older\n\nnext: 1\n"
    assert removed == ["3.10", "3.11", "3.12"]


def test_exclude_entries_untouched() -> None:
    text = "exclude:\n  - os: windows-latest\n    python-version: '3.11'\n"
    new, removed, raised = update(text)
    assert new == text
    assert removed == raised == []


def test_include_entries_made_identical_are_deduped() -> None:
    text = (
        "include:\n"
        "  - os: macos-latest\n    python-version: '3.11'\n"
        "  - os: macos-latest\n    python-version: '3.13'\n"
        "  - os: linux\n    python-version: '3.12'\n"
    )
    new, removed, raised = update(text)
    assert new == (
        "include:\n  - os: macos-latest\n    python-version: '3.13'\n  - os: linux\n    python-version: '3.13'\n"
    )
    assert removed == ["3.11"]
    assert raised == ["3.12"]


def test_include_duplicate_raised_after_original() -> None:
    text = "include:\n  - os: m\n    python-version: '3.13'\n  - os: m\n    python-version: '3.12'\n"
    new, removed, raised = update(text)
    assert new == "include:\n  - os: m\n    python-version: '3.13'\n"
    assert (removed, raised) == (["3.12"], [])


def test_include_original_duplicate_of_earlier_raised_drops_the_raised() -> None:
    text = "include:\n  - os: m\n    python-version: '3.12'\n  - os: m\n    python-version: '3.13'\n"
    new, removed, raised = update(text)
    assert new == "include:\n  - os: m\n    python-version: '3.13'\n"
    assert (removed, raised) == (["3.12"], [])


def test_quoted_key() -> None:
    new, removed, _ = update("\"python-version\": ['3.12', '3.13']\n")
    assert new == "\"python-version\": ['3.13']\n"
    assert removed == ["3.12"]


def test_unquoted_floor_in_all_stale_list_is_quoted() -> None:
    new, _, _ = update("python-version: [3.9, 3.10]\n")
    assert new == "python-version: ['3.13']\n"


def test_three_identical_include_entries_collapse_to_one() -> None:
    entry = "  - os: m\n    python-version: '{}'\n"
    text = "include:\n" + entry.format("3.12") + entry.format("3.13") + entry.format("3.13")
    new, removed, raised = update(text)
    assert new == "include:\n" + entry.format("3.13") + entry.format("3.13")
    assert (removed, raised) == (["3.12"], [])


def test_identical_include_entries_in_separate_jobs_are_independent() -> None:
    job = "  {}:\n    include:\n      - os: u\n        python-version: '3.12'\n"
    text = "jobs:\n" + job.format("test") + job.format("bench")
    new, removed, raised = update(text)
    assert new == text.replace("'3.12'", "'3.13'")
    assert (removed, raised) == ([], ["3.12", "3.12"])


def test_quoted_exclude_key_untouched() -> None:
    text = "\"exclude\":\n  - os: w\n    python-version: '3.11'\n"
    assert update(text)[0] == text


def test_block_list_with_expression_item_does_not_synthesize_floor() -> None:
    text = "python-version:\n  - '3.11'\n  - ${{ matrix.py }}\n  - '3.12'\n"
    new, removed, _ = update(text)
    assert new == "python-version:\n  - ${{ matrix.py }}\n"
    assert removed == ["3.11", "3.12"]
