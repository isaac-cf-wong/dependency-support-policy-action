# Known Limitations

- Only PEP 508 requirement strings in `project.dependencies`,
  `project.optional-dependencies`, and `[dependency-groups]` are managed;
  `tool.uv.sources`, path/URL dependencies, and non-PyPI indexes are not.
- Pinned requirements (`==`, `===`, `~=`) are reported and skipped, never
  rewritten.
- A policy floor that conflicts with an existing upper bound or exclusion is
  reported and skipped — resolve the conflict manually.
- Release metadata comes from the PyPI JSON API; private registries are not
  supported yet. Registry failures abort the run with exit code 2 —
  deterministic, but a single unreachable package fails the whole run.
- When the Python floor moves, stale `Programming Language :: Python :: X.Y`
  classifiers are removed, but new series are not added. Workflow files are
  edited only in the `.github/workflows` directory beside `pyproject.toml` (a
  shared workflow at a monorepo root is never touched, nor are symlinked files), and multi-line flow lists that contain
  comments are reported in the plan notes instead of rewritten.
- The CPython release table is built in; extend it via
  `[tool.dependency-support-policy.python-releases]` when new series ship.
  A plan note warns when the table looks stale relative to the reference
  date.
- Version grouping assumes `major.minor` series semantics. Packages using
  calendar or single-number versioning are grouped as `(major, 0)`, which
  makes the window coarser for them.
