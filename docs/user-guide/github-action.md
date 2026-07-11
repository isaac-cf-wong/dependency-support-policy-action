# GitHub Action

```yaml
- uses: isaac-cf-wong/dependency-support-policy-action@v1
  id: policy
  with:
      mode: update # check | plan | update
      lock: minimal # off | minimal | upgrade
```

The action is a composite that installs [uv](https://docs.astral.sh/uv/) and
runs the [CLI](cli.md); every input maps onto a CLI flag, and configuration
in `[tool.dependency-support-policy]` applies equally.

## Inputs

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

## Outputs

| Output                      | Description                                                      |
| --------------------------- | ---------------------------------------------------------------- |
| `changed`                   | `true` if any floor is below policy (check/plan) or was updated. |
| `python-floor-changed`      | `true` if `requires-python` changed (or would change).           |
| `dependency-floors-changed` | JSON list of `{name, group, old, new}` floor changes.            |
| `files-changed`             | JSON list of files written (update mode).                        |
| `plan`                      | Full machine-readable change plan (JSON).                        |

## Permissions

The action itself only edits files in the workspace — it needs no secrets and
works with the default `contents: read`. Workflows that push a branch and
open a PR (see the examples) need `contents: write` and `pull-requests: write`
for the `create-pull-request` step, and PR creation by Actions must be
allowed in the repository settings (_Settings → Actions → General → Allow
GitHub Actions to create and approve pull requests_).

## Example workflows

Ready-to-copy workflows live in
[`examples/workflows/`](https://github.com/isaac-cf-wong/dependency-support-policy-action/tree/main/examples/workflows):

- `scheduled-floor-update.yml` — monthly floor bump, PR via
  `peter-evans/create-pull-request`.
- `pr-compliance-check.yml` — fail pull requests whose floors drifted below
  the policy.
- `update-with-lockfile.yml` — update `pyproject.toml` **and** `uv.lock` in a
  single PR.

This repository [dogfoods the action](https://github.com/isaac-cf-wong/dependency-support-policy-action/blob/main/.github/workflows/support_floor_update.yml)
with a monthly floor-update workflow.
