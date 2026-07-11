# Ecosystem Packages: Latest Floors

Not every dependency should get a time-window floor. A project often depends
on two kinds of packages:

- **Foundational packages** (e.g. `numpy`, `scipy`) — widely used, stable
  release lines, where supporting a rolling window of older versions is the
  community-friendly default. This is what SPEC 0 windows are for.
- **Ecosystem packages** — sibling packages from your own project family
  (e.g. `yourproject-core`, `yourproject-plugins`) that are released in
  lockstep and where you always want the **latest release as the floor**,
  because old combinations are never meant to be supported.

"Latest as floor" is not a support window — it is a version bump on every
release. That is Renovate's job, and the two tools compose cleanly.

## Recommended setup

Let Renovate bump the ecosystem floors and let this action manage the
foundational ones:

```json
{
    "rangeStrategy": "bump",
    "packageRules": [
        {
            "matchManagers": ["pep621"],
            "matchDepTypes": ["project.dependencies"],
            "matchPackageNames": ["numpy", "scipy"],
            "description": "Foundational floors owned by dependency-support-policy.",
            "enabled": false
        },
        {
            "matchDatasources": ["python-version"],
            "description": "requires-python owned by dependency-support-policy.",
            "enabled": false
        }
    ]
}
```

With `rangeStrategy: "bump"`, every new `yourproject-core` release produces a
Renovate PR raising the floor, e.g. `yourproject-core>=1.4.2` →
`>=1.5.0` — the floor tracks latest. The first rule scopes the Renovate
disable to the foundational packages only, instead of disabling all of
`project.dependencies`.

## Why the two tools do not fight

- This action **never lowers** an existing floor. A Renovate-bumped floor is
  always at or above the policy floor, so the action reports those packages
  as compliant and leaves them alone.
- The action only ever touches lower bounds; Renovate's other work (upper
  bounds, lockfile, dev tooling) is unaffected.

Optionally, list the ecosystem packages in the action's `exclude` for
explicitness — it changes nothing in behaviour, but documents the ownership
split in `pyproject.toml`:

```toml
[tool.dependency-support-policy]
exclude = ["yourproject-core", "yourproject-plugins"]
```

## Testing both floors

The [recommended CI setup](ci-recommendations.md) covers this split too:
`--resolution lowest-direct` installs the ecosystem packages at exactly the
latest-release floor Renovate wrote and the foundational packages at their
window floors — proving the declared combination actually works.
