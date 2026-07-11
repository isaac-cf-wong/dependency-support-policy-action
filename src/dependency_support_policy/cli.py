"""Command-line interface: check, plan, and update modes.

Exit codes: 0 = compliant / success, 1 = drift found (check mode only),
2 = configuration, registry, or lockfile error.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import uuid
from collections.abc import Sequence
from pathlib import Path
from typing import Any, TextIO

from . import __version__
from .config import LockMode, load_config
from .dates import parse_iso_date
from .errors import ConfigError, DependencyPolicyError
from .planner import ApplyResult, ChangePlan, apply_plan, build_plan
from .policies import available_policies
from .pyproject_edit import load_document
from .registry import PyPIReleaseFetcher, ReleaseFetcher

EXIT_OK = 0
EXIT_DRIFT = 1
EXIT_ERROR = 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dependency-support-policy",
        description="Manage rolling minimum-supported versions for Python projects.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="mode", required=True, metavar="{check,plan,update}")
    modes = {
        "check": "Report drift; exit 1 if any floor is below the policy.",
        "plan": "Print the machine-readable change plan as JSON; never writes.",
        "update": "Apply floor updates to pyproject.toml (and uv.lock if configured).",
    }
    for mode, help_text in modes.items():
        sub = subparsers.add_parser(mode, help=help_text, description=help_text)
        _add_common_arguments(sub)
    return parser


def _add_common_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--pyproject", type=Path, default=Path("pyproject.toml"), help="Path to pyproject.toml.")
    parser.add_argument(
        "--reference-date",
        default=None,
        help="Evaluate support windows as of this date (YYYY-MM-DD); defaults to today (UTC).",
    )
    parser.add_argument("--policy", default=None, choices=available_policies(), help="Support policy to apply.")
    parser.add_argument("--python-support-months", type=int, default=None, help="Override the Python support window.")
    parser.add_argument(
        "--package-support-months", type=int, default=None, help="Override the default package support window."
    )
    parser.add_argument(
        "--package-override",
        action="append",
        default=None,
        metavar="NAME=MONTHS",
        help="Per-package support window (repeatable).",
    )
    parser.add_argument(
        "--include",
        action="append",
        default=None,
        metavar="NAMES",
        help="Only manage these packages (comma separated, repeatable).",
    )
    parser.add_argument(
        "--exclude",
        action="append",
        default=None,
        metavar="NAMES",
        help="Never touch these packages (comma separated, repeatable).",
    )
    parser.add_argument(
        "--groups",
        default=None,
        help="Comma-separated dependency collections to manage: project, optional[:name], group[:name], all.",
    )
    parser.add_argument(
        "--manage-python",
        default=None,
        choices=("true", "false"),
        help="Whether to manage the requires-python floor (default: true).",
    )
    parser.add_argument(
        "--lock",
        default=None,
        choices=[mode.value for mode in LockMode],
        help="uv.lock handling after updates (default: off).",
    )
    parser.add_argument("--output-json", type=Path, default=None, help="Also write the change plan JSON to this file.")
    parser.add_argument("--quiet", action="store_true", help="Suppress the human-readable summary.")


def _split_names(values: Sequence[str] | None) -> list[str] | None:
    if values is None:
        return None
    names = [name.strip() for value in values for name in value.split(",") if name.strip()]
    return names


def _parse_override_flags(values: Sequence[str] | None) -> dict[str, int] | None:
    if values is None:
        return None
    overrides: dict[str, int] = {}
    for value in values:
        name, separator, months = value.partition("=")
        if not separator or not name.strip():
            raise ConfigError(f"invalid --package-override {value!r}: expected NAME=MONTHS")
        try:
            overrides[name.strip()] = int(months)
        except ValueError:
            raise ConfigError(f"invalid --package-override {value!r}: MONTHS must be an integer") from None
    return overrides


def _cli_overrides(args: argparse.Namespace) -> dict[str, Any]:
    manage_python = None if args.manage_python is None else args.manage_python == "true"
    groups = None
    if args.groups is not None:
        groups = [token.strip() for token in args.groups.split(",") if token.strip()]
    return {
        "policy_name": args.policy,
        "python_support_months": args.python_support_months,
        "package_support_months": args.package_support_months,
        "package_overrides": _parse_override_flags(args.package_override),
        "include": _split_names(args.include),
        "exclude": _split_names(args.exclude),
        "groups": groups,
        "manage_python": manage_python,
        "lock": args.lock,
    }


def _summarize(plan: ChangePlan, mode: str, apply_result: ApplyResult | None, stream: TextIO) -> None:
    print(f"policy: {plan.policy} (reference date {plan.reference_date.isoformat()})", file=stream)
    if not plan.changed:
        print("all managed floors comply with the policy", file=stream)
    for change in plan.dependency_changes:
        print(f"  {change.group}: {change.old_requirement!r} -> {change.new_requirement!r}", file=stream)
    if plan.python_change is not None:
        print(
            f"  requires-python: {plan.python_change.old_requires_python!r} -> "
            f"{plan.python_change.new_requires_python!r}",
            file=stream,
        )
    for skipped in plan.skipped:
        print(f"  skipped {skipped.requirement!r}: {skipped.reason}", file=stream)
    for note in plan.notes:
        print(f"  note: {note}", file=stream)
    if mode == "update" and apply_result is not None:
        if apply_result.changed_files:
            print(f"updated files: {', '.join(apply_result.changed_files)}", file=stream)
        else:
            print("no files changed", file=stream)


def _write_github_outputs(plan: ChangePlan, apply_result: ApplyResult | None) -> None:
    output_path = os.environ.get("GITHUB_OUTPUT")
    if not output_path:
        return
    floors_changed = [
        {"name": change.name, "group": change.group, "old": change.old_floor, "new": change.new_floor}
        for change in plan.dependency_changes
    ]
    changed_files = apply_result.changed_files if apply_result is not None else []
    values = {
        "changed": str(plan.changed).lower(),
        "python-floor-changed": str(plan.python_change is not None).lower(),
        "dependency-floors-changed": json.dumps(floors_changed),
        "files-changed": json.dumps(changed_files),
        "plan": json.dumps(plan.to_dict()),
    }
    with open(output_path, "a", encoding="utf-8") as handle:
        for key, value in values.items():
            delimiter = f"dspa-{uuid.uuid4()}"
            handle.write(f"{key}<<{delimiter}\n{value}\n{delimiter}\n")


def main(argv: Sequence[str] | None = None, *, fetcher: ReleaseFetcher | None = None) -> int:
    """CLI entry point; ``fetcher`` is injectable for tests."""
    args = build_parser().parse_args(argv)
    try:
        reference_date = (
            parse_iso_date(args.reference_date) if args.reference_date is not None else dt.datetime.now(dt.UTC).date()
        )
        document = load_document(args.pyproject)
        config = load_config(args.pyproject, document, reference_date, _cli_overrides(args))
        plan = build_plan(document, config, fetcher if fetcher is not None else PyPIReleaseFetcher())
        apply_result = apply_plan(document, plan, config) if args.mode == "update" else None
    except DependencyPolicyError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR

    plan_json = json.dumps(plan.to_dict(), indent=2)
    if args.output_json is not None:
        args.output_json.write_text(plan_json + "\n", encoding="utf-8")
    if args.mode == "plan":
        print(plan_json)
    elif not args.quiet:
        _summarize(plan, args.mode, apply_result, sys.stdout)
    _write_github_outputs(plan, apply_result)

    if args.mode == "check" and plan.changed:
        return EXIT_DRIFT
    return EXIT_OK


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
