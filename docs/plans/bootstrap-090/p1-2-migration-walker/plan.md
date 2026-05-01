# Plan: Multi-hop migration walker (P1-2)

**Status:** Verified with evidence: agent-validate.sh @ 2026-04-30T08:15:34Z (exit=0)
**Date:** 2026-04-30
**Ref commit:** `6b95814`
**Plan location note:** Stored under `docs/plans/bootstrap-090/p1-2-migration-walker/`. Generated target repos should use `.agent/runs/<date>-<slug>/`.

## Goal

Ship a **multi-hop sync orchestrator** so a target repo can advance from template version `N` to `M` (for example `0.4.0 → 0.8.1`) in one user invocation, without rewriting the single-hop migration engine in `agent-sync.py`. Dry-run must not mutate the target worktree; `--apply` must only touch the target after a full successful rehearsal on an ephemeral clone.

## Run Artifact

`docs/plans/bootstrap-090/p1-2-migration-walker/{spec.md,plan.md}`

## Affected Areas

- `scripts/agent-sync.py` (MODIFIED) — add chain resolution + multi-hop orchestration; factor minimal shared helpers if needed without destabilizing `main()`.
- `scripts/agent-sync.sh` (MODIFIED) — pass through new flags (thin wrapper).
- `USAGE.md` and/or `core/migrations/README.md` (MODIFIED) — document multi-hop usage and sync-log aggregation policy.
- `tests/migrations/multi-hop/run.sh` (NEW) — mechanical regression for dry-run, successful apply, failed mid-chain, dirty-target guard.

## Owner

Implementer. Reviewer verifies target immutability on failure paths and that single-hop CLI behavior is unchanged.

## Acceptance Criteria

| ID | Criterion | Verification Method | Gate |
|:---|:---|:---|:---|
| AC-P2-1 | Multi-hop plan/spec validate strict-clean | `AUTOMATED-INTEGRATION` | `scripts/agent-validate-plan.sh --force --strict` on this folder |
| AC-P2-2 | Default `--multi-hop` dry-run leaves `--target` manifest bytes unchanged | `AUTOMATED-INTEGRATION` | `tests/migrations/multi-hop/run.sh` |
| AC-P2-3 | `--multi-hop --apply` reaches final `--to` manifest when rehearsal succeeds | `AUTOMATED-INTEGRATION` | `tests/migrations/multi-hop/run.sh` |
| AC-P2-4 | Mid-chain failure on temp leaves target tree identical | `AUTOMATED-INTEGRATION` | `tests/migrations/multi-hop/run.sh` |
| AC-P2-5 | `.agent/sync-log.md` has exactly one new H2 section for successful multi-hop apply | `AUTOMATED-INTEGRATION` | `tests/migrations/multi-hop/run.sh` |

## Implementation Plan

1. **Graph + chain resolution**
   - Enumerate migrations with `list_migrations()`; for each `core/migrations/<to>/migration.json`, parse accepted sources via `from_versions` and legacy `from` (same union as `load_migration()`).
   - Build adjacency: directed edge `src → to` when `src` is accepted for migration to `to`.
   - Compute a **shortest** path from detected current version (`detect_current_version()`) to `--to` using BFS. If unreachable, raise `NoPathError` with an actionable message listing known neighbors.
   - Tie-break: when multiple edges exist at the same BFS depth, prefer the next hop version with **lowest semver** by the existing tuple sort key used in `list_migrations()`.

2. **CLI surface**
   - Extend `argparse` with `--multi-hop` (store_true). When absent, preserve today’s single-hop behavior verbatim.
   - When `--multi-hop` is set, require explicit `--to` (do not implicitly chain to “latest” unless `--to` is provided — avoids surprising long chains). Document this in `USAGE.md`.
   - Forward `--multi-hop` through `scripts/agent-sync.sh` unchanged (`exec python3 ... "$@"` already passes flags).

3. **Preflight order (mandatory before any temp work)**
   - Run target existence/git/dirty/current-version checks **before** temp copy for both dry-run and apply. This means: target must exist, must be a git repo, must be clean (or `--allow-dirty`), must have `.agent/manifest.json`, and the detected current version must validate as semver. Only after these checks pass do we materialize the temp clone. This guarantees that `EXIT_DIRTY` (and equivalent usage failures) is raised against the real target without ever calling `tempfile.mkdtemp` or `shutil.copytree`.

4. **Ephemeral rehearsal clone (dry-run and apply)**
   - Create `temp_root = Path(tempfile.mkdtemp(prefix="agent-sync-chain-"))`.
   - `shutil.copytree(target, temp_root, dirs_exist_ok=False, symlinks=True)` (or equivalent) to clone the target working tree for simulation — **never** run hop planning against a synthetic manifest that does not match real files.
   - For **each** hop `(v_i → v_{i+1})` in the chain:
     - Load migration via `load_migration(template_root, v_i, v_{i+1})`.
     - Reuse the existing planning sequence: `expand_file_entries`, `plan_safe_overwrites`, `plan_patches`, `plan_codex_wrappers`, `plan_manifest` with a `sync_now` stamp derived from `AGENT_SYNC_NOW` when set (tests) or UTC now — per hop, reuse the same timestamp policy as single-hop for determinism.
     - **Dry-run (`--multi-hop` without `--apply`)**: print a hop banner and the same per-file dry-run lines as `main()` (`update ...`, adapter/orphan warnings), then **`apply_writes(temp_root, writes)`** so the temp tree advances — **still no writes to `--target`**.
     - **Apply (`--multi-hop --apply`)**: on the temp clone only, `apply_writes` each hop; collect the union of relative paths touched across hops for the final target batch (see step 4). Do **not** append sync-log entries inside the temp clone (avoid misleading history under `.agent/sync-log.md` in the ephemeral tree) — optional: truncate or delete sync-log in temp after each hop if `append_sync_log` runs during internal single-hop reuse; implementation must ensure the final target replay does not double-append. **Preferred approach:** refactor the hop executor so sync-log append is **optional** (parameter `write_sync_log: bool`), default `True` for single-hop `main()`, `False` for multi-hop intermediate hops; multi-hop performs **one** `append_sync_log(target, aggregated_entry)` at the end.

5. **Target apply batch (only when `--apply`)**
   - After the temp rehearsal succeeds (no conflicts, no validation abort), acquire `acquire_lock(target, current, final_to)` once, re-check `target_clean` unless `--allow-dirty`.
   - Copy **only** the union of relative paths that changed between `snapshot_bytes(target_rel)` at start and `temp_final` for each path in the touched set (or recomputed final `writes` from a second identical temp run if safer — pick one strategy and test it; default recommended: **single rehearsal**, hash-compare baseline snapshot taken before rehearsal).
   - Invoke `run_validation(target, verify_fast)` on the real target after the batch copies mirror single-hop `--apply` semantics.
   - Append **one** aggregated sync-log entry to the target describing: original `from`, final `to`, ordered hop list, final template commit SHA, merged `updated`/`accepted`/`orphans`/`validation` fields with hop labels where needed.

6. **Validation policy**
   - **Do not** run `run_validation` on the temp clone. The rehearsal tree is a planning surface only; invoking `agent-validate.sh` there can fail for known fixture quirks (`bootstrap_pending` / validator false-positives) without reflecting the target’s real post-upgrade state.
   - On the **real target** after batch apply: run `run_validation(target, verify_fast)` when `--verify-fast` is set, identical to single-hop `main()`.

7. **Documentation**
   - Update `USAGE.md` with `scripts/agent-sync.sh --multi-hop --target … --to …` examples (dry-run vs `--apply`).
   - Add a short subsection to `core/migrations/README.md` noting multi-hop availability and pointing to deferred v2 items still out of scope.

8. **Tests**
   - Add `tests/migrations/multi-hop/run.sh`:
     - Build a genuine **0.4.0** fixture using the same helper pattern as `tests/migrations/0.5.0/run.sh` (`setup_040_fixture`).
     - Case A: `--multi-hop --to 0.5.0` (or a slightly longer chain ending at `0.6.0` for speed) dry-run: assert target `manifest.json` bytes unchanged (mtime or `sha256sum` before/after).
     - Case B: `--multi-hop --apply --to <final>`: assert manifest `synced_to_template_version` matches `<final>` and equals the sequential single-hop oracle run in a throwaway clone (optional cross-check).
     - Case C: force a mid-chain conflict in temp only (fixture with intentional drift that fails hop `k`); assert target tree unchanged.
     - Case D: dirty target without `--allow-dirty` exits with `EXIT_DIRTY` before any `tempfile.mkdtemp` / `shutil.copytree` call. Implementation must keep preflight (existence/git/dirty/current-version) ordered before temp materialization.
   - Register the script wherever other `tests/migrations/*/run.sh` aggregators are listed (if a parent `run-all` exists — search and wire).

9. Gates after implementation

Run, in order:

- `scripts/agent-validate.sh`
- `python3 -m unittest` modules touched by validation
- `bash scripts/agent-evals.sh --fast`
- `scripts/agent-validate-plan.sh --force --strict docs/plans/bootstrap-090/p1-2-migration-walker`
- Representative migration tests including new `tests/migrations/multi-hop/run.sh`

## Existing Behaviors Preserved

- Single-hop CLI defaults remain: dry-run without `--apply`, dirty target rejection without `--allow-dirty`, `.agent/.sync.lock` only on `--apply`, `EXIT_*` codes unchanged for existing paths. Citation: `historical-code`; `scripts/agent-sync.py:611-704` (pre-P1-2 main()).
- `load_migration()` metadata rules (`from_versions` union, `migration["from"]` pin to actual current) remain the contract for every hop. Citation: `historical-code`; `scripts/agent-sync.py:155-194` (pre-P1-2 line numbers; behavior unchanged post-implementation).
- `sync_log_entry()` / `append_sync_log()` markdown shape remains backward compatible for single-hop; multi-hop adds **aggregated** entry only, still append-only. Citation: `historical-code`; `scripts/agent-sync.py:500-545` (pre-P1-2 line numbers).
- Thin bash wrapper continues to delegate to Python with `PYTHONDONTWRITEBYTECODE=1`. Citation: `current-code`; `scripts/agent-sync.sh:1-13`.
- Schema v1 still explicitly defers cross-hop in the historical migration design note — P1-2 supersedes ops practice only for the orchestrator, not schema. Citation: `historical-code`; `core/migrations/README.md:40-47`.

## Grounded Evidence

<!-- historical-code path=scripts/agent-sync.py lines=611-704 ref=6b95814 region_sha256=01edb320720fd5693fb4c3ccd799bac0908abb5567a526476274462a1454bc06 -->
```python
    if args.to is not None:
        validate_version(args.to, "--to")
    migrations = list_migrations(template_root)
    to_version = args.to or (migrations[-1] if migrations else None)
    validate_version(to_version, "--to")

    migration_path = template_root / "core" / "migrations" / to_version / "migration.json"
    if not migration_path.is_file():
        raise NoPathError(f"no migration path found for requested target version {to_version}: missing {migration_path}")
    migration = read_json(migration_path)
    if migration.get("schema_version") != 1:
        raise UsageError(f"unsupported migration schema_version: {migration.get('schema_version')}")
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

    if not tag_exists(template_root, migration["to"]):
        raise UsageError(f"version {migration['to']} requires tag {tag_for(migration['to'])}; try git fetch --tags")
    for version in candidate_sources:
        if not tag_exists(template_root, version):
            raise UsageError(f"version {version} requires tag {tag_for(version)}; try git fetch --tags")

    if not target.exists():
        raise UsageError(f"target does not exist: {target}")
    if run_git(target, "rev-parse", "--git-dir", check=False).returncode != 0:
        raise UsageError(f"target is not a git repo: {target}")
    if not args.allow_dirty and not target_clean(target):
        raise DirtyError(f"target worktree is dirty: {target}. Commit/stash changes or pass --allow-dirty.")

    manifest_path = target / ".agent" / "manifest.json"
    if not manifest_path.is_file():
        raise UsageError(f"target is missing .agent/manifest.json: {target}")
    manifest = read_json(manifest_path)
    current = detect_current_version(manifest)
    validate_version(current, "current template version")

    if current == to_version:
        print(f"Target already synced to {to_version}; no-op.")
        return 0

    migration = load_migration(template_root, current, to_version)

    lock_path = None
    if args.apply:
        lock_path = acquire_lock(target, current, to_version)

    try:
        writes = {}
        updated = []
        accepted = []
        entries, managed_scopes, adapter_report = expand_file_entries(template_root, migration, args.with_adapters, manifest)

        plan_safe_overwrites(template_root, target, migration, entries, accept_theirs, writes, updated, accepted)
        plan_patches(target, migration, writes, updated)
        plan_codex_wrappers(template_root, target, migration, manifest, accept_theirs, writes, updated, accepted)

        sync_now = os.environ.get("AGENT_SYNC_NOW") or dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        plan_manifest(template_root, target, migration, manifest, sync_now, writes, updated)

        planned_targets = set(writes) | {entry["target"] for entry in entries}
        generator = migration.get("generate_codex_command_wrappers") or {}
        if generator and generator.get("enabled_when_feature_present") in (manifest.get("features_enabled") or []):
            for source_path in list_tag_files(template_root, migration["to"], generator["commands_source_glob"]):
                command_name = Path(source_path).stem
                planned_targets.add((Path(generator["target_dir"]) / f"agent-{command_name}" / "SKILL.md").as_posix())
        orphans = collect_orphans(target, managed_scopes, planned_targets)

        if not args.apply:
            print(f"Dry run: {current} -> {to_version}")
            for path in sorted(writes):
                print(f"  update {path}")
            for path in adapter_report:
                print(f"  adapter report-only {path} (pass --with-adapters to include)")
            for path in orphans:
                print(f"  warning orphan managed file: {path}")
            return 0

        apply_writes(target, writes)
        validation = run_validation(target, args.verify_fast)
        entry = sync_log_entry(sync_now, migration, tag_commit(template_root, migration["to"]), updated, accepted, orphans, validation)
        append_sync_log(target, entry)
        print(f"Synced {target} from {current} to {to_version}.")
        return 0
```
<!-- /historical-code -->

<!-- historical-code path=scripts/agent-sync.py lines=155-194 ref=6b95814 region_sha256=18fbaf692a223f86b8aada1b9337df6ac05c068c3342b3ffb83506b5e11e8ec5 -->
```python
def load_migration(template_root, current, to_version):
    path = template_root / "core" / "migrations" / to_version / "migration.json"
    if not path.is_file():
        raise NoPathError(f"no migration path found for {current} -> {to_version}: missing {path}")
    migration = read_json(path)
    if migration.get("schema_version") != 1:
        raise UsageError(f"unsupported migration schema_version: {migration.get('schema_version')}")
    for key in ("version", "to"):
        validate_version(migration.get(key), f"migration {key}")

    # `from` is optional when `from_versions: []` is provided; otherwise required.
    from_versions = migration.get("from_versions")
    if from_versions is not None:
        if not isinstance(from_versions, list) or not from_versions:
            raise UsageError("migration from_versions must be a non-empty array of semver strings")
        for value in from_versions:
            validate_version(value, "migration from_versions[]")

    if migration.get("from") is not None:
        validate_version(migration["from"], "migration from")

    if from_versions is None and migration.get("from") is None:
        raise UsageError("migration must declare either `from` or `from_versions`")

    accepted_sources = set(from_versions or [])
    if migration.get("from") is not None:
        accepted_sources.add(migration["from"])

    if current not in accepted_sources or migration["to"] != to_version or migration["version"] != to_version:
        raise NoPathError(
            f"migration metadata mismatch: current={current}, requested={to_version}, "
            f"manifest from={migration.get('from')} from_versions={from_versions} "
            f"to={migration['to']} version={migration['version']}"
        )

    # Normalize: downstream code reads migration['from'] when building the sync
    # log entry and validating tag presence. Pin it to the actual source version
    # the caller is migrating from.
    migration["from"] = current
    return migration
```
<!-- /historical-code -->

<!-- historical-code path=scripts/agent-sync.py lines=500-545 ref=6b95814 region_sha256=a193d989cb19cd7f59362ed20adb9c31cba5d1337137988f064cf04a0b6038fa -->
```python
def sync_log_entry(sync_now, migration, template_commit, updated, accepted, orphans, validation):
    lines = [
        f"## {sync_now} - Sync to {migration['to']}",
        "",
        f"- From: {migration['from']}",
        f"- To: {migration['to']}",
        f"- Template commit: {template_commit[:7]}",
        "- Updated:",
    ]
    if updated:
        lines.extend(f"  - {item}" for item in updated)
    else:
        lines.append("  - none")
    lines.append("- Accepted theirs:")
    if accepted:
        lines.extend(f"  - {item}" for item in accepted)
    else:
        lines.append("  - none")
    lines.extend([
        "- Preserved:",
        "  - .agent/project-profile.md",
        "  - .agent/gates.md",
        "  - .agent/ownership.md",
        "  - scripts/agent-eval.sh repo-specific gates",
        "- Warnings:",
    ])
    if orphans:
        lines.extend(f"  - orphan managed file: {item}" for item in orphans)
    else:
        lines.append("  - no managed-directory orphan files")
    lines.append("- Validation:")
    for item in validation:
        lines.append(f"  - {item}")
    return "\n".join(lines) + "\n"


def append_sync_log(target, entry):
    path = target / ".agent" / "sync-log.md"
    if path.exists():
        existing = path.read_text(encoding="utf-8")
        if not existing.endswith("\n"):
            existing += "\n"
        text = existing + "\n" + entry
    else:
        text = "# Sync Log\n\n" + entry
    path.write_text(text, encoding="utf-8")
```
<!-- /historical-code -->

<!-- current-code path=scripts/agent-sync.sh lines=1-13 ref=6b95814 region_sha256=f25f4e48cd35a9e6ed5e23510a7799af8e036ce0ffd28699e6515c0cfeeba209 -->
```bash
#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
TEMPLATE_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

if ! command -v python3 >/dev/null 2>&1; then
  printf 'ERROR: python3 is required for agent sync.\n' >&2
  exit 2
fi

export PYTHONDONTWRITEBYTECODE=1
exec python3 "$SCRIPT_DIR/agent-sync.py" --template-root "$TEMPLATE_ROOT" "$@"
```
<!-- /current-code -->

<!-- historical-code path=core/migrations/README.md lines=40-47 ref=6b95814 region_sha256=facae3b682ad91009f8b9e3dcee56c666cda66776cf4135ee03e3da71b1d963b -->
```text
**Deferred to schema v2:**

- File delete / rename operations.
- `/agent-bootstrap:sync` slash command.
- Default auto-running of real gates post-migration. MVP only supports explicit `--verify-fast`.
- Cross-minor chain migration beyond one hop.

---
```
<!-- /historical-code -->

## Contract Value Table

| Literal | Producer | Consumer | User-facing behavior | Test |
|:---|:---|:---|:---|:---|
| CLI flag `--multi-hop` | `argparse` in `agent-sync.py` | Users / CI | Runs BFS chain orchestration; without it, legacy single-hop path only | `tests/migrations/multi-hop/run.sh` |
| Aggregated sync-log heading `Sync to <final>` | Multi-hop `--apply` | Humans / auditors | One appended section lists hop chain + final template commit | `tests/migrations/multi-hop/run.sh` |
| Env `AGENT_SYNC_NOW` | Tests / CI | `agent-sync.py` | Freezes timestamps like single-hop for determinism | Existing migration tests pattern |

## Decision Ledger

| Decision | Chosen Behavior | Rationale | Alternatives Rejected | Caller/User Impact | Verification |
|:---|:---|:---|:---|:---|:---|
| Preflight order (sign-off invariant 1) | Run target existence/git/dirty/current-version checks before `tempfile.mkdtemp` / `shutil.copytree`, for both dry-run and apply | Dirty/invalid target must be rejected without disturbing any temp tree; mirrors single-hop policy in `current-code`; `scripts/agent-sync.py:644-655` | Materialize temp first, validate later | Users with dirty trees get same `EXIT_DIRTY` as today, no stray `/tmp` dirs | Test Case D in `tests/migrations/multi-hop/run.sh` asserts no temp dir creation when target dirty |
| Single-hop preservation (sign-off invariant 2) | When `--multi-hop` is absent, `main()` flow is byte-equivalent to today | Avoid regressing existing CI / docs / muscle memory | Refactor `main()` into multi-hop-only entrypoint | All existing `tests/migrations/*/run.sh` keep passing unchanged | Existing migration regression tests must remain green |
| Sync-log cardinality (sign-off invariant 3) | Multi-hop `--apply` performs **exactly one** `append_sync_log(target, aggregated_entry)` after the full target batch is applied successfully | Audit trail stays one-event-per-upgrade; prevents partial logs if final apply fails | Append per intermediate hop on temp then replay | Reviewers see one upgrade event per multi-hop run | `tests/migrations/multi-hop/run.sh` greps section count delta in `.agent/sync-log.md` (delta == 1) |
| Multi-hop dry-run mutates temp only | Copy `--target` to `tmp`, apply writes hop-by-hop in `tmp`, print per-hop dry-run lines | Real target manifest at `N` cannot plan hop `N+1 → N+2` without advancing state; prior design deferred chaining (`historical-code path=core/migrations/README.md lines=40-47`) | Printing hop≥2 plans directly against an unmodified target | Users see accurate plan; disk writes confined to `tmp` | Assert manifest SHA stable on target after dry-run |
| Target mutation timing | After successful full rehearsal, acquire lock then copy final bytes for touched paths | Matches safety goal: no partial hop states on production target | Apply each hop directly to target | Failed hop never leaves target mid-version | Failure-injection test on temp branch |
| Sync-log cardinality | Single aggregated append on successful `--apply` | `sync_log_entry()` is hop-shaped today (`current-code path=scripts/agent-sync.py lines=500-533`); repeating it raw per hop is noisy and confusing in audit | Per-hop log sections mirror temp | Reviewers see one upgrade event | Golden substring checks in `sync-log.md` |
| Shortest chain tie-break | BFS + lowest semver next hop when depth ties | Deterministic, reproducible | Random / lexicographic on directory name | Identical reruns pick same path | Unit test on toy graph |
| `run_validation` cadence | **Target only**, once after aggregated batch apply, when `--verify-fast` (never on temp) | Mirrors single-hop: one post-apply validation; temp is not a git/working copy match for `AGENT_ROOT` gates | Validate after every hop or on temp after final hop | Same `--verify-fast` semantics as single-hop | `USAGE.md` + multi-hop integration test default leaves `--verify-fast` off |

## Test Delta

| Test | Action | Why |
|:---|:---|:---|
| `tests/migrations/multi-hop/run.sh` | ADD | Covers dry-run immutability, apply success, mid-chain failure, dirty guard |
| Existing `tests/migrations/*/run.sh` | KEEP | Regression signal for single-hop migrations remains primary |

## Compatibility Matrix

| Scenario | Producer | Consumer | Policy |
|:---|:---|:---|:---|
| User omits `--multi-hop` | Older scripts | Current `agent-sync.py` | Identical behavior and exit codes as today |
| User adds `--multi-hop` without `--to` | CLI | Python | Fail fast with usage hint (`--to` required) |
| Aggregated sync-log reader | Template maintainers | Downstream humans | New headings are still markdown H2 sections; parsers must tolerate extra bullets |

## Risks

- **RISK-001:** Refactoring `main()` to share hop execution might regress single-hop lock ordering — **Mitigation:** keep single-hop `main()` path callable as today; add internal function covered by both paths.
- **RISK-002:** Skipping per-hop `append_sync_log` in temp could hide bugs if code assumes log exists — **Mitigation:** pass `write_sync_log=False` only for multi-hop rehearsal; single-hop remains default `True`.

## Verification

- `scripts/agent-validate.sh`
- `python3 -m unittest` (modules as impacted by validator changes)
- `bash scripts/agent-evals.sh --fast`
- `scripts/agent-validate-plan.sh --force --strict docs/plans/bootstrap-090/p1-2-migration-walker`
- `bash tests/migrations/multi-hop/run.sh`
