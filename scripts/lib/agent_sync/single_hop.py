"""Single-hop migration orchestrator (no chain walk).

Default code path when ``--multi-hop`` is not set. Performs preflight
(target existence / git / clean / current version), loads a single
migration JSON, plans all writes (safe overwrites + patches + codex
wrappers + manifest), then either prints the dry-run plan or applies
under a ``.agent/.sync.lock`` and appends a sync-log entry.

The lock acquisition + try/finally release mirrors the original
``main()`` behavior 1:1 so the migration fixtures' lock-leak assertions
keep passing.
"""

from __future__ import annotations

import datetime as dt
import os
import sys
from pathlib import Path

from .codex_wrappers import plan_codex_wrappers
from .errors import (
    DirtyError,
    EXIT_VALIDATION,
    NoPathError,
    UsageError,
)
from .git_ops import run_git, tag_commit
from .io_utils import read_json
from .manifest_ops import plan_manifest
from .merge import apply_writes, collect_orphans, plan_safe_overwrites
from .migrations import expand_file_entries, list_migrations, list_tag_files, load_migration
from .patches import plan_patches
from .preflight import (
    acquire_lock,
    render_preflight,
    should_render_preflight,
    target_clean,
)
from .sync_log import append_sync_log, sync_log_entry
from .validation import run_validation
from .versions import detect_current_version, validate_version


def run_single_hop(args, template_root, target, accept_theirs):
    if args.to is not None:
        validate_version(args.to, "--to")
    migrations = list_migrations(template_root)
    to_version = args.to or (migrations[-1] if migrations else None)
    validate_version(to_version, "--to")

    migration_path = (
        template_root / "core" / "migrations" / to_version / "migration.json"
    )
    if not migration_path.is_file():
        raise NoPathError(
            f"no migration path found for requested target version {to_version}: missing {migration_path}"
        )
    migration = read_json(migration_path)
    if migration.get("schema_version") != 1:
        raise UsageError(
            f"unsupported migration schema_version: {migration.get('schema_version')}"
        )
    for key in ("version", "to"):
        validate_version(migration.get(key), f"migration {key}")

    candidate_sources = []
    if migration.get("from") is not None:
        validate_version(migration["from"], "migration from")
        candidate_sources.append(migration["from"])
    from_versions_pre = migration.get("from_versions")
    if isinstance(from_versions_pre, list):
        for value in from_versions_pre:
            validate_version(value, "migration from_versions[]")
            candidate_sources.append(value)
    if not candidate_sources:
        raise UsageError("migration must declare either `from` or `from_versions`")

    # Stage 3.2: tag existence is no longer validated up-front. The
    # 3-way merge path inside ``plan_safe_overwrites`` lazily checks
    # ``v<from>`` and ``v<to>`` only when an entry actually needs them,
    # which lets the Stage 3.2 checksum fast-path complete a hop in an
    # ephemeral mirror missing ``v<from>`` (AC-6). The actionable
    # "git fetch --tags" hint is preserved on fall-through, see
    # ``merge._ensure_tags_for_three_way``.

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

    if current == to_version:
        print(f"Target already synced to {to_version}; no-op.")
        return 0

    if current not in candidate_sources:
        # Auto multi-hop fallback (Stage 1.1, D-1): the requested target
        # version exists, but its migration.json does not list the
        # caller's current version as a valid `from`. Default behavior
        # is to walk a deterministic BFS chain; ``--no-auto-multi-hop``
        # opts out and re-raises NoPathError as before.
        if getattr(args, "no_auto_multi_hop", False):
            raise NoPathError(
                f"current version {current} is not a valid `from` for migration "
                f"{to_version}; pass --multi-hop to walk a chain or drop "
                f"--no-auto-multi-hop"
            )
        # Defer the import to avoid a circular dependency with
        # ``run_multi_hop``-side helpers.
        from .multi_hop import run_multi_hop  # noqa: WPS433

        # ``run_multi_hop`` raises UsageError when ``args.to is None``;
        # the user-facing single-hop default already resolved
        # ``to_version`` for us, so propagate it explicitly. No
        # single-hop lock has been taken yet, so no double-lock risk.
        if args.to is None:
            args.to = to_version
        args.multi_hop = True
        args.auto_multi_hop_fallback = True
        print(
            f"Auto-walking multi-hop chain from {current} to {to_version} "
            f"(no direct migration available)."
        )
        return run_multi_hop(args, template_root, target, accept_theirs)

    migration = load_migration(template_root, current, to_version)

    lock_path = None
    if args.apply:
        lock_path = acquire_lock(target, current, to_version)

    try:
        writes = {}
        updated = []
        accepted = []
        entries, managed_scopes, adapter_report = expand_file_entries(
            template_root, migration, args.with_adapters, manifest
        )

        known_conflicts = migration.get("known_conflicts") or []
        catalog_label = f"{current}->{to_version} catalog"
        plan_safe_overwrites(
            template_root,
            target,
            migration,
            entries,
            accept_theirs,
            writes,
            updated,
            accepted,
            known_conflicts=known_conflicts,
            catalog_source_label=catalog_label,
            tracked_files=manifest.get("tracked_files") or {},
        )
        plan_patches(target, migration, writes, updated)
        plan_codex_wrappers(
            template_root, target, migration, manifest, accept_theirs, writes, updated, accepted
        )

        sync_now = os.environ.get("AGENT_SYNC_NOW") or dt.datetime.now(
            dt.timezone.utc
        ).strftime("%Y-%m-%dT%H:%M:%SZ")
        plan_manifest(
            template_root,
            target,
            migration,
            manifest,
            sync_now,
            writes,
            updated,
            entries=entries,
        )

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
                    (
                        Path(generator["target_dir"])
                        / f"agent-{command_name}"
                        / "SKILL.md"
                    ).as_posix()
                )
        orphans = collect_orphans(target, managed_scopes, planned_targets)

        # Render preflight AFTER planner so writes/patches/orphans are
        # the authoritative counts the user is about to commit to. The
        # plan call sites this "immediately before the dry-run branch
        # and apply_writes" — both are below this point.
        if should_render_preflight(args):
            render_preflight(
                target=target,
                template_root=template_root,
                current_version=current,
                to_version=to_version,
                chain_versions=[to_version],
                entries=entries,
                backup_enabled=getattr(args, "backup", False),
                worktree_clean=target_clean(target),
                write_count=len(writes),
                patch_count=len(migration.get("patches") or []),
                orphan_count=len(orphans),
                tracked_files=manifest.get("tracked_files") or {},
            )

        if not args.apply:
            print(f"Dry run: {current} -> {to_version}")
            for path in sorted(writes):
                print(f"  update {path}")
            for path in adapter_report:
                print(f"  adapter report-only {path} (pass --with-adapters to include)")
            for path in orphans:
                print(f"  warning orphan managed file: {path}")
            return 0

        if getattr(args, "backup", False):
            from .backups import create_backup  # noqa: WPS433

            backup_dir, backup_id, _ = create_backup(
                target=target,
                from_version=current,
                to_version=to_version,
                writes=writes,
                mode="single-hop",
                backup_root_override=getattr(args, "backup_dir", None),
                keep=getattr(args, "backup_keep", None) or 5,
            )
            print(f"Backup created: {backup_dir} (id={backup_id})")

        apply_writes(target, writes)
        validation = run_validation(target, args.verify_fast)
        entry = sync_log_entry(
            sync_now,
            migration,
            tag_commit(template_root, migration["to"]),
            updated,
            accepted,
            orphans,
            validation,
        )
        append_sync_log(target, entry)
        print(f"Synced {target} from {current} to {to_version}.")
        return 0
    except SystemExit as exc:
        if exc.code == EXIT_VALIDATION:
            print("Migration applied but validation failed. To revert:", file=sys.stderr)
            print(f"  git -C {target} restore .", file=sys.stderr)
            print(f"  git -C {target} clean -fd", file=sys.stderr)
        raise
    finally:
        if lock_path is not None:
            try:
                lock_path.unlink()
            except FileNotFoundError:
                pass
