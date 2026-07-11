# Support-Window Model

## How floors are computed

For every managed package, releases are grouped into **minor series**
(`major.minor`), each dated by its first stable release — prereleases, dev
releases, and yanked files are ignored.

A series is _supported_ at a reference date if its first release falls within
the support window: a number of calendar months looking back from the
reference date, **boundary inclusive**. The policy floor is the **first
version of the oldest supported series**.

Two edge rules keep the model total and reproducible:

- If every series is older than the window, the newest series is the floor,
  so at least one release line always remains supported.
- Series first released _after_ the reference date are ignored, which makes
  evaluation with an explicit `--reference-date` reproducible.

!!! example

    With a 24-month window evaluated on 2026-07-11 (cutoff 2024-07-11):
    tomlkit 0.13.0 was released 2024-07-10 — one day outside the window — so
    the 0.13 series is no longer supported and the floor moves to the first
    version of the oldest supported series, 0.14.0.

Calendar-month arithmetic clamps to month length (e.g. 2024-03-31 minus one
month is 2024-02-29).

## SPEC 0

The built-in `spec0` policy implements
[Scientific Python SPEC 0](https://scientific-python.org/specs/spec-0000/)
defaults:

| Scope    | Window    |
| -------- | --------- |
| Python   | 36 months |
| Packages | 24 months |

Both windows, and per-package windows, are
[configurable](configuration.md), so you can follow SPEC 0 strictly or run
"SPEC 0 with a 30-month window for numpy".

## Python floor

The `requires-python` lower bound is floored against a built-in table of
CPython minor-series release dates. When new CPython series ship, extend the
table via configuration:

```toml
[tool.dependency-support-policy.python-releases]
"3.15" = 2026-10-01
```

If `requires-python` is absent it is left absent (noted in the plan), and an
existing floor is never lowered.

## Extending with new policies

Policies are registered by name. Subclass
`dependency_support_policy.policies.SupportPolicy` and add the instance to
the registry — see the [API reference](../reference/index.md) and the
[contributing guide](../contributing.md).
