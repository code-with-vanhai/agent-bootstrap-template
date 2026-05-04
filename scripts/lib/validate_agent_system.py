#!/usr/bin/env python3
"""Compatibility shim for the modular agent-system validator.

The implementation now lives under
``scripts/lib/agent_system_validation/``. This file is kept so that
existing entrypoints (``scripts/agent-validate.sh`` and downstream
generated repos) continue to work without changes.
"""

from __future__ import annotations

try:
    from .agent_system_validation import *  # type: ignore  # noqa: F401,F403
    from .agent_system_validation.cli import main
except ImportError:
    # Executed as `python3 scripts/lib/validate_agent_system.py`; sys.path
    # points at scripts/lib, so import the sibling package directly.
    from agent_system_validation import *  # type: ignore  # noqa: F401,F403
    from agent_system_validation.cli import main


if __name__ == "__main__":
    raise SystemExit(main())
