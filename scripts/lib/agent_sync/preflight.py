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
  - :func:`classify_merge_mode` (Stage 3.2 / 3.3 follow-up) labels each
    entry as ``fast-path`` / ``3-way-merge`` / ``tag-required-but-missing``
    so the preflight summary mirrors the routing the planner is about
    to take in :func:`merge.plan_safe_overwrites`. Default behavior is
    unchanged — the new line only appears when the mode counts are
    explicitly passed by the caller, which keeps the existing
    ``preflight-output`` fixture byte-stable.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import os
import sys
from pathlib import Path

from .errors import LockError
from .git_ops import git_text, tag_exists


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


def classify_merge_mode(
    entry, target, template_root, from_version, to_version, tracked_files
):
    """Classify the merge route a single entry will take in the planner.

    Mirrors the routing inside :func:`merge.plan_safe_overwrites` so the
    preflight summary can quote the same authoritative
    ``fast-path / 3-way-merge / tag-required-but-missing`` split the
    user is about to commit to. Read-only: never invokes ``git show``
    on the source path itself; only checks tag presence so the
    fast-path determination stays cheap (Stage 3.2 / AC-6: a hop where
    every entry fast-paths must not poke ``v<from>`` at all).

    Entries the planner **skips entirely** (same conditions as
    :func:`merge.plan_safe_overwrites`: ``enabled_when_path_exists`` not
    met, or ``skip_if_target_missing`` with a missing target) return
    ``None``. :func:`render_preflight` excludes them from the Merge
    modes line so counts never over-count optional entries.

    Returns one of:

      - ``None`` — planner will not process this entry this hop.
      - ``"fast-path"`` — ``manifest.tracked_files[target]`` is recorded
        AND the on-disk sha matches the recorded baseline. The planner
        will only consult ``v<to>`` for ``theirs``.
      - ``"3-way-merge"`` — fall-through to byte-exact 3-way merge with
        both ``v<from>`` and ``v<to>`` available locally.
      - ``"tag-required-but-missing"`` — entry is on the 3-way path but
        a required tag is absent from the template root. The planner
        will surface the ``try git fetch --tags`` hint when it actually
        runs; the preflight reports it up-front so the user can fetch
        before re-running.
    """

    condition = entry.get("enabled_when_path_exists")
    if condition and not (target / condition).exists():
        return None

    target_rel = entry["target"]
    target_path = target / target_rel
    if entry.get("skip_if_target_missing") and not target_path.exists():
        return None

    current_sha = _sha256_file(target_path)
    record = (tracked_files or {}).get(target_rel)
    if (
        isinstance(record, dict)
        and current_sha is not None
        and isinstance(record.get("synced_checksum_sha256"), str)
        and record["synced_checksum_sha256"] == current_sha
    ):
        # Fast-path branch: planner only needs ``v<to>``. ``v<from>`` is
        # never consulted on this branch (AC-6), so missing-from-tag is
        # NOT a fast-path-blocker. ``v<to>`` missing falls through to
        # 3-way merge inside the planner; flag it so the user can
        # ``git fetch --tags`` before applying.
        if not tag_exists(template_root, to_version):
            return "tag-required-but-missing"
        return "fast-path"

    # 3-way merge branch — both tags must be present.
    missing = [
        v for v in (from_version, to_version) if not tag_exists(template_root, v)
    ]
    if missing:
        return "tag-required-but-missing"
    return "3-way-merge"


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
    tracked_files=None,
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

    When ``tracked_files`` is non-empty, an additional ``Merge modes:``
    line summarises the per-entry routing the planner is about to take
    (``fast-path`` / ``3-way-merge`` / ``tag-required-but-missing``).
    The line is suppressed otherwise so manifests that have not yet
    opted into Stage 3.1 schema (every fixture pre-1.0.0) keep the
    pre-Stage-3.3 preflight output byte-stable.
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

    if tracked_files:
        # Mirror the planner's routing so the user sees the same
        # fast-path / 3-way-merge / tag-required-but-missing split
        # before any disk write. Counts are derived from the same
        # ``tag_exists`` checks the planner uses lazily, but executed
        # here read-only — no ``git show`` and no ``git fetch``.
        mode_counts = {
            "fast-path": 0,
            "3-way-merge": 0,
            "tag-required-but-missing": 0,
        }
        for entry in entries:
            mode = classify_merge_mode(
                entry,
                target,
                template_root,
                current_version,
                to_version,
                tracked_files,
            )
            if mode is None:
                continue
            mode_counts[mode] = mode_counts[mode] + 1
        block.append(
            "  Merge modes:      "
            f"fast-path: {mode_counts['fast-path']}, "
            f"3-way-merge: {mode_counts['3-way-merge']}, "
            f"tag-required-but-missing: {mode_counts['tag-required-but-missing']}"
        )

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
