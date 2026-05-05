"""Target-tree cleanliness check, lock acquisition, and preflight summary.

Preflight responsibilities:

  - :func:`target_clean` runs ``git status --porcelain`` and refuses to
    proceed when the worktree carries uncommitted changes (caller may
    bypass with ``--allow-dirty``).
  - :func:`acquire_lock` writes a PID/timestamp lock atomically with
    ``O_CREAT|O_EXCL`` so two concurrent ``agent-sync`` invocations
    cannot race on the same target. Lock contents include source/target
    versions for postmortem debugging.
  - :func:`render_preflight` (Stage 1.2) prints a per-run summary block
    derived from ``expand_file_entries`` so the user sees customized /
    new / deleted counts before any disk write. Output is suppressed
    when stdout is not a TTY and ``--verbose`` is not set so CI logs
    stay short.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import os
import sys
from pathlib import Path

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


def _sha256_file(path):
    try:
        data = path.read_bytes()
    except FileNotFoundError:
        return None
    return hashlib.sha256(data).hexdigest()


def _classify_entry(entry, target, template_root, from_version):
    """Classify one expand_file_entries entry as untouched/customized/new/deleted.

    Pure read; never writes. ``compute_base_sha`` is local-imported to
    avoid a circular import via :mod:`merge`.
    """

    from .merge import compute_base_sha  # noqa: WPS433

    target_path = target / entry["target"]
    current_sha = _sha256_file(target_path)
    base_sha = compute_base_sha(entry, template_root, from_version)

    if current_sha is None and base_sha is None:
        return "new"
    if current_sha is None and base_sha is not None:
        return "deleted"
    if base_sha is None:
        # File exists locally but template did not have it at v<from>
        # (e.g. user-created or a path that only landed in v<to>).
        return "new"
    if current_sha == base_sha:
        return "untouched"
    return "customized"


def render_preflight(
    *,
    target,
    template_root,
    current_version,
    to_version,
    chain_versions,
    entries,
    backup_enabled,
    worktree_clean,
    write_count=None,
    patch_count=None,
    orphan_count=None,
    output=None,
):
    """Render the Stage 1.2 preflight summary block to ``output``.

    Caller decides whether to invoke this (TTY + --verbose gating lives
    in the ``cli``/``single_hop``/``multi_hop`` callsites). The
    ``write_count`` / ``patch_count`` / ``orphan_count`` parameters are
    the **authoritative** "Planned changes" counts and SHOULD be
    populated after the planner has run. When the caller cannot supply
    the exact write count yet, ``render_preflight`` reports a labeled
    estimate (``~N writes (estimated)``) derived from the per-entry
    customization classifier — it never silently substitutes a
    pre-planner heuristic for the real count, which is what the
    revision-7 review caught (the ``customized + new + deleted``
    fallback under-counted because it ignored entries already touched
    in earlier hops or already byte-identical to ``theirs``).
    """

    if output is None:
        output = sys.stdout

    counts = {"untouched": 0, "customized": 0, "new": 0, "deleted": 0}
    for entry in entries:
        bucket = _classify_entry(entry, target, template_root, current_version)
        counts[bucket] = counts[bucket] + 1

    walk_display = " -> ".join([current_version] + list(chain_versions or []))
    if not chain_versions:
        walk_display = f"{current_version} -> {to_version}"
    worktree_state = "clean" if worktree_clean else "dirty"
    backup_state = "enabled" if backup_enabled else "disabled (pass --backup to enable)"

    if write_count is None:
        estimate = counts["customized"] + counts["new"] + counts["deleted"]
        write_label = f"~{estimate} writes (estimated)"
    else:
        write_label = f"{write_count} writes"

    parts = [write_label]
    if patch_count is not None:
        parts.append(f"{patch_count} patches")
    if orphan_count is not None:
        parts.append(f"{orphan_count} orphans")
    planned_changes = ", ".join(parts)

    block = [
        "Pre-flight summary",
        f"  Target:           {target}",
        f"  Current version:  {current_version}",
        f"  Target version:   {to_version}",
        f"  Walk:             {walk_display}",
        f"  Worktree:         {worktree_state}",
        f"  Customized files: {counts['customized']}",
        f"  Planned changes:  {planned_changes}",
        f"  Backup:           {backup_state}",
    ]
    output.write("\n".join(block) + "\n")
    output.flush()
    return counts


def should_render_preflight(args, *, output=None):
    """TTY + --verbose gate. Returns True when the summary should print."""

    if getattr(args, "verbose", False):
        return True
    if output is None:
        output = sys.stdout
    return bool(getattr(output, "isatty", lambda: False)())
