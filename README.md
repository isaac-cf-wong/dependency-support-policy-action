# dependency-support-policy-action

[![CI](https://github.com/isaac-cf-wong/dependency-support-policy-action/actions/workflows/ci.yml/badge.svg)](https://github.com/isaac-cf-wong/dependency-support-policy-action/actions/workflows/ci.yml)
[![CodeQL](https://github.com/isaac-cf-wong/dependency-support-policy-action/actions/workflows/codeql.yml/badge.svg)](https://github.com/isaac-cf-wong/dependency-support-policy-action/actions/workflows/codeql.yml)
[![pre-commit.ci status](https://results.pre-commit.ci/badge/github/isaac-cf-wong/dependency-support-policy-action/main.svg)](https://results.pre-commit.ci/latest/github/isaac-cf-wong/dependency-support-policy-action/main)
[![PyPI Version](https://img.shields.io/pypi/v/dependency-support-policy)](https://pypi.org/project/dependency-support-policy/)
[![Python Versions](https://img.shields.io/pypi/pyversions/dependency-support-policy)](https://pypi.org/project/dependency-support-policy/)
[![License: BSD-3-Clause](https://img.shields.io/badge/License-BSD--3--Clause-blue.svg)](LICENSE)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![SPEC 0 — Minimum Supported Dependencies](https://img.shields.io/badge/SPEC-0-green?labelColor=%23004811&color=%235CA038)](https://scientific-python.org/specs/spec-0000/)

Manage **rolling minimum-supported versions** for Python projects, as a
standalone CLI and a GitHub Action.

The tool reads dependency constraints from `pyproject.toml`, evaluates a
support policy — [Scientific Python SPEC 0](https://scientific-python.org/specs/spec-0000/)
is built in — against package release history, and raises dependency lower
bounds and the `requires-python` floor accordingly. Everything else in your
requirements (upper bounds, exclusions, extras, environment markers) and your
TOML formatting/comments is preserved character-for-character. Existing
minimums are never lowered.

## How it works

### The support-window model

For every managed package, releases are grouped into **minor series**
(`major.minor`), each dated by its first stable release (prereleases, dev
releases, and yanked files are ignored). A series is _supported_ at a
reference date if its first release falls within the support window — a
number of calendar months looking back from the reference date, boundary
inclusive. The policy floor is the **first version of the oldest supported
series**. If every series is older than the window, the newest series is the
floor, so at least one release line always remains supported. Series released
_after_ the reference date are ignored, which makes evaluation with an
explicit `--reference-date` reproducible.

### SPEC 0

The built-in `spec0` policy implements Scientific Python SPEC 0 defaults:

- **Python**: support window 36 months — `requires-python` is floored at the
  oldest CPython minor series released within 3 years.
- **Packages**: support window 24 months.

Both windows, and per-package windows, are configurable (see below), so you
can follow SPEC 0 strictly, or run "SPEC 0 with a 30-month window for numpy".
The policy layer is extensible: additional named policies can be registered
in `dependency_support_policy.policies`.

## CLI usage

The CLI is published on PyPI as
[`dependency-support-policy`](https://pypi.org/project/dependency-support-policy/):

```bash
uvx dependency-support-policy check --reference-date 2026-07-01
uvx dependency-support-policy plan   # prints the machine-readable change plan (JSON)
uvx dependency-support-policy update --lock minimal
```

Modes:

| Mode     | Writes files | Exit codes                                  |
| -------- | ------------ | ------------------------------------------- |
| `check`  | never        | `0` compliant, `1` drift found, `2` error   |
| `plan`   | never        | `0` (prints plan JSON to stdout), `2` error |
| `update` | yes          | `0` success (even if no-op), `2` error      |

Common flags (all modes): `--pyproject PATH`, `--reference-date YYYY-MM-DD`,
`--policy spec0`, `--python-support-months N`, `--package-support-months N`,
`--package-override NAME=MONTHS`, `--include`/`--exclude NAMES`,
`--groups project,optional:docs,group:dev`, `--manage-python true|false`,
`--lock off|minimal|upgrade`, `--output-json PATH`, `--quiet`.

## Configuration

Defaults live in `pyproject.toml`; CLI flags / action inputs override them.

```toml
[tool.dependency-support-policy]
policy = "spec0"
python-support-months = 36           # override the policy's Python window
package-support-months = 24          # override the policy's package window
groups = ["project", "optional:sgwb"] # dependency collections to manage
include = []                          # if non-empty, only these packages
exclude = ["some-fast-moving-lib"]
manage-python = true
lock = "off"                          # off | minimal | upgrade

[tool.dependency-support-policy.package-support]
numpy = 30                            # per-package window, in months

[tool.dependency-support-policy.python-releases]
"3.15" = 2026-10-01                   # extend the built-in CPython table
```

Managed dependency collections (`groups`): `project`
(`project.dependencies`), `optional:<extra>`, `group:<dependency-group>`, or
the shorthands `optional`, `group`, and `all`.

## GitHub Action

```yaml
- uses: isaac-cf-wong/dependency-support-policy-action@v1
  id: policy
  with:
      mode: update # check | plan | update
      lock: minimal # off | minimal | upgrade
```

### Inputs

| Input                    | Default          | Description                                            |
| ------------------------ | ---------------- | ------------------------------------------------------ |
| `mode`                   | `check`          | `check`, `plan`, or `update`.                          |
| `working-directory`      | `.`              | Directory containing the project.                      |
| `pyproject`              | `pyproject.toml` | Path to `pyproject.toml`, relative to the directory.   |
| `reference-date`         | today            | Evaluate windows as of this date (reproducible runs).  |
| `policy`                 | `spec0`          | Support policy.                                        |
| `python-support-months`  | policy default   | Python support window override.                        |
| `package-support-months` | policy default   | Package support window override.                       |
| `package-overrides`      | —                | Newline-separated `name=months` per-package windows.   |
| `include` / `exclude`    | —                | Comma-separated package names.                         |
| `groups`                 | `project`        | Comma-separated dependency collections.                |
| `manage-python`          | `true`           | Manage the `requires-python` floor.                    |
| `lock`                   | `off`            | uv.lock regeneration mode.                             |
| `fail-on-outdated`       | `true`           | In `check` mode, fail the step when drift is detected. |

### Outputs

| Output                      | Description                                                      |
| --------------------------- | ---------------------------------------------------------------- |
| `changed`                   | `true` if any floor is below policy (check/plan) or was updated. |
| `python-floor-changed`      | `true` if `requires-python` changed (or would change).           |
| `dependency-floors-changed` | JSON list of `{name, group, old, new}` floor changes.            |
| `files-changed`             | JSON list of files written (update mode).                        |
| `plan`                      | Full machine-readable change plan (JSON).                        |

### Permissions

The action itself only edits files in the workspace — it needs no secrets and
works with the default `contents: read`. Workflows that push a branch and
open a PR (see the examples) need `contents: write` and `pull-requests: write`
for the `create-pull-request` step, and PR creation by Actions must be
allowed in the repository settings (_Settings → Actions → General → Allow
GitHub Actions to create and approve pull requests_).

### Example workflows

Ready-to-copy workflows live in [`examples/workflows/`](examples/workflows):

- [`scheduled-floor-update.yml`](examples/workflows/scheduled-floor-update.yml) —
  monthly floor bump, PR via `peter-evans/create-pull-request`.
- [`pr-compliance-check.yml`](examples/workflows/pr-compliance-check.yml) —
  fail pull requests whose floors drifted below the policy.
- [`update-with-lockfile.yml`](examples/workflows/update-with-lockfile.yml) —
  update `pyproject.toml` **and** `uv.lock` in a single PR.

## uv.lock handling

With `lock: minimal` (recommended), `uv lock` re-locks after the pyproject
edit — uv only changes what the new floors require. With `lock: upgrade`,
`uv lock --upgrade` refreshes everything (usually better left to Renovate's
lockfile maintenance). If regeneration fails, **both** `pyproject.toml` and
`uv.lock` are rolled back to their previous contents and the run fails; if no
`uv.lock` exists, regeneration is skipped with a note. `uv` must be on `PATH`
for the CLI (the action installs it).

## Coexisting with Renovate

Renovate and this action own different halves of the problem — keep both:

| Concern                                                 | Owner       |
| ------------------------------------------------------- | ----------- |
| New upstream releases (bump upper ranges, lockfile)     | Renovate    |
| GitHub Actions, Docker, pre-commit, dev-tool updates    | Renovate    |
| Lockfile maintenance                                    | Renovate    |
| Rolling **lower-bound** policy (SPEC 0 support windows) | this action |
| `requires-python` floor                                 | this action |

Renovate does not implement time-based minimum-version policies; this action
never touches upper bounds or unmanaged ecosystems. To avoid Renovate
"fixing" your floors back, keep `rangeStrategy` at `"bump"` (raises upper
constraints) or `"replace"` — not `"widen"` — for `pep621`. The PRs this
action opens (via `create-pull-request`) use a dedicated branch
(`dependency-support-policy/update`), which Renovate ignores.

## Recommended CI for floors

A floor is only honest if you test it. Recommended matrix:

- **Minimum versions**: `uv sync --resolution lowest-direct` then run tests —
  proves the floors actually work.
- **Latest versions**: `uv sync --upgrade` (or Renovate-maintained lockfile) —
  proves you're compatible with current releases.

## Known limitations

- Only PEP 508 requirement strings in `project.dependencies`,
  `project.optional-dependencies`, and `[dependency-groups]` are managed;
  `tool.uv.sources`, path/URL dependencies, and non-PyPI indexes are not.
- Pinned requirements (`==`, `===`, `~=`) are reported and skipped, never
  rewritten.
- A policy floor that conflicts with an existing upper bound or exclusion is
  reported and skipped — resolve the conflict manually.
- Release metadata comes from the PyPI JSON API; private registries are not
  supported yet (registry failures abort the run with exit code 2).
- Trove classifiers (`Programming Language :: Python :: 3.x`) are not
  updated when the Python floor moves.
- The CPython release table is built in; extend it via
  `[tool.dependency-support-policy.python-releases]` when new series ship.

## Development

```bash
uv sync --all-groups
uv run prek run --all-files
uv run pytest
uv run mypy src
uv build
```

See [CONTRIBUTING.md](CONTRIBUTING.md). Released under the
[BSD 3-Clause License](LICENSE).
