# Recommended CI

A floor is only honest if you test it. Recommended resolutions to run in CI:

- **Minimum versions**: `uv sync --upgrade --resolution lowest-direct` then
  run tests — every direct dependency is installed at exactly its lower
  bound, proving the floors actually work.
- **Latest versions**: `uv sync --upgrade` — proves you're compatible with
  current releases.
- **Locked** (your day-to-day resolution): `uv sync --frozen`.

## Example matrix

```yaml
strategy:
    matrix:
        python-version: ['3.12', '3.13', '3.14']
        os: [ubuntu-latest]
        resolution: [locked, lowest-direct, highest]
        include:
            - os: macos-latest
              python-version: '3.14'
              resolution: highest
steps:
    - uses: actions/checkout@v6
    - uses: astral-sh/setup-uv@v7
      with:
          python-version: ${{ matrix.python-version }}
    - name: Install dependencies
      env:
          RESOLUTION: ${{ matrix.resolution }}
      run: |
          case "$RESOLUTION" in
              locked) uv sync --group dev --frozen ;;
              lowest-direct) uv sync --group dev --upgrade --resolution lowest-direct ;;
              highest) uv sync --group dev --upgrade ;;
          esac
    - name: Run tests
      run: uv run --no-sync pytest
```

Notes:

- `--upgrade` forces re-resolution instead of reusing `uv.lock`; the re-lock
  happens only in the runner's ephemeral checkout.
- `uv run --no-sync` stops the test step from silently syncing back to the
  lockfile resolution.
- `--resolution lowest-direct` also floors your dev dependency group — a
  feature: it validates those floors too.
- Resolution behaviour is OS-independent, so running `lowest-direct` on a
  single OS is usually enough (this repository runs it on ubuntu only).
