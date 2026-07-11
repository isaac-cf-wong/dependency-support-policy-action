"""Allow ``python -m dependency_support_policy_action``."""

from __future__ import annotations

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
