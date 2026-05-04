"""Target-tree cleanliness check + ``.agent/.sync.lock`` acquisition.

Both checks gate any disk write inside the target repo:

  - :func:`target_clean` runs ``git status --porcelain`` and refuses to
    proceed when the worktree carries uncommitted changes (caller may
    bypass with ``--allow-dirty``).
  - :func:`acquire_lock` writes a PID/timestamp lock atomically with
    ``O_CREAT|O_EXCL`` so two concurrent ``agent-sync`` invocations
    cannot race on the same target. Lock contents include source/target
    versions for postmortem debugging.
"""

from __future__ import annotations

import datetime as dt
import os

from .errors import LockError
from .git_ops import git_text


def target_clean(target):
    status = git_text(target, "status", "--porcelain")
    return status == ""


def acquire_lock(target, from_version, to_version):
    lock = target / ".agent" / ".sync.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    body = (
        f"pid={os.getpid()}\n"
        f"created_at={dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}\n"
        f"from={from_version}\n"
        f"to={to_version}\n"
    ).encode("utf-8")
    try:
        fd = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    except FileExistsError:
        try:
            contents = lock.read_text(encoding="utf-8")
        except OSError:
            contents = "<cannot read lock>"
        raise LockError(f"sync lock already exists at {lock}\n{contents}")
    with os.fdopen(fd, "wb") as fh:
        fh.write(body)
    return lock
