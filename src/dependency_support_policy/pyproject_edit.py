"""Format-preserving pyproject.toml reading and editing via tomlkit."""

from __future__ import annotations

import os
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

import tomlkit
from tomlkit import TOMLDocument
from tomlkit.exceptions import TOMLKitError
from tomlkit.items import Array

from .errors import ConfigError

PROJECT_GROUP = "project"
_OPTIONAL_PREFIX = "optional:"
_GROUP_PREFIX = "group:"


@dataclass
class DependencyItem:
    """One string entry of a dependency array, addressable for in-place update."""

    group: str
    index: int
    text: str
    _array: Array = field(repr=False)

    def set_text(self, new_text: str) -> None:
        self._array[self.index] = new_text


def load_document(path: Path) -> TOMLDocument:
    """Parse ``path`` as TOML, preserving formatting and comments."""
    try:
        return tomlkit.parse(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigError(f"pyproject file not found: {path}") from exc
    except TOMLKitError as exc:
        raise ConfigError(f"failed to parse {path}: {exc}") from exc


def dump_document(document: TOMLDocument) -> str:
    return tomlkit.dumps(document)


def write_text_atomic(path: Path, text: str) -> None:
    """Write ``text`` to ``path`` atomically (write temp file, then rename)."""
    temporary = path.with_name(path.name + ".dspa-tmp")
    temporary.write_text(text, encoding="utf-8")
    try:
        if path.exists():
            os.chmod(temporary, path.stat().st_mode)
        os.replace(temporary, path)
    except OSError:
        temporary.unlink(missing_ok=True)
        raise


def available_groups(document: TOMLDocument) -> list[str]:
    """All dependency collections present in the document."""
    groups: list[str] = []
    project = document.get("project")
    if isinstance(project, dict):
        if "dependencies" in project:
            groups.append(PROJECT_GROUP)
        optional = project.get("optional-dependencies")
        if isinstance(optional, dict):
            groups.extend(f"{_OPTIONAL_PREFIX}{name}" for name in optional)
    dependency_groups = document.get("dependency-groups")
    if isinstance(dependency_groups, dict):
        groups.extend(f"{_GROUP_PREFIX}{name}" for name in dependency_groups)
    return groups


def resolve_groups(document: TOMLDocument, selection: Sequence[str]) -> list[str]:
    """Expand a group selection (supporting ``all``, ``optional``, ``group``) to concrete groups.

    Explicitly named groups that do not exist raise :class:`ConfigError`.
    """
    present = available_groups(document)
    resolved: list[str] = []
    for selector in selection:
        if selector == "all":
            matches = present
        elif selector == "optional":
            matches = [g for g in present if g.startswith(_OPTIONAL_PREFIX)]
        elif selector == "group":
            matches = [g for g in present if g.startswith(_GROUP_PREFIX)]
        elif selector in present:
            matches = [selector]
        elif selector == PROJECT_GROUP:
            matches = []  # project table has no dependencies array; nothing to manage
        else:
            raise ConfigError(f"dependency group {selector!r} not found in pyproject.toml")
        resolved.extend(g for g in matches if g not in resolved)
    return resolved


def _group_array(document: TOMLDocument, group: str) -> Array:
    if group == PROJECT_GROUP:
        candidate = document["project"]["dependencies"]
    elif group.startswith(_OPTIONAL_PREFIX):
        candidate = document["project"]["optional-dependencies"][group[len(_OPTIONAL_PREFIX) :]]
    elif group.startswith(_GROUP_PREFIX):
        candidate = document["dependency-groups"][group[len(_GROUP_PREFIX) :]]
    else:  # pragma: no cover - groups come from resolve_groups
        raise ConfigError(f"unknown dependency group {group!r}")
    if not isinstance(candidate, Array):
        raise ConfigError(f"dependency group {group!r} is not an array of requirement strings")
    return candidate


def iter_dependency_items(document: TOMLDocument, groups: Sequence[str]) -> list[DependencyItem]:
    """List all string requirement entries in the selected groups.

    Non-string entries (e.g. ``{include-group = "..."}``) are ignored.
    """
    items: list[DependencyItem] = []
    for group in resolve_groups(document, groups):
        array = _group_array(document, group)
        for index, value in enumerate(array):
            if isinstance(value, str):
                items.append(DependencyItem(group=group, index=index, text=str(value), _array=array))
    return items


def get_requires_python(document: TOMLDocument) -> str | None:
    project = document.get("project")
    if isinstance(project, dict):
        value = project.get("requires-python")
        if isinstance(value, str):
            return str(value)
    return None


def set_requires_python(document: TOMLDocument, text: str) -> None:
    document["project"]["requires-python"] = text
