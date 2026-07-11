# Configuration

Defaults live in `pyproject.toml` under `[tool.dependency-support-policy]`;
CLI flags and action inputs override them.

```toml
[tool.dependency-support-policy]
policy = "spec0"
python-support-months = 36            # override the policy's Python window
package-support-months = 24           # override the policy's package window
groups = ["project"]                  # dependency collections to manage
include = []                          # if non-empty, only these packages
exclude = ["some-fast-moving-lib"]
manage-python = true
lock = "off"                          # off | minimal | upgrade

[tool.dependency-support-policy.package-support]
numpy = 30                            # per-package window, in months

[tool.dependency-support-policy.python-releases]
"3.15" = 2026-10-01                   # extend the built-in CPython table
```

## Keys

| Key                      | Type   | Default       | Meaning                                        |
| ------------------------ | ------ | ------------- | ---------------------------------------------- |
| `policy`                 | string | `"spec0"`     | Support policy providing the default windows.  |
| `python-support-months`  | int    | policy        | Python support window (calendar months).       |
| `package-support-months` | int    | policy        | Default package support window.                |
| `package-support`        | table  | `{}`          | Per-package windows, `name = months`.          |
| `groups`                 | array  | `["project"]` | Dependency collections to manage (see below).  |
| `include`                | array  | all           | If non-empty, only these packages are managed. |
| `exclude`                | array  | `[]`          | Packages never touched.                        |
| `manage-python`          | bool   | `true`        | Manage the `requires-python` floor.            |
| `lock`                   | string | `"off"`       | uv.lock handling after updates.                |
| `python-releases`        | table  | `{}`          | Extra CPython series, `"3.x" = date`.          |

Package names are compared case-insensitively with PEP 503 normalization
(`My_Package` matches `my-package`).

Unknown keys, wrong types, non-positive windows, and unknown lock modes are
rejected with exit code 2, so configuration typos fail loudly.

## Dependency collections (`groups`)

| Selector          | Manages                                      |
| ----------------- | -------------------------------------------- |
| `project`         | `project.dependencies`                       |
| `optional:<name>` | one extra in `project.optional-dependencies` |
| `optional`        | every extra                                  |
| `group:<name>`    | one group in `[dependency-groups]`           |
| `group`           | every dependency group                       |
| `all`             | everything above                             |

Non-string entries (such as `{include-group = "..."}`) are skipped.
Explicitly named collections that do not exist are a configuration error.

## Precedence

CLI flags (or action inputs, which map onto them) win over the tool table,
which wins over the policy defaults.
