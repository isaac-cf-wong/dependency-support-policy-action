"""Format-preserving update of ``python-version`` entries in GitHub Actions workflows.

When the ``requires-python`` floor is raised, CI entries naming an older
interpreter can no longer install the project. Editing is line based so that
quotes, comments, indentation and sibling keys survive untouched. Handled:

- list values (inline ``[...]``, multi-line ``[...]`` without comments, and
  block ``-`` items): versions below the floor are dropped; if all would be
  dropped, the floor itself is kept;
- scalar values (a matrix ``include`` entry or a tooling pin): raised to the
  floor. Raising may make two ``include`` entries identical; the later
  duplicate is dropped;
- ``exclude`` entries are left alone: excluding a combination that is no
  longer tested is harmless, while raising it would disable a tested one.

Expressions (``${{ matrix.python-version }}``) and non-numeric values
(``3.x``, ``pypy3.10``) are left alone. Constructs this editor cannot rewrite
safely (a multi-line flow list containing comments) are reported in
``WorkflowChange.unsupported`` instead of being skipped silently.

An unquoted floor is written quoted: YAML reads ``3.10`` as the float ``3.1``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from packaging.version import Version

_KEY_RE = re.compile(
    r"^(?P<indent>[ \t]*(?:-[ \t]+)?)(?P<name>[\"']?python-version[\"']?):[ \t]*(?P<rest>[^\r\n]*?)(?P<eol>\r?\n?)$"
)
_BLOCK_ITEM_RE = re.compile(
    r"^(?P<indent>[ \t]*)-[ \t]+(?P<q>[\"']?)(?P<ver>[^\s\"'#,]+)(?P=q)(?P<tail>[ \t]*(?:#[^\r\n]*)?)(?P<eol>\r?\n?)$"
)
_SCALAR_RE = re.compile(r"^(?P<q>[\"']?)(?P<ver>[^\s\"'#]+)(?P=q)(?P<tail>[ \t]*(?:#.*)?)$")
_VERSION_RE = re.compile(r"^(\d+)\.(\d+)(?:[.\-\w]*)$")
_PARENT_KEY_RE = re.compile(r"^[ \t]*[\"']?(?P<key>[\w-]+)[\"']?:[ \t]*(?:[&!][^\s#]+[ \t]*)*(?:#.*)?$")
_ANY_ITEM_RE = re.compile(r"^(?P<indent>[ \t]*)-([ \t]|$)")


@dataclass
class WorkflowChange:
    """Python versions dropped or raised in one workflow file."""

    file: str
    removed: list[str] = field(default_factory=list)
    raised: list[str] = field(default_factory=list)
    unsupported: list[str] = field(default_factory=list)

    @property
    def edited(self) -> bool:
        return bool(self.removed or self.raised)

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


def _floor_text(floor: Version, quote: str) -> str:
    quote = quote or "'"  # an unquoted 3.10 would be read as the float 3.1
    return f"{quote}{floor.major}.{floor.minor}{quote}"


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" \t"))


def _flow_items(raw: list[str], floor: Version, change: WorkflowChange) -> list[str]:
    kept = [t for t in raw if not _below(_unquote(t)[1], floor)]
    change.removed.extend(_unquote(t)[1] for t in raw if _below(_unquote(t)[1], floor))
    if not kept and raw:
        kept = [_floor_text(floor, _unquote(raw[0])[0])]
    return kept


def _flow_list(
    lines: list[str], i: int, key: re.Match[str], floor: Version, change: WorkflowChange
) -> tuple[dict[int, str], set[int], int]:
    """Rewrite a flow list starting at line ``i``; return (replacements, drops, next index)."""
    rest = key["rest"]
    end_line = i
    text = rest
    while "]" not in text and end_line + 1 < len(lines):
        end_line += 1
        text += "\n" + lines[end_line].strip()
    close = text.find("]")
    after = text[close + 1 :] if close != -1 else ""
    multiline = end_line > i
    if close == -1 or (multiline and ("#" in text[:close] or after.strip())):
        change.unsupported.append(f"line {i + 1}: multi-line python-version list not rewritten")
        return {}, set(), i + 1
    raw = [t.strip() for t in text[1:close].replace("\n", ",").split(",") if t.strip()]
    before = len(change.removed)
    kept = _flow_items(raw, floor, change)
    if len(change.removed) == before:
        return {}, set(), end_line + 1
    new = f"{key['indent']}{key['name']}: [{', '.join(kept)}]{after}{key['eol']}"
    return {i: new}, set(range(i + 1, end_line + 1)), end_line + 1


def _block_list(
    lines: list[str], start: int, key_col: int, floor: Version, change: WorkflowChange
) -> tuple[dict[int, str], set[int], int]:
    """Rewrite ``-`` items after a bare key; comments and blank lines between items pass through."""
    items: list[tuple[int, re.Match[str] | None]] = []
    i = start
    while i < len(lines):
        stripped = lines[i].strip()
        if stripped == "" or stripped.startswith("#"):
            i += 1
            continue
        any_item = _ANY_ITEM_RE.match(lines[i])
        if any_item is None or len(any_item["indent"]) < key_col:
            break
        items.append((i, _BLOCK_ITEM_RE.match(lines[i])))  # None: not a plain version (expression, mapping)
        i += 1
    next_index = items[-1][0] + 1 if items else start
    stale = [(n, m) for n, m in items if m is not None and _below(m["ver"], floor)]
    change.removed.extend(m["ver"] for _, m in stale)
    drops = {n for n, _ in stale}
    repl: dict[int, str] = {}
    if stale and len(stale) == len(items):
        n, m = stale[0]
        drops.discard(n)
        repl[n] = f"{m['indent']}- {_floor_text(floor, m['q'])}{m['tail']}{m['eol']}"
    return repl, drops, next_index


def _enclosing_key(lines: list[str], idx: int, dash_col: int) -> tuple[str, int] | None:
    """Name and line of the mapping key owning the list item that starts at column ``dash_col``."""
    for j in range(idx - 1, -1, -1):
        line = lines[j]
        stripped = line.strip()
        if stripped == "" or stripped.startswith("#"):
            continue
        col = _indent(line)
        if col > dash_col or (col == dash_col and stripped.startswith("-")):
            continue
        match = _PARENT_KEY_RE.match(line)
        return (match["key"], j) if match and col <= dash_col else None
    return None


def _entry_bounds(lines: list[str], idx: int, key_col: int, dash_col: int) -> tuple[int, int]:
    """First and last line of the list item containing line ``idx``."""
    start = idx
    for j in range(idx, -1, -1):
        line = lines[j]
        if line.strip() and _indent(line) == dash_col and line.lstrip().startswith("-"):
            start = j
            break
    end = idx
    for j in range(idx + 1, len(lines)):
        line = lines[j]
        if line.strip() and _indent(line) < key_col:
            break
        if line.strip():
            end = j
    return start, end


_Seen = dict[tuple[int, str], tuple[int, int, str | None]]


def _scalar(
    lines: list[str],
    i: int,
    key: re.Match[str],
    key_col: int,
    floor: Version,
    change: WorkflowChange,
    seen: _Seen,
) -> tuple[dict[int, str], set[int]]:
    """Raise a scalar ``python-version`` below the floor; dedupe ``include`` entries it duplicates."""
    value = _SCALAR_RE.match(key["rest"])
    if value is None:
        return {}, set()
    below = _below(value["ver"], floor)
    dash_col = key["indent"].index("-") if "-" in key["indent"] else key_col - 2
    start, end = _entry_bounds(lines, i, key_col, dash_col) if dash_col >= 0 else (i, i)
    in_entry = dash_col >= 0 and lines[start].lstrip().startswith("-") and _indent(lines[start]) == dash_col
    enclosing = _enclosing_key(lines, start, dash_col) if in_entry else None
    parent, block = enclosing if enclosing is not None else (None, -1)
    if parent == "exclude":
        return {}, set()
    repl: dict[int, str] = {}
    if below:
        new = f"{key['indent']}{key['name']}: {_floor_text(floor, value['q'])}{value['tail']}{key['eol']}"
        repl[i] = new
        change.raised.append(value["ver"])
    if parent != "include":
        return repl, set()
    text = "".join(repl.get(n, lines[n]) for n in range(start, end + 1))
    drops: set[int] = set()
    ident = (block, text)  # duplicates are only meaningful within one include block
    if ident in seen:
        prev_start, prev_end, prev_raised = seen[ident]
        if below:
            drops = set(range(start, end + 1))
            change.raised.remove(value["ver"])
            change.removed.append(value["ver"])
            repl = {}
        elif prev_raised is not None:
            drops = set(range(prev_start, prev_end + 1))
            change.raised.remove(prev_raised)
            change.removed.append(prev_raised)
            seen[ident] = (start, end, None)
    else:
        seen[ident] = (start, end, value["ver"] if below else None)
    return repl, drops


def update_workflow_text(text: str, floor: Version) -> tuple[str, WorkflowChange]:
    """Return ``(new_text, change)``; ``change.file`` is left empty for the caller."""
    change = WorkflowChange(file="")
    lines = text.splitlines(keepends=True)
    repl: dict[int, str] = {}
    drops: set[int] = set()
    new_repl: dict[int, str]
    new_drops: set[int]
    seen: _Seen = {}
    i = 0
    while i < len(lines):
        key = _KEY_RE.match(lines[i])
        if key is None:
            i += 1
            continue
        rest = key["rest"]
        key_col = len(key["indent"].replace("-", " "))
        if rest[:1] in {"&", "*", "!"}:  # anchor, alias or tag: not rewritten, but never silently
            change.unsupported.append(f"line {i + 1}: python-version with an anchor, alias or tag not rewritten")
            new_repl, new_drops, i = {}, set(), i + 1
        elif rest.startswith("["):
            new_repl, new_drops, i = _flow_list(lines, i, key, floor, change)
        elif rest == "" or rest.startswith("#"):
            new_repl, new_drops, i = _block_list(lines, i + 1, key_col, floor, change)
        else:
            new_repl, new_drops = _scalar(lines, i, key, key_col, floor, change, seen)
            i += 1
        repl.update(new_repl)
        drops |= new_drops
    return "".join(repl.get(n, line) for n, line in enumerate(lines) if n not in drops), change
