"""Opt-in backup creation, listing, restore, and prune (Stage 1.3).

Triggered only when the caller passes ``--backup`` (or runs the
``backups`` subcommand). Default behavior is unchanged so existing
fixtures stay byte-identical post-apply.

Backups live **outside** the target repo to honor the
``core/README.md:42-43`` invariant that bootstrap/sync must not modify
the target repo's ``.gitignore``. Layout:

    $XDG_CACHE_HOME/agent-bootstrap/backups/<target-sha1>/<id>/
        manifest.json             # pre-apply copy of .agent/manifest.json
        sync-log.md.snapshot      # pre-apply copy of .agent/sync-log.md
        files/<relative-path>     # one file per touched path that
                                  #   existed before apply
        meta.json                 # authoritative restore map

    where  <target-sha1> = sha1(abspath(target))[:12]
           <id>          = <ISO8601>-<from>-<to>
           $XDG_CACHE_HOME falls back to ~/.cache when unset

``meta.json::entries`` holds one record per touched path:

    {
      "path": "<relative-target-path>",
      "pre_state": "present" | "absent",
      "sha256": "<hex of pre-apply bytes, or null when absent>"
    }

``pre_state == "absent"`` is the sentinel for files the migration
**creates** so that ``backups restore`` can delete them rather than
silently leaving a created file in place — without this, the
round-trip contract would break for migrations like 0.10.0 that add
new managed files.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import shutil
import sys
from collections import OrderedDict
from pathlib import Path

from .errors import SyncError, UsageError
from .io_utils import read_bytes, write_bytes
from .preflight import target_clean
from .sync_log import restore_log_entry


META_FILENAME = "meta.json"
MANIFEST_SNAPSHOT = "manifest.json"
SYNC_LOG_SNAPSHOT = "sync-log.md.snapshot"
FILES_DIR = "files"
DEFAULT_KEEP = 5


class BackupError(SyncError):
    exit_code = 1


def _target_sha1(target):
    abspath = str(Path(target).resolve())
    return hashlib.sha1(abspath.encode("utf-8")).hexdigest()[:12]


def _root_under(base, target):
    return Path(base) / "agent-bootstrap" / "backups" / _target_sha1(target)


def _candidate_roots(target, override=None):
    """Return the ordered list of backup roots to consider for ``target``.

    Single source of truth for the plan D-9 fallback chain. Both the
    write path (``create_backup``) and the read paths
    (``list_backups`` / ``prune_backups`` / ``restore_backup``) iterate
    this list in order so a backup written into the fallback when
    ``$XDG_CACHE_HOME`` is unwritable can still be discovered and
    restored later.

    Order:
      1. ``override`` (``--backup-dir``) — single candidate, no fallback.
      2. ``$XDG_CACHE_HOME/agent-bootstrap/backups/...`` when the env var
         is set.
      3. ``~/.cache/agent-bootstrap/backups/...`` — used directly when
         ``$XDG_CACHE_HOME`` is unset, AND as fallback when XDG is set
         but unwritable.
    """

    if override:
        return [Path(override).expanduser().resolve() / _target_sha1(target)]
    home = Path.home() / ".cache"
    home_root = _root_under(home, target)
    xdg = os.environ.get("XDG_CACHE_HOME")
    if xdg:
        xdg_root = _root_under(xdg, target)
        # When XDG is set, list it first; ~/.cache is the documented
        # fallback. Skip the duplicate entry if XDG already points at
        # ``~/.cache`` to avoid emitting a misleading warning.
        if xdg_root == home_root:
            return [xdg_root]
        return [xdg_root, home_root]
    return [home_root]


# Back-compat shim for any external caller; new code should prefer
# ``_candidate_roots``.
def _resolve_root(target, override=None):
    return _candidate_roots(target, override)[0]


def _try_make_writable(path):
    """Best-effort: ensure ``path`` exists and accepts writes. Returns True/False."""

    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".write-probe"
        probe.write_bytes(b"")
        probe.unlink()
        return True
    except OSError:
        return False


def _ensure_writable(path):
    """Raise :class:`BackupError` with guidance if ``path`` is unwritable."""

    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".write-probe"
        probe.write_bytes(b"")
        probe.unlink()
    except OSError as exc:
        raise BackupError(
            f"backup cache is not writable: {path} ({exc}). "
            f"Set $XDG_CACHE_HOME or pass --backup-dir to override."
        )


def _existing_roots(target, override=None):
    """Return every candidate root that exists on disk, in D-9 order.

    Used by read-side helpers (``list_backups`` / ``prune_backups``) so
    they discover backups **across** the candidate chain. Returning
    only the first ``is_dir()`` entry would hide the mixed-history
    corner where ``$XDG_CACHE_HOME/agent-bootstrap/backups/<sha>``
    exists (e.g. created by a prior writable run) but subsequent
    backups landed under ``~/.cache`` after XDG flipped read-only —
    list/prune would then silently shadow the real backups. Unioning
    also makes list symmetric with restore, which already iterates
    every candidate.
    """

    out = []
    seen = set()
    for root in _candidate_roots(target, override):
        if root.is_dir():
            try:
                resolved = root.resolve()
            except OSError:
                resolved = root
            if resolved in seen:
                continue
            seen.add(resolved)
            out.append(root)
    return out


# Back-compat shim for any caller outside this module.
def _existing_root(target, override=None):
    roots = _existing_roots(target, override)
    return roots[0] if roots else None


def _resolve_writable_root(target, override=None):
    """Return a writable backup root, honoring the plan D-9 fallback chain.

    Iterates :func:`_candidate_roots` and returns the first entry that
    becomes writable. When the primary candidate is unwritable but a
    fallback succeeds, emits a one-line stderr notice so the path the
    user sees in ``Backup created: ...`` is not surprising.

    Raises :class:`BackupError` (with all attempted paths in the
    message) when every candidate is unwritable.
    """

    candidates = _candidate_roots(target, override)
    tried = []
    for idx, root in enumerate(candidates):
        if _try_make_writable(root):
            if idx > 0:
                primary = candidates[0]
                print(
                    f"warning: backup cache {primary} is not writable; "
                    f"falling back to {root}",
                    file=sys.stderr,
                )
            return root
        tried.append(root)
    if override:
        # Honor the original error shape for ``--backup-dir`` so callers
        # still get the actionable hint about XDG.
        _ensure_writable(candidates[0])
    raise BackupError(
        "backup cache is not writable: tried "
        + ", ".join(str(p) for p in tried)
        + ". Pass --backup-dir to override."
    )


def _prune_empty_parents(start, *, stop):
    """Remove empty ancestor directories up to (but not including) ``stop``.

    Used by :func:`restore_backup` after deleting a file whose
    ``pre_state`` was ``absent`` so the post-restore tree matches the
    pre-apply layout byte-for-byte (plan L4). Silently stops on the
    first non-empty directory or on any OSError; never deletes
    ``stop`` itself.
    """

    try:
        stop_resolved = Path(stop).resolve()
    except OSError:
        return
    cur = Path(start)
    while True:
        try:
            cur_resolved = cur.resolve()
        except OSError:
            return
        if cur_resolved == stop_resolved:
            return
        # Safety: never walk above ``stop``.
        try:
            cur_resolved.relative_to(stop_resolved)
        except ValueError:
            return
        try:
            cur.rmdir()
        except OSError:
            return
        cur = cur.parent


def _sha256_hex(data):
    return hashlib.sha256(data).hexdigest()


def _now_iso():
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")


def make_backup_id(from_version, to_version, *, now=None):
    timestamp = now or _now_iso()
    return f"{timestamp}-{from_version}-{to_version}"


def create_backup(
    *,
    target,
    from_version,
    to_version,
    writes,
    mode,
    backup_root_override=None,
    keep=DEFAULT_KEEP,
):
    """Capture a pre-apply snapshot of the files about to be written.

    ``writes`` is the same dict the planner just produced (relative
    target paths -> new bytes). ``mode`` is the human label written to
    ``meta.json`` (typically ``"single-hop"`` or ``"multi-hop"``).
    Always snapshots ``.agent/manifest.json`` when it exists. A
    ``sync-log.md.snapshot`` is written only when ``.agent/sync-log.md``
    already exists pre-apply (first sync has none).
    """

    cache_root = _resolve_writable_root(target, backup_root_override)
    backup_id = make_backup_id(from_version, to_version)
    backup_dir = cache_root / backup_id
    backup_dir.mkdir(parents=True, exist_ok=False)
    files_dir = backup_dir / FILES_DIR
    files_dir.mkdir(parents=True, exist_ok=True)

    entries = []
    touched_paths = set(writes.keys())
    touched_paths.add(".agent/manifest.json")
    # Intentionally do NOT add ``.agent/sync-log.md`` to ``entries`` —
    # the file is append-only per ``core/migrations/README.md:341`` and
    # D-5, so restore must never overwrite it (doing so would erase the
    # apply entry that the just-completed sync just appended). The log
    # is still captured as ``sync-log.md.snapshot`` below **when the file
    # exists pre-apply** (first sync has no log yet), purely for audit.
    # ``restore_backup`` always appends the Restore entry to the *current*
    # on-disk log (never gated on snapshot presence).

    for rel in sorted(touched_paths):
        src = target / rel
        if src.exists():
            data = src.read_bytes()
            dest = files_dir / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
            entries.append(
                OrderedDict(
                    path=rel,
                    pre_state="present",
                    sha256=_sha256_hex(data),
                )
            )
        else:
            entries.append(
                OrderedDict(
                    path=rel,
                    pre_state="absent",
                    sha256=None,
                )
            )

    manifest_src = target / ".agent" / "manifest.json"
    if manifest_src.exists():
        (backup_dir / MANIFEST_SNAPSHOT).write_bytes(manifest_src.read_bytes())
    sync_log_src = target / ".agent" / "sync-log.md"
    if sync_log_src.exists():
        (backup_dir / SYNC_LOG_SNAPSHOT).write_bytes(sync_log_src.read_bytes())

    meta = OrderedDict(
        target=str(Path(target).resolve()),
        from_version=from_version,
        to_version=to_version,
        mode=mode,
        created_at=dt.datetime.now(dt.timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        ),
        entries=entries,
    )
    (backup_dir / META_FILENAME).write_text(
        json.dumps(meta, indent=2) + "\n", encoding="utf-8"
    )

    pruned = prune_backups(target, keep=keep, backup_root_override=backup_root_override)
    return backup_dir, backup_id, pruned


def list_backups(target, backup_root_override=None):
    """Return ``[(id, meta_dict)]`` sorted newest first.

    Honors the D-9 fallback chain: when ``$XDG_CACHE_HOME`` is set but
    empty (e.g. unwritable at create time so the writer fell back to
    ``~/.cache``), this returns the rows from the first candidate that
    actually exists on disk so list/restore stay symmetric with create.
    """

    seen_ids = set()
    rows = []
    for root in _existing_roots(target, backup_root_override):
        for child in root.iterdir():
            if not child.is_dir():
                continue
            meta_path = child / META_FILENAME
            if not meta_path.is_file():
                continue
            if child.name in seen_ids:
                # Prefer the row from the first candidate in D-9 order.
                continue
            try:
                with meta_path.open("r", encoding="utf-8") as fh:
                    meta = json.load(fh)
            except json.JSONDecodeError:
                continue
            seen_ids.add(child.name)
            rows.append((child.name, meta))
    rows.sort(key=lambda item: item[0], reverse=True)
    return rows


def prune_backups(target, *, keep, backup_root_override=None):
    """Keep the ``keep`` most recent backups for ``target``; delete the rest.

    Returns the list of pruned ids. ``keep`` of 0 deletes everything.
    Walks the D-9 candidate chain so prune still works after a write
    fell back from ``$XDG_CACHE_HOME`` to ``~/.cache``.
    """

    roots = _existing_roots(target, backup_root_override)
    if not roots:
        return []
    # Union across candidate roots with id-level dedup (prefer the first
    # candidate in D-9 order — same policy as ``list_backups``). ``keep``
    # is applied to the combined, newest-first order so prune semantics
    # stay stable regardless of where each backup physically landed.
    seen = {}
    for root in roots:
        for child in root.iterdir():
            if not child.is_dir():
                continue
            if not (child / META_FILENAME).is_file():
                continue
            seen.setdefault(child.name, child)
    ordered = sorted(seen.items(), key=lambda item: item[0], reverse=True)
    pruned = []
    for name, path in ordered[keep:]:
        shutil.rmtree(path, ignore_errors=True)
        pruned.append(name)
    return pruned


def restore_backup(target, backup_id, backup_root_override=None):
    """Round-trip the target tree to the pre-apply state captured by ``backup_id``.

    Append-only contract per D-5: rewrites ``manifest.json`` from the
    snapshot but **only appends** a ``Restore`` entry to
    ``.agent/sync-log.md``. The pre-apply log is preserved as a prefix.
    """

    backup_dir = None
    tried = []
    for root in _candidate_roots(target, backup_root_override):
        candidate = root / backup_id
        if (candidate / META_FILENAME).is_file():
            backup_dir = candidate
            break
        tried.append(candidate)
    if backup_dir is None:
        raise BackupError(
            "backup not found: tried " + ", ".join(str(p) for p in tried)
        )
    meta_path = backup_dir / META_FILENAME

    if not target_clean(target):
        raise BackupError(
            f"target worktree is dirty: {target}. Commit/stash before restore."
        )

    with meta_path.open("r", encoding="utf-8") as fh:
        meta = json.load(fh, object_pairs_hook=OrderedDict)

    files_dir = backup_dir / FILES_DIR

    restored = 0
    for entry in meta.get("entries", []):
        rel = entry["path"]
        # Defensive guard for backups created by pre-fix runners that
        # still recorded ``.agent/sync-log.md`` in entries. Restoring
        # the old log bytes would erase the apply entry we are about to
        # cite in the Restore audit line; the append-only invariant
        # (D-5) demands we leave the current log alone here.
        if rel == ".agent/sync-log.md":
            continue
        target_path = target / rel
        pre_state = entry.get("pre_state")
        if pre_state == "present":
            backed = files_dir / rel
            if not backed.is_file():
                raise BackupError(
                    f"backup is missing file body for {rel}: {backed}"
                )
            data = backed.read_bytes()
            write_bytes(target_path, data)
            written_sha = _sha256_hex(data)
            expected = entry.get("sha256")
            if expected and written_sha != expected:
                raise BackupError(
                    f"sha256 mismatch after restore for {rel}: expected "
                    f"{expected}, got {written_sha}"
                )
            restored += 1
        elif pre_state == "absent":
            if target_path.exists():
                target_path.unlink()
                _prune_empty_parents(target_path.parent, stop=Path(target).resolve())
            restored += 1
        else:
            raise BackupError(
                f"unknown pre_state {pre_state!r} in backup entry {entry}"
            )

    # D-5: always append a Restore audit line. Do not gate on
    # ``sync-log.md.snapshot`` — first sync has no pre-apply log, so
    # ``create_backup`` skips the snapshot file, but after apply the
    # target already has a sync-log with the apply entry; restore must
    # still append.
    log_path = target / ".agent" / "sync-log.md"
    existing = read_bytes(log_path) or b""
    if not existing.endswith(b"\n") and existing:
        existing = existing + b"\n"
    log_entry = restore_log_entry(
        sync_now=dt.datetime.now(dt.timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        ),
        backup_id=backup_id,
        restored_from=meta.get("from_version") or "<unknown>",
        file_count=restored,
        backup_dir=str(backup_dir),
    )
    if existing:
        new_log = existing + b"\n" + log_entry.encode("utf-8")
    else:
        new_log = ("# Sync Log\n\n" + log_entry).encode("utf-8")
    write_bytes(log_path, new_log)

    return backup_dir, restored


def cmd_list(args):
    target = Path(args.target).resolve()
    rows = list_backups(target, backup_root_override=getattr(args, "backup_dir", None))
    if not rows:
        print(f"No backups found for {target}")
        return 0
    print(f"Backups for {target}:")
    for backup_id, meta in rows:
        print(
            f"  {backup_id}  from={meta.get('from_version')}  "
            f"to={meta.get('to_version')}  files={len(meta.get('entries') or [])}"
        )
    return 0


def cmd_restore(args):
    target = Path(args.target).resolve()
    backup_id = args.backup_id
    backup_dir, restored = restore_backup(
        target, backup_id, backup_root_override=getattr(args, "backup_dir", None)
    )
    print(f"Restored {restored} files for {target} from {backup_dir}")
    return 0


def cmd_prune(args):
    target = Path(args.target).resolve()
    keep = args.keep if args.keep is not None else DEFAULT_KEEP
    pruned = prune_backups(
        target, keep=keep, backup_root_override=getattr(args, "backup_dir", None)
    )
    if not pruned:
        print(f"No backups pruned (keep={keep}).")
        return 0
    print(f"Pruned {len(pruned)} backup(s) for {target}:")
    for victim in pruned:
        print(f"  {victim}")
    return 0
