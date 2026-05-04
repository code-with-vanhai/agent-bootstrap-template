"""Exit codes, semver regex, and the ``SyncError`` exception hierarchy.

Centralized so every other ``agent_sync`` module raises typed errors with
stable exit codes. The shim at ``scripts/agent-sync.py`` catches
:class:`SyncError` and exits with ``exc.exit_code``; the migration test
fixtures assert specific codes (``EXIT_DIRTY``, ``EXIT_CONFLICT`` etc.)
so this contract is load-bearing.
"""

from __future__ import annotations

import re

EXIT_USAGE = 2
EXIT_DIRTY = 10
EXIT_CONFLICT = 20
EXIT_VALIDATION = 30
EXIT_NO_PATH = 40
EXIT_LOCKED = 50

VERSION_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+(-[0-9A-Za-z.-]+)?$")


class SyncError(Exception):
    exit_code = 1


class UsageError(SyncError):
    exit_code = EXIT_USAGE


class DirtyError(SyncError):
    exit_code = EXIT_DIRTY


class ConflictError(SyncError):
    exit_code = EXIT_CONFLICT


class NoPathError(SyncError):
    exit_code = EXIT_NO_PATH


class LockError(SyncError):
    exit_code = EXIT_LOCKED
