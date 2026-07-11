# dependency-support-policy-action

Manage **rolling minimum-supported versions** for Python projects, as a
standalone CLI and a GitHub Action.

The tool reads dependency constraints from `pyproject.toml`, evaluates a
support policy — [Scientific Python SPEC 0](https://scientific-python.org/specs/spec-0000/)
is built in — against package release history, and raises dependency lower
bounds and the `requires-python` floor accordingly. Everything else in your
requirements (upper bounds, exclusions, extras, environment markers) and your
TOML formatting/comments is preserved character-for-character. Existing
minimums are never lowered.

## Quick start

=== "CLI"

    ```bash
    uvx dependency-support-policy check    # exit 1 if floors drifted below policy
    uvx dependency-support-policy plan     # machine-readable change plan (JSON)
    uvx dependency-support-policy update --lock minimal
    ```

=== "GitHub Action"

    ```yaml
    - uses: isaac-cf-wong/dependency-support-policy-action@v1
      id: policy
      with:
          mode: update # check | plan | update
          lock: minimal # off | minimal | upgrade
    ```

## Where to go next

- [Support-window model](user-guide/support-window-model.md) — how floors are
  computed, and what SPEC 0 means exactly.
- [Configuration](user-guide/configuration.md) — the
  `[tool.dependency-support-policy]` table and its precedence rules.
- [CLI](user-guide/cli.md) and [GitHub Action](user-guide/github-action.md) —
  modes, flags, inputs, and outputs.
- [Coexisting with Renovate](user-guide/renovate.md) — who owns which
  updates.
