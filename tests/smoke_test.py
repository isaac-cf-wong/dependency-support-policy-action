"""Pre-publish smoke checks, run against the built wheel/sdist in isolation.

Invoked as a script (not via pytest):

    uv run --isolated --no-project --with dist/*.whl tests/smoke_test.py

The check functions deliberately do not follow pytest naming so the normal
test run does not collect them (they assert the package is imported from an
installed distribution, which is false in the editable dev environment).
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

import dependency_support_policy


def check_import_location() -> None:
    print(f"Python version: {sys.version}")
    print(f"Package version: {dependency_support_policy.__version__}")
    location = dependency_support_policy.__file__ or ""
    assert "site-packages" in location, f"package imported from unexpected location: {location}"


def check_cli_version() -> None:
    result = subprocess.run(
        ["dependency-support-policy", "--version"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "dependency-support-policy" in result.stdout


def check_cli_functional() -> None:
    """Run a full check offline: no dependencies, python floor unmanaged."""
    with tempfile.TemporaryDirectory() as tmp:
        pyproject = Path(tmp) / "pyproject.toml"
        pyproject.write_text(
            '[project]\nname = "smoke"\nversion = "0.1.0"\ndependencies = []\n',
            encoding="utf-8",
        )
        result = subprocess.run(
            [
                "dependency-support-policy",
                "check",
                "--pyproject",
                str(pyproject),
                "--reference-date",
                "2025-01-01",
                "--manage-python",
                "false",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        assert "comply with the policy" in result.stdout


def main() -> int:
    check_import_location()
    check_cli_version()
    check_cli_functional()
    print("smoke tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
