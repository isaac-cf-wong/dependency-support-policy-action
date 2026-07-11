# Coexisting with Renovate

Renovate and this action own different halves of the problem — keep both:

| Concern                                                 | Owner       |
| ------------------------------------------------------- | ----------- |
| New upstream releases (bump upper ranges, lockfile)     | Renovate    |
| GitHub Actions, Docker, pre-commit, dev-tool updates    | Renovate    |
| Lockfile maintenance                                    | Renovate    |
| Rolling **lower-bound** policy (SPEC 0 support windows) | this action |
| `requires-python` floor                                 | this action |

Renovate does not implement time-based minimum-version policies; this action
never touches upper bounds or unmanaged ecosystems.

## Avoiding fights

- Keep Renovate's `rangeStrategy` at `"bump"` (raises upper constraints) or
  `"replace"` — not `"widen"` — for `pep621`, so Renovate does not rewrite
  your floors back.
- The PRs this action opens (via `create-pull-request`) use a dedicated
  branch (`dependency-support-policy/update`), which Renovate ignores.
- If you want Renovate to stay away from runtime lower bounds entirely,
  disable them explicitly:

```json
{
    "packageRules": [
        {
            "matchManagers": ["pep621"],
            "matchDepTypes": [
                "project.dependencies",
                "project.requires-python"
            ],
            "description": "Lower bounds owned by dependency-support-policy.",
            "enabled": false
        }
    ]
}
```

This repository's own
[`renovate.json`](https://github.com/isaac-cf-wong/dependency-support-policy-action/blob/main/renovate.json)
follows exactly this split: Renovate bumps only pre-commit hooks and
`dependency-groups`; the SPEC 0 workflow owns the runtime floors.
