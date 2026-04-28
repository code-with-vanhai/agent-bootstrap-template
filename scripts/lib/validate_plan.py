#!/usr/bin/env python3
"""Compatibility wrapper for the modular plan validator.

Public imports from `scripts.lib.validate_plan` are intentionally preserved.
The implementation now lives under `scripts.lib.plan_validation`.
"""

from __future__ import annotations

try:
    from .plan_validation import *  # type: ignore  # noqa: F401,F403
    from .plan_validation.cli import main
except ImportError:
    # Executed as `python3 scripts/lib/validate_plan.py`; sys.path points at
    # scripts/lib, so import the sibling package directly.
    from plan_validation import *  # type: ignore  # noqa: F401,F403
    from plan_validation.cli import main


if __name__ == "__main__":
    raise SystemExit(main())
