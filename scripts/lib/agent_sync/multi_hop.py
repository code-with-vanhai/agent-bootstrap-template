"""Multi-hop migration walker (chain rehearsal then atomic apply).

Sign-off invariants this module preserves verbatim from the original
single-file implementation (and that the migration fixtures pin):

  1. Preflight (target existence / git / dirty / current-version) runs
     BEFORE any ``tempfile.mkdtemp`` or ``shutil.copytree`` call —
     fixture ``multi-hop/run.sh`` case D fails if a temp dir
     materializes when the target is dirty.
  2. Single-hop semantics are unaffected; ``run_single_hop`` is the
     default code path. ``--multi-hop`` is the only switch into here.
  3. On ``--apply`` exactly one aggregated sync-log entry is appended
     after the full target batch is applied — fixture case B asserts
     the section count delta is exactly ``1``.
  4. ``--allow-dirty`` re-checks ``target_clean`` AFTER rehearsal but
     BEFORE ``acquire_lock``, because ``acquire_lock`` itself writes
     into the target.
  5. Conflict mid-rehearsal raises :class:`ConflictError` and the real
     target is left byte-identical (fixture case C verifies the SHA).
"""

from __future__ import annotations

import datetime as dt
import os
import shutil
import sys
import tempfile
from pathlib import Path

from .errors import (
    DirtyError,
    EXIT_VALIDATION,
    NoPathError,
    SyncError,
    UsageError,
)
from .git_ops import run_git, tag_commit, tag_exists, tag_for
from .io_utils import read_json
from .manifest_ops import plan_manifest
from .merge import apply_writes, collect_orphans, plan_safe_overwrites
from .migrations import expand_file_entries, list_tag_files, load_migration
from .patches import plan_patches
from .codex_wrappers import plan_codex_wrappers
from .preflight import acquire_lock, target_clean
from .sync_log import append_sync_log, multi_hop_sync_log_entry
from .validation import run_validation
from .versions import compute_migration_chain, detect_current_version, validate_version


def _execute_hop_on_temp(
    template_root, work_target, accept_theirs, args, hop_source, hop_to, sync_now, dry_run_print
):
    """Plan and apply one hop's writes against a writable rehearsal directory.

    `work_target` is an ephemeral copy of the real target. Always advances the
    rehearsal tree by writing the planned changes through `apply_writes` so the
    next hop sees the right state. Never validates and never appends to the
    rehearsal sync-log.
    """

    manifest_path = work_target / ".agent" / "manifest.json"
    manifest = read_json(manifest_path)
    migration = load_migration(template_root, hop_source, hop_to)

    writes = {}
    updated = []
    accepted = []
    entries, managed_scopes, adapter_report = expand_file_entries(
        template_root, migration, args.with_adapters, manifest
    )
    plan_safe_overwrites(
        template_root, work_target, migration, entries, accept_theirs, writes, updated, accepted
    )
    plan_patches(work_target, migration, writes, updated)
    plan_codex_wrappers(
        template_root, work_target, migration, manifest, accept_theirs, writes, updated, accepted
    )
    plan_manifest(template_root, work_target, migration, manifest, sync_now, writes, updated)

    planned_targets = set(writes) | {entry["target"] for entry in entries}
    generator = migration.get("generate_codex_command_wrappers") or {}
    if generator and generator.get("enabled_when_feature_present") in (
        manifest.get("features_enabled") or []
    ):
        for source_path in list_tag_files(
            template_root, migration["to"], generator["commands_source_glob"]
        ):
            command_name = Path(source_path).stem
            planned_targets.add(
                (Path(generator["target_dir"]) / f"agent-{command_name}" / "SKILL.md").as_posix()
            )
    orphans = collect_orphans(work_target, managed_scopes, planned_targets)

    if dry_run_print:
        print(f"  hop {hop_source} -> {hop_to}: {len(writes)} change(s)")
        for path in sorted(writes):
            print(f"    update {path}")
        for path in adapter_report:
            print(f"    adapter report-only {path} (pass --with-adapters to include)")
        for path in orphans:
            print(f"    warning orphan managed file: {path}")

    apply_writes(work_target, writes)

    return {
        "from": hop_source,
        "to": hop_to,
        "writes": dict(writes),
        "updated": list(updated),
        "accepted": list(accepted),
        "adapter_report": list(adapter_report),
        "orphans": list(orphans),
    }


def run_multi_hop(args, template_root, target, accept_theirs):
    if not target.exists():
        raise UsageError(f"target does not exist: {target}")
    if run_git(target, "rev-parse", "--git-dir", check=False).returncode != 0:
        raise UsageError(f"target is not a git repo: {target}")
    if not args.allow_dirty and not target_clean(target):
        raise DirtyError(
            f"target worktree is dirty: {target}. Commit/stash changes or pass --allow-dirty."
        )
    manifest_path = target / ".agent" / "manifest.json"
    if not manifest_path.is_file():
        raise UsageError(f"target is missing .agent/manifest.json: {target}")
    manifest = read_json(manifest_path)
    current = detect_current_version(manifest)
    validate_version(current, "current template version")

    if args.to is None:
        raise UsageError("--multi-hop requires --to <version>")
    validate_version(args.to, "--to")
    to_version = args.to

    if current == to_version:
        print(f"Target already synced to {to_version}; no-op.")
        return 0

    chain = compute_migration_chain(template_root, current, to_version)
    if not chain:
        raise NoPathError(f"empty migration chain from {current} to {to_version}")

    for version in [current] + chain:
        if not tag_exists(template_root, version):
            raise UsageError(
                f"version {version} requires tag {tag_for(version)}; try git fetch --tags"
            )

    sync_now = os.environ.get("AGENT_SYNC_NOW") or dt.datetime.now(
        dt.timezone.utc
    ).strftime("%Y-%m-%dT%H:%M:%SZ")

    print(f"Multi-hop {'apply' if args.apply else 'dry run'}: {current} -> {to_version}")
    print(f"Chain: {' -> '.join([current] + chain)}")

    temp_parent = Path(tempfile.mkdtemp(prefix="agent-sync-chain-"))
    lock_path = None
    try:
        temp_target = temp_parent / "target"
        shutil.copytree(
            target,
            temp_target,
            symlinks=True,
            ignore=shutil.ignore_patterns(".git"),
        )
        temp_lock = temp_target / ".agent" / ".sync.lock"
        if temp_lock.exists():
            temp_lock.unlink()

        hop_results = []
        hop_source = current
        for hop_to in chain:
            print(f"Hop {hop_source} -> {hop_to}")
            result = _execute_hop_on_temp(
                template_root,
                temp_target,
                accept_theirs,
                args,
                hop_source,
                hop_to,
                sync_now,
                dry_run_print=not args.apply,
            )
            hop_results.append(result)
            hop_source = hop_to

        if not args.apply:
            return 0

        # Re-check target_clean AFTER rehearsal but BEFORE acquire_lock, because
        # acquire_lock writes .agent/.sync.lock into the target tree itself
        # (which would otherwise make this very check fail).
        if not args.allow_dirty and not target_clean(target):
            raise DirtyError(
                f"target worktree became dirty during rehearsal: {target}. Aborting before write."
            )
        lock_path = acquire_lock(target, current, to_version)

        touched = set()
        for r in hop_results:
            touched.update(r["writes"].keys())
        final_writes = {}
        for rel in sorted(touched):
            final_writes[rel] = (temp_target / rel).read_bytes()
        apply_writes(target, final_writes)

        try:
            validation = run_validation(target, args.verify_fast)
        except SystemExit as exc:
            if exc.code == EXIT_VALIDATION:
                print("Migration applied but validation failed. To revert:", file=sys.stderr)
                print(f"  git -C {target} restore .", file=sys.stderr)
                print(f"  git -C {target} clean -fd", file=sys.stderr)
            raise

        merged_updated, merged_accepted, merged_orphans = [], [], []
        seen_updated, seen_accepted, seen_orphans = set(), set(), set()
        for r in hop_results:
            for u in r["updated"]:
                if u not in seen_updated:
                    merged_updated.append(u)
                    seen_updated.add(u)
            for a in r["accepted"]:
                if a not in seen_accepted:
                    merged_accepted.append(a)
                    seen_accepted.add(a)
            for o in r["orphans"]:
                if o not in seen_orphans:
                    merged_orphans.append(o)
                    seen_orphans.add(o)

        final_template_commit = tag_commit(template_root, to_version)
        entry = multi_hop_sync_log_entry(
            sync_now,
            current,
            to_version,
            chain,
            final_template_commit,
            merged_updated,
            merged_accepted,
            merged_orphans,
            validation,
        )
        append_sync_log(target, entry)

        print(
            f"Synced {target} from {current} to {to_version} via {' -> '.join([current] + chain)}."
        )
        return 0
    finally:
        if lock_path is not None:
            try:
                lock_path.unlink()
            except FileNotFoundError:
                pass
        shutil.rmtree(temp_parent, ignore_errors=True)
