"""Tests for format-preserving pyproject.toml editing."""

from __future__ import annotations

from pathlib import Path

import pytest
import tomlkit

from dependency_support_policy.errors import ConfigError
from dependency_support_policy.pyproject_edit import (
    available_groups,
    dump_document,
    get_requires_python,
    iter_dependency_items,
    load_document,
    resolve_groups,
    set_requires_python,
    write_text_atomic,
)

SAMPLE = """\
# project metadata
[project]
name = "demo"
version = "0.1.0"
requires-python = ">=3.9"  # python floor
dependencies = [
  "numpy>=1.21",  # keep this comment
  "scipy >= 1.7, <2",
]

[project.optional-dependencies]
plot = ["matplotlib>=3.5"]

[dependency-groups]
dev = [
  "pytest>=7.0",
  { include-group = "lint" },
]
lint = ["ruff>=0.1"]
"""


class TestLoadDocument:
    def test_missing_file(self, tmp_path: Path) -> None:
        with pytest.raises(ConfigError, match="not found"):
            load_document(tmp_path / "pyproject.toml")

    def test_invalid_toml(self, tmp_path: Path) -> None:
        path = tmp_path / "pyproject.toml"
        path.write_text("[project\nname=", encoding="utf-8")
        with pytest.raises(ConfigError, match="failed to parse"):
            load_document(path)

    def test_round_trip_preserves_text(self, tmp_path: Path) -> None:
        path = tmp_path / "pyproject.toml"
        path.write_text(SAMPLE, encoding="utf-8")
        assert dump_document(load_document(path)) == SAMPLE


class TestGroups:
    def test_available_groups(self) -> None:
        document = tomlkit.parse(SAMPLE)
        assert available_groups(document) == ["project", "optional:plot", "group:dev", "group:lint"]

    def test_resolve_all(self) -> None:
        document = tomlkit.parse(SAMPLE)
        assert resolve_groups(document, ["all"]) == ["project", "optional:plot", "group:dev", "group:lint"]

    def test_resolve_shorthands(self) -> None:
        document = tomlkit.parse(SAMPLE)
        assert resolve_groups(document, ["optional"]) == ["optional:plot"]
        assert resolve_groups(document, ["group"]) == ["group:dev", "group:lint"]

    def test_resolve_explicit(self) -> None:
        document = tomlkit.parse(SAMPLE)
        assert resolve_groups(document, ["project", "group:dev"]) == ["project", "group:dev"]

    def test_resolve_deduplicates(self) -> None:
        document = tomlkit.parse(SAMPLE)
        assert resolve_groups(document, ["all", "project"]) == ["project", "optional:plot", "group:dev", "group:lint"]

    def test_unknown_group_rejected(self) -> None:
        document = tomlkit.parse(SAMPLE)
        with pytest.raises(ConfigError, match="'group:nope' not found"):
            resolve_groups(document, ["group:nope"])

    def test_project_without_dependencies(self) -> None:
        document = tomlkit.parse('[project]\nname = "demo"\n')
        assert resolve_groups(document, ["project"]) == []

    def test_non_array_group(self) -> None:
        document = tomlkit.parse('[dependency-groups]\ndev = "oops"\n')
        with pytest.raises(ConfigError, match="not an array"):
            iter_dependency_items(document, ["group:dev"])


class TestIterDependencyItems:
    def test_strings_only(self) -> None:
        document = tomlkit.parse(SAMPLE)
        items = iter_dependency_items(document, ["all"])
        assert [(item.group, item.text) for item in items] == [
            ("project", "numpy>=1.21"),
            ("project", "scipy >= 1.7, <2"),
            ("optional:plot", "matplotlib>=3.5"),
            ("group:dev", "pytest>=7.0"),  # include-group table skipped
            ("group:lint", "ruff>=0.1"),
        ]

    def test_set_text_preserves_all_other_formatting(self) -> None:
        document = tomlkit.parse(SAMPLE)
        items = iter_dependency_items(document, ["project"])
        items[0].set_text("numpy>=1.25.0")
        expected = SAMPLE.replace('"numpy>=1.21"', '"numpy>=1.25.0"')
        assert dump_document(document) == expected


class TestRequiresPython:
    def test_get(self) -> None:
        assert get_requires_python(tomlkit.parse(SAMPLE)) == ">=3.9"

    def test_get_absent(self) -> None:
        assert get_requires_python(tomlkit.parse('[project]\nname = "demo"\n')) is None

    def test_set_preserves_comment(self) -> None:
        document = tomlkit.parse(SAMPLE)
        set_requires_python(document, ">=3.11")
        assert dump_document(document) == SAMPLE.replace('">=3.9"', '">=3.11"')


class TestWriteTextAtomic:
    def test_writes_and_overwrites(self, tmp_path: Path) -> None:
        path = tmp_path / "file.toml"
        write_text_atomic(path, "one\n")
        write_text_atomic(path, "two\n")
        assert path.read_text(encoding="utf-8") == "two\n"
        assert list(tmp_path.iterdir()) == [path]  # no temp file left behind

    def test_preserves_mode(self, tmp_path: Path) -> None:
        path = tmp_path / "file.toml"
        path.write_text("one\n", encoding="utf-8")
        path.chmod(0o600)
        write_text_atomic(path, "two\n")
        assert path.stat().st_mode & 0o777 == 0o600
