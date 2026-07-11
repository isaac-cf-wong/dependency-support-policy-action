"""Parsing and lower-bound rewriting of PEP 508 requirement strings.

Rewrites are textual splices: only the lower-bound clause (or a newly
appended one) changes, so upper bounds, exclusions, extras, markers, and the
original spacing are preserved character-for-character.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

from packaging.requirements import InvalidRequirement, Requirement
from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.utils import NormalizedName, canonicalize_name
from packaging.version import InvalidVersion, Version

_NAME_EXTRAS_RE = re.compile(
    r"""^\s*
        [A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?   # distribution name
        \s*
        (?:\[[^\]]*\]\s*)?                           # optional extras
    """,
    re.VERBOSE,
)
_CLAUSE_RE = re.compile(r"^(\s*)(===|==|!=|~=|<=|>=|<|>)(\s*)(.*?)(\s*)$")

_PINNED_OPERATORS = frozenset({"==", "===", "~="})
_LOWER_BOUND_OPERATORS = frozenset({">=", ">"})


class RewriteStatus(Enum):
    """Outcome of a lower-bound rewrite attempt."""

    UNCHANGED = "unchanged"
    UPDATED = "updated"
    SKIPPED = "skipped"


@dataclass(frozen=True)
class RewriteResult:
    """Result of rewriting one requirement (or specifier) string."""

    status: RewriteStatus
    text: str
    name: NormalizedName | None = None
    old_floor: Version | None = None
    new_floor: Version | None = None
    reason: str | None = None


@dataclass(frozen=True)
class _Clause:
    lead: str
    operator: str
    gap: str
    version_text: str
    trail: str

    @property
    def text(self) -> str:
        return f"{self.lead}{self.operator}{self.gap}{self.version_text}{self.trail}"


def requirement_name(text: str) -> NormalizedName | None:
    """Canonical distribution name of a requirement string, or None if unparsable."""
    try:
        return canonicalize_name(Requirement(text).name)
    except InvalidRequirement:
        return None


def rewrite_specifier_lower_bound(spec_text: str, floor: Version) -> RewriteResult:
    """Raise the ``>=`` lower bound of a bare specifier set (e.g. ``requires-python``)."""
    return _rewrite_spec(spec_text, floor, head="", tail="")


def rewrite_requirement_lower_bound(text: str, floor: Version) -> RewriteResult:
    """Raise the lower bound of a full PEP 508 requirement string."""
    try:
        requirement = Requirement(text)
    except InvalidRequirement:
        return RewriteResult(RewriteStatus.SKIPPED, text, reason="unparsable requirement")
    name = canonicalize_name(requirement.name)
    if requirement.url is not None:
        return RewriteResult(RewriteStatus.SKIPPED, text, name=name, reason="direct URL requirement")

    base, semicolon, marker = text.partition(";")
    match = _NAME_EXTRAS_RE.match(base)
    if match is None:  # pragma: no cover - unreachable once Requirement() parsed
        return RewriteResult(RewriteStatus.SKIPPED, text, name=name, reason="unparsable requirement")
    head = base[: match.end()]
    spec_region = base[match.end() :]
    result = _rewrite_spec(spec_region, floor, head=head, tail=semicolon + marker)
    return RewriteResult(
        status=result.status,
        text=result.text,
        name=name,
        old_floor=result.old_floor,
        new_floor=result.new_floor,
        reason=result.reason,
    )


def _rewrite_spec(spec_region: str, floor: Version, *, head: str, tail: str) -> RewriteResult:
    original = head + spec_region + tail
    prefix, inner, suffix = _split_parentheses(spec_region)
    clauses = _parse_clauses(inner)
    if clauses is None:
        return RewriteResult(RewriteStatus.SKIPPED, original, reason="unparsable version specifier")

    if any(clause.operator in _PINNED_OPERATORS for clause in clauses):
        return RewriteResult(RewriteStatus.SKIPPED, original, reason="pinned requirement (==, ===, or ~=)")

    try:
        bound_index, old_floor = _effective_lower_bound(clauses)
    except InvalidVersion:
        return RewriteResult(RewriteStatus.SKIPPED, original, reason="unparsable lower-bound version")
    if old_floor is not None and old_floor >= floor:
        return RewriteResult(
            RewriteStatus.UNCHANGED,
            original,
            old_floor=old_floor,
            reason="existing lower bound already satisfies the policy floor",
        )

    others = [clause for index, clause in enumerate(clauses) if index != bound_index]
    if not _floor_allowed(others, floor):
        return RewriteResult(
            RewriteStatus.SKIPPED,
            original,
            old_floor=old_floor,
            reason=f"policy floor {floor} conflicts with existing constraints",
        )

    if bound_index is not None:
        old = clauses[bound_index]
        new_clause = _Clause(lead=old.lead, operator=">=", gap=old.gap, version_text=str(floor), trail=old.trail)
        new_clauses = [*clauses[:bound_index], new_clause, *clauses[bound_index + 1 :]]
        new_inner = ",".join(clause.text for clause in new_clauses)
        new_text = head + prefix + new_inner + suffix + tail
    elif clauses:
        separator = ", " if ", " in inner else ","
        new_inner = inner + f"{separator}>={floor}"
        new_text = head + prefix + new_inner + suffix + tail
    else:
        new_text = head + prefix + f">={floor}" + suffix + tail

    return RewriteResult(RewriteStatus.UPDATED, new_text, old_floor=old_floor, new_floor=floor)


def _split_parentheses(spec_region: str) -> tuple[str, str, str]:
    """Split ``(...)``-wrapped specifiers into prefix, inner text, and suffix."""
    stripped = spec_region.strip()
    if stripped.startswith("(") and stripped.endswith(")"):
        open_index = spec_region.index("(")
        close_index = spec_region.rindex(")")
        return spec_region[: open_index + 1], spec_region[open_index + 1 : close_index], spec_region[close_index:]
    return "", spec_region, ""


def _parse_clauses(inner: str) -> list[_Clause] | None:
    if not inner.strip():
        return []
    clauses: list[_Clause] = []
    for part in inner.split(","):
        match = _CLAUSE_RE.match(part)
        if match is None or not match.group(4):
            return None
        clauses.append(
            _Clause(
                lead=match.group(1),
                operator=match.group(2),
                gap=match.group(3),
                version_text=match.group(4),
                trail=match.group(5),
            )
        )
    return clauses


def _effective_lower_bound(clauses: list[_Clause]) -> tuple[int | None, Version | None]:
    """Index and version of the highest existing lower-bound clause."""
    bound_index: int | None = None
    bound_version: Version | None = None
    for index, clause in enumerate(clauses):
        if clause.operator not in _LOWER_BOUND_OPERATORS:
            continue
        version = Version(clause.version_text)
        if bound_version is None or version > bound_version:
            bound_index, bound_version = index, version
    return bound_index, bound_version


def _floor_allowed(other_clauses: list[_Clause], floor: Version) -> bool:
    """True if ``floor`` satisfies every constraint other than the lower bound."""
    if not other_clauses:
        return True
    try:
        specifier_set = SpecifierSet(",".join(f"{c.operator}{c.version_text}" for c in other_clauses))
    except InvalidSpecifier:  # pragma: no cover - clauses came from a parsed requirement
        return False
    return specifier_set.contains(floor)
