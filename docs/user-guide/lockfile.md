# uv.lock Handling

With `lock: minimal` (recommended), `uv lock` re-locks after the pyproject
edit — uv only changes what the new floors require. With `lock: upgrade`,
`uv lock --upgrade` refreshes everything (usually better left to Renovate's
lockfile maintenance). The default is `off`: `uv.lock` is not touched.

## Failure and rollback

If lockfile regeneration fails — no satisfying resolution, network trouble,
missing `uv` — **both** `pyproject.toml` and `uv.lock` are restored to their
previous contents and the run fails with exit code 2. A failed update never
leaves the repository half-edited.

## Notes

- If no `uv.lock` exists, regeneration is skipped with a note in the plan; a
  lockfile is never created from scratch.
- `uv` must be on `PATH` for the CLI; the GitHub Action installs it.
- All file writes are atomic (write temp file, then rename).
