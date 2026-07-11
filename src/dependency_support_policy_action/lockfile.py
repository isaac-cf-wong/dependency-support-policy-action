"""uv lockfile regeneration with rollback on failure."""

from __future__ import annotations

import subprocess
from pathlib import Path

from .config import LockMode
from .errors import LockfileError

_UV_TIMEOUT_SECONDS = 600.0


def regenerate_lockfile(project_dir: Path, mode: LockMode, *, uv_executable: str = "uv") -> bool:
    """Run ``uv lock`` in ``project_dir``; return True if uv.lock content changed.

    ``LockMode.MINIMAL`` performs the default minimal re-lock; ``LockMode.UPGRADE``
    passes ``--upgrade``. Raises :class:`LockfileError` on failure — the caller
    is responsible for rolling back file snapshots.
    """
    if mode is LockMode.OFF:
        return False
    lock_path = project_dir / "uv.lock"
    before = lock_path.read_bytes() if lock_path.exists() else None
    command = [uv_executable, "lock"]
    if mode is LockMode.UPGRADE:
        command.append("--upgrade")
    try:
        completed = subprocess.run(  # noqa: S603 - fixed argument list, no shell
            command,
            cwd=project_dir,
            capture_output=True,
            text=True,
            timeout=_UV_TIMEOUT_SECONDS,
            check=False,
        )
    except FileNotFoundError as exc:
        raise LockfileError(f"uv executable not found: {uv_executable!r}") from exc
    except subprocess.TimeoutExpired as exc:
        raise LockfileError(f"'{' '.join(command)}' timed out after {_UV_TIMEOUT_SECONDS:.0f}s") from exc
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()
        raise LockfileError(f"'{' '.join(command)}' failed with exit code {completed.returncode}:\n{detail}")
    after = lock_path.read_bytes() if lock_path.exists() else None
    return after != before
