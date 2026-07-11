# CLI

The CLI is published on PyPI as
[`dependency-support-policy`](https://pypi.org/project/dependency-support-policy/):

```bash
uvx dependency-support-policy check --reference-date 2026-07-11
```

## Modes

| Mode     | Writes files | Exit codes                                  |
| -------- | ------------ | ------------------------------------------- |
| `check`  | never        | `0` compliant, `1` drift found, `2` error   |
| `plan`   | never        | `0` (prints plan JSON to stdout), `2` error |
| `update` | yes          | `0` success (even if no-op), `2` error      |

Exit code `2` covers configuration errors, registry failures, and lockfile
regeneration failures.

## Flags

All modes accept the same flags:

| Flag                         | Meaning                                                       |
| ---------------------------- | ------------------------------------------------------------- |
| `--pyproject PATH`           | Path to `pyproject.toml` (default `./pyproject.toml`).        |
| `--reference-date DATE`      | Evaluate windows as of `YYYY-MM-DD`; defaults to today (UTC). |
| `--policy NAME`              | Support policy (currently `spec0`).                           |
| `--python-support-months N`  | Override the Python window.                                   |
| `--package-support-months N` | Override the default package window.                          |
| `--package-override N=M`     | Per-package window (repeatable).                              |
| `--include NAMES`            | Only manage these packages (comma separated, repeatable).     |
| `--exclude NAMES`            | Never touch these packages.                                   |
| `--groups LIST`              | Dependency collections to manage.                             |
| `--manage-python true/false` | Manage the `requires-python` floor.                           |
| `--lock off/minimal/upgrade` | uv.lock handling after updates.                               |
| `--output-json PATH`         | Also write the change plan JSON to a file.                    |
| `--quiet`                    | Suppress the human-readable summary.                          |

## Reproducible evaluation

Support windows move with time. Pin `--reference-date` to make a run
reproducible — the same date always produces the same floors, because
releases published after the reference date are ignored.

## The change plan

`plan` mode (and `--output-json` in any mode) emits a machine-readable plan:

```json
{
    "reference_date": "2026-07-11",
    "policy": "spec0",
    "changed": true,
    "dependency_changes": [
        {
            "group": "project",
            "name": "tomlkit",
            "old_requirement": "tomlkit>=0.13.2",
            "new_requirement": "tomlkit>=0.14.0",
            "old_floor": "0.13.2",
            "new_floor": "0.14.0"
        }
    ],
    "python_change": {
        "old_requires_python": ">=3.11",
        "new_requires_python": ">=3.12",
        "old_floor": "3.11",
        "new_floor": "3.12"
    },
    "skipped": [],
    "notes": []
}
```

`skipped` lists requirements the policy could not rewrite (pinned, direct
URL, conflicting constraints, ...) with a reason each; `notes` carries
non-fatal observations such as a missing `requires-python`.
