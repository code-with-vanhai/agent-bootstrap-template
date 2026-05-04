#!/usr/bin/env python3
"""Compatibility shim for the modular agent-sync runner.

The implementation now lives under ``scripts/lib/agent_sync/``. This
file is kept so that existing entrypoints (``scripts/agent-sync.sh``,
direct ``python3 scripts/agent-sync.py`` invocations from migration
fixtures) continue to work without changes.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Allow ``python3 scripts/agent-sync.py ...`` to find the sibling package
# under ``scripts/lib/`` without requiring the caller to set PYTHONPATH.
_SCRIPTS_LIB = Path(__file__).resolve().parent / "lib"
if str(_SCRIPTS_LIB) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_LIB))

from agent_sync.cli import main_with_exit  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main_with_exit(sys.argv[1:]))
