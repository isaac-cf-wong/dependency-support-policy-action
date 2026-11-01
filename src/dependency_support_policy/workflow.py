"""Format-preserving update of ``python-version`` entries in GitHub Actions workflows.

When the ``requires-python`` floor is raised, CI entries naming an older
interpreter can no longer install the project. Editing is line based so that
quotes, comments, indentation and sibling keys survive untouched. Three shapes
of ``python-version`` are handled:

- inline list, ``python-version: ['3.12', '3.13']`` and block list
  (``-`` items): versions below the floor are dropped; if all would be
  dropped, the floor itself is kept;
- scalar, ``python-version: '3.12'`` (a matrix ``include`` entry or a tooling
  pin): raised to the floor.

Expressions (``${{ matrix.python-version }}``) and non-numeric values
(``3.x``, ``pypy3.10``) are left alone.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from packaging.version import Version

_KEY_RE = re.compile(r"^(?P<indent>[ \t]*(?:-[ \t]+)?)python-version:[ \t]*(?P<rest>[^\r\n]*?)(?P<eol>\r?\n?)$")
_BLOCK_ITEM_RE = re.compile(
    r"^(?P<indent>[ \t]*)-[ \t]+(?P<q>[\"']?)(?P<ver>[^\s\"'#,]+)(?P=q)(?P<tail>[ \t]*(?:#[^\r\n]*)?)(?P<eol>\r?\n?)$"
)
_SCALAR_RE = re.compile(r"^(?P<q>[\"']?)(?P<ver>[^\s\"'#]+)(?P=q)(?P<tail>[ \t]*(?:#.*)?)$")
_VERSION_RE = re.compile(r"^(\d+)\.(\d+)(?:[.\-\w]*)$")


@dataclass
class WorkflowChange:
    """Python versions dropped or raised in one workflow file."""

    file: str
    removed: list[str] = field(default_factory=list)
    raised: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {"file": self.file, "removed": list(self.removed), "raised": list(self.raised)}


def find_workflow_files(project_dir: Path) -> list[Path]:
    """Workflow files in ``<project_dir>/.github/workflows``, sorted."""
    directory = project_dir / ".github" / "workflows"
    if not directory.is_dir():
        return []
    return sorted(p for p in directory.iterdir() if p.is_file() and p.suffix in {".yml", ".yaml"})


def _below(token: str, floor: Version) -> bool:
    match = _VERSION_RE.match(token)
    return match is not None and (int(match[1]), int(match[2])) < (floor.major, floor.minor)


def _unquote(token: str) -> tuple[str, str]:
    token = token.strip()
    quote = token[0] if token[:1] in {'"', "'"} and token[-1:] == token[:1] else ""
    return quote, token[len(quote) : len(token) - len(quote)]


def _inline_list(key: re.Match[str], floor: Version, change: WorkflowChange) -> str | None:
    rest = key["rest"]
    end = rest.find("]")
    if end == -1:
        return None
    raw = [t.strip() for t in rest[1:end].split(",") if t.strip()]
    kept = [t for t in raw if not _below(_unquote(t)[1], floor)]
    change.removed.extend(_unquote(t)[1] for t in raw if t not in kept)
    if not kept and raw:
        quote = _unquote(raw[0])[0]
        kept = [f"{quote}{floor.major}.{floor.minor}{quote}"]
    return f"{key['indent']}python-version: [{', '.join(kept)}]{rest[end + 1 :]}{key['eol']}"


def _block_list(
    lines: list[str], start: int, key_col: int, floor: Version, change: WorkflowChange
) -> tuple[list[str], int]:
    """Rewrite the ``-`` items after a bare ``python-version:`` key; return (lines, next index)."""
    items: list[tuple[re.Match[str], str]] = []
    i = start
    while i < len(lines):
        item = _BLOCK_ITEM_RE.match(lines[i])
        if item is None or len(item["indent"]) < key_col:
            break
        items.append((item, lines[i]))
        i += 1
    kept = [raw for m, raw in items if not _below(m["ver"], floor)]
    dropped = [m for m, _ in items if _below(m["ver"], floor)]
    change.removed.extend(m["ver"] for m in dropped)
    if not kept and dropped:
        f = dropped[0]
        kept = [f"{f['indent']}- {f['q']}{floor.major}.{floor.minor}{f['q']}{f['tail']}{f['eol']}"]
    return kept, i


def _scalar(key: re.Match[str], floor: Version, change: WorkflowChange) -> str | None:
    value = _SCALAR_RE.match(key["rest"])
    if value is None or not _below(value["ver"], floor):
        return None
    change.raised.append(value["ver"])
    q = value["q"]
    return f"{key['indent']}python-version: {q}{floor.major}.{floor.minor}{q}{value['tail']}{key['eol']}"


def update_workflow_text(text: str, floor: Version) -> tuple[str, WorkflowChange]:
    """Return ``(new_text, change)``; ``change.file`` is left empty for the caller."""
    change = WorkflowChange(file="")
    lines = text.splitlines(keepends=True)
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        i += 1
        key = _KEY_RE.match(line)
        if key is None:
            out.append(line)
            continue
        rest = key["rest"]
        if rest.startswith("["):
            out.append(_inline_list(key, floor, change) or line)
        elif rest == "" or rest.startswith("#"):
            out.append(line)
            kept, i = _block_list(lines, i, len(key["indent"].replace("-", " ")), floor, change)
            out.extend(kept)
        else:
            out.append(_scalar(key, floor, change) or line)
    return "".join(out), change
