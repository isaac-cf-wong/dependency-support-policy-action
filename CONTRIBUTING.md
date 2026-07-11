# Contributing

Thanks for considering a contribution! This project follows a
[Code of Conduct](https://github.com/isaac-cf-wong/dependency-support-policy-action/blob/main/CODE_OF_CONDUCT.md)
— by participating you agree to uphold it.

## Development setup

```bash
git clone https://github.com/isaac-cf-wong/dependency-support-policy-action
cd dependency-support-policy-action
uv sync --all-groups
uv run prek install
```

## Canonical checks

All of these must pass before a change is merged (CI runs the same):

```bash
uv run prek run --all-files
uv run pytest
uv run mypy src
uv build
```

Unit tests mock the package registry; the GitHub Actions integration tests in
`.github/workflows/ci.yml` run the local action against the fixture projects
in `tests/data/action/` (these hit the real PyPI JSON API with a fixed
`reference-date`, so results are reproducible).

## Commit and PR conventions

- Commit messages and PR titles follow
  [Conventional Commits](https://www.conventionalcommits.org/) (`feat:`,
  `fix:`, `docs:`, `chore:`...). PR titles are linted.
- The changelog is generated from commits by git-cliff — write messages you
  would want to read in release notes.

## Release process

- Every push to `main` refreshes the **draft release** (`next-release`).
- A **scheduled release** runs every Tuesday: if there are new commits since
  the last tag, CI and CodeQL are re-run, a semver tag is derived from the
  conventional commits, the GitHub release is published, and the floating
  major tag (e.g. `v1`) is moved.
- The static `version` in `pyproject.toml` is cosmetic; release versions come
  from git tags.

## Adding a support policy

1. Subclass `SupportPolicy` in
   `src/dependency_support_policy/policies.py` and register it in
   `_POLICIES`.
2. Add tests for its windows and floor behaviour.
3. Document it in the README.
