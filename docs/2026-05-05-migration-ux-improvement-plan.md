# Migration UX Improvement Plan

Date: 2026-05-05
Status: Draft (revision 7, implementation-ready for Stage 1; D-11 selected as Option A, pending implementation; Stage 3 direction-only)
Audience: Maintainers planning releases 0.12.0 → 1.0.0
Related work:
- `docs/2026-05-01-agent-bootstrap-hardening-implementation-plan.md`
- Comparative reference: `claudekit-engineer-main` (CLI-led upgrade model)

## Review Decision

Revision 6 incorporates six review rounds on 2026-05-05. The direction
— keep 3-way merge + `sync-log` invariants, layer UX improvements — is
unchanged from revision 1. Material corrections accumulated through r2,
r3, r4, r5, r6 (each finding is cited inline near the change it
produced):

- AC wording "any released version → latest released" is **replaced** by
  "latest migratable version". Note: the live `0.11.0` case is a
  **process exception**, not a legitimate patch: `core/release-process.md:7`
  requires minor releases (incl. `0.10.0 → 0.11.0`) to ship a migration
  directory "even when the migration is intentionally empty". The
  optional-migration rule at `core/release-process.md:8` applies only to
  patch releases (e.g. `0.3.0 → 0.3.1`). Resolution path is in **D-11 /
  Q-1** below: either backfill an empty `core/migrations/0.11.0/` (Option
  A, restores policy compliance) or amend `core/release-process.md` to
  permit minor-without-migration (Option B, weakens current contract).
  Revision 7 closes this decision: **Option A is selected**. Stage 2
  now includes the 0.11.0 migration backfill implementation.
- Zip release artifact is **removed** from Stage 2 and moved to Backlog.
  Current runner depends on `git show` / `git ls-tree` against tags
  (`scripts/lib/agent_sync/migrations.py:103-124`,
  `scripts/lib/agent_sync/git_ops.py`), so a `.git`-less zip cannot serve
  as `--template-root` without a baseline-provider redesign.
- Auto-backup is **opt-in** (`--backup` flag) and writes to an OS cache
  directory (`$XDG_CACHE_HOME/agent-bootstrap/backups/<target-hash>/...`)
  rather than inside the target repo. This preserves the invariant that
  the runner must not modify target `.gitignore` (`core/README.md:42-43`)
  and keeps existing fixtures unchanged (e.g.
  `tests/migrations/0.5.0/run.sh:119` asserts exact 2-file post-apply
  status).
- Restore semantics change: sync-log is **append-only** per
  `core/migrations/README.md:341`. Restore appends a `restore` entry
  referencing the snapshot; it does not truncate the log.
- Stage 1.1 auto multi-hop gains a **hash-guarded known-conflict
  catalog**. To honor `core/migrations/README.md:20` ("Silent overwrite
  of customized downstream files is not acceptable at any point"), the
  walker only auto-applies a catalog entry when the target file's
  current sha256 matches one of the recorded baseline hashes for that
  path. If the user has customized the file, the conflict is reported as
  today and an explicit `--accept-theirs <path>` is required. Catalog
  schema therefore stores `{path, baseline_sha256: [string]}`, not bare
  paths. Reference fixture: `tests/migrations/multi-hop/run.sh:105-112`.
- Stage 2.1 is reframed as **extending** the existing 5-source check
  (`scripts/lib/check_version_consistency.py`), not replacing it, and
  drops `core/manifest.template.json` (token file, not a version source).
- Stage 3 checksum fast-path explicitly calls out the preflight
  refactor required (`single_hop.py:74-82` tag validation must move from
  up-front to per-file lazy) so the "no tag fetch attempted" claim is
  achievable.

No files are modified by this plan; only the plan document itself is
updated. The plan targets review gates, not the final delivery gate.

## Global Implementation Rules

- Every stage is independently mergeable and ships with fixtures.
- Python stdlib only for runner code. No new third-party dependencies.
- `acquire_lock` + `try/finally` release in
  `scripts/lib/agent_sync/single_hop.py:106-184` and the analogous block
  in `multi_hop.py` stay byte-identical at the control-flow level.
- `.agent/sync-log.md` is append-only. All new features (backup, restore,
  checksum update) emit additive entries.
- `core/migrations/<version>/migration.json::schema_version` stays at `1`.
  If a field is strictly required for a stage, this plan must call out
  the schema bump in its own "Risk" subsection.
- No change to a target repo's `.gitignore`, per
  `core/README.md:40-45`.
- New fixtures are additive under `tests/migrations/<slug>/`. Existing
  fixture `run.sh` scripts are not edited.

## Baseline Evidence

- `scripts/lib/agent_sync/single_hop.py:97-104` — detects `current`
  version and rejects `current ∉ candidate_sources`. Insertion point for
  auto multi-hop fallback.
- `scripts/lib/agent_sync/single_hop.py:74-82` — upfront tag presence
  validation. Must become lazy for Stage 3 fast-path.
- `scripts/lib/agent_sync/migrations.py:127-` — `expand_file_entries()`
  is the real source of managed source/target mapping; `manifest.json`
  only stores `canonical_files` (`core/manifest.template.json:17`).
  Stage 1.2 preflight and Stage 3 checksum both derive managed paths
  from `expand_file_entries()`, not from manifest.
- `scripts/lib/agent_sync/merge.py` — byte-exact 3-way merge. No
  `compute_base_sha` helper exists; Stage 1.2 adds one explicitly.
- `scripts/lib/check_version_consistency.py` — checks 5 sources:
  `scripts/bootstrap-request.sh`, `.claude-plugin/plugin.json`,
  `.claude-plugin/marketplace.json` (two positions), and
  `CHANGELOG.md`. Stage 2.1 extends, not duplicates.
- `tests/migrations/0.3.0/run.sh:17` — `diff -r` asserts tree equality.
- `tests/migrations/0.5.0/run.sh:119` — exact post-apply status
  `' M .agent/manifest.json\n M .agent/sync-log.md'`.
- `tests/migrations/multi-hop/run.sh:105-112` — documented
  `--accept-theirs scripts/agent-eval.sh` requirement for the
  `0.7.0 → 0.8.0` hop. Baseline for Stage 1.1 conflict catalog.
- `core/release-process.md:7-8` — minor releases require a migration
  dir; patch releases may omit one. `0.11.0` is a **minor release
  shipped without a migration dir**, which violates `:7`. Resolution
  tracked as **D-11 / Q-1**.
- `core/migrations/README.md:341` — append-only sync-log rule.
- `core/README.md:42-43` — bootstrap must not modify target `.gitignore`.

## Implementation Plan

### Stage 1 — Quick wins (target release: 0.12.0)

#### Files To Change

- `scripts/lib/agent_sync/single_hop.py` — auto-fallback branch; defer
  lock acquisition.
- `scripts/lib/agent_sync/cli.py` — add `--no-auto-multi-hop`,
  `--backup`, `--backup-dir`, `--verbose` flags; add `backups` subcommand
  router. `--verbose` opts in to preflight summary on non-TTY stdout.
- `scripts/lib/agent_sync/preflight.py` — add `render_preflight()`.
- `scripts/lib/agent_sync/merge.py` — add
  `compute_base_sha(entry, template_root, version)` helper used by
  preflight, where `entry` is the dict returned by
  `expand_file_entries()` carrying `{source, target, kind, ...}`. The
  helper reads `git show v<version>:<entry["source"]>` (template path),
  hashes it, and compares against `sha256(target/<entry["target"]>)`.
  Source and target paths differ in general (e.g. `core/rulebase.template.md`
  → `.agent/rulebase.md`).
- `scripts/lib/agent_sync/backups.py` — **new** module.
- `scripts/lib/agent_sync/migrations.py` — read optional
  `migration["known_conflicts"]` list (Stage 1.1 catalog).
- `scripts/lib/agent_sync/merge.py` — change `accepted` from
  `list[str]` (paths only, current at
  `scripts/lib/agent_sync/merge.py:54-58`) to `list[AcceptedRecord]`
  where `AcceptedRecord = {path, reason, source}`. Pre-existing
  `--accept-theirs` produces `{reason: "user-flag", source: "cli"}`;
  the Stage 1.1 catalog branch produces
  `{reason: "catalog-baseline-match", source: "<from>-><to> catalog"}`.
  Existing call sites that just want paths use
  `[r.path for r in accepted]`.
- `scripts/lib/agent_sync/sync_log.py` — update **both** accepted-list
  formatters to the D-12 shape `"  - <path> [reason=<reason>,
  source=<source>]"`: the single-hop block at
  `scripts/lib/agent_sync/sync_log.py:28` (function emitting the
  per-apply summary) **and** the multi-hop block at
  `scripts/lib/agent_sync/sync_log.py:76-82`. The pre-existing
  path-only format is dropped on the **writer** side from 0.12.0
  onward. Unit tests in `tests/lib/test_sync_log.py` must exercise
  both code paths so a future divergence between the two formatters
  is caught immediately. Compatibility window on the **reader** side:
  any repo-local sync-log parser introduced here (e.g. doctor, future
  lint hooks) must accept both legacy path-only accepted lines and
  the new `[reason=..., source=...]` lines so existing append-only
  logs written by pre-0.12.0 runners remain parseable. This is one
  of the few invariants this plan deliberately changes; documented
  in **D-12** below.
- `core/migrations/<future>/migration.json` authoring guide — document
  `known_conflicts` field in `core/migrations/README.md`.
- `tests/migrations/auto-fallback/run.sh` — **new** fixture.
- `tests/migrations/backup-create-opt-in/run.sh` — **new** fixture.
- `tests/migrations/backup-restore/run.sh` — **new** fixture.
- `tests/migrations/preflight-output/run.sh` — **new** fixture.
- `CHANGELOG.md` — 0.12.0 entry.
- `README.md` — "Upgrading" section rewrite.

#### Stage 1.1 Auto Multi-hop Fallback With Conflict Catalog

Insertion point: after `current = detect_current_version(manifest)` in
`scripts/lib/agent_sync/single_hop.py:97`, before the current-version
no-op check at line 100 and before `acquire_lock` at line 108.

Logic:

1. If `current not in candidate_sources and current != to_version`:
   a. If `args.no_auto_multi_hop` is set, raise the existing `NoPathError`
      with a hint.
   b. Otherwise **assign `args.to = to_version` when `args.to is None`**
      (single-hop already resolves a default-latest target when `--to`
      is omitted; `run_multi_hop` currently rejects a `None` target at
      `scripts/lib/agent_sync/multi_hop.py:133` with `UsageError`, so
      the fallback path must propagate the resolved version). Then set
      `args.multi_hop = True` and `return run_multi_hop(args, ...)`.
      No single-hop lock has been taken yet, so there is no
      double-lock risk.
2. In `run_multi_hop`, accumulate a
   `carry_catalog_entries: list[CatalogEntry]` from each hop's
   `migration.get("known_conflicts", [])`, where each `CatalogEntry =
   {path: str, baseline_sha256: list[str]}` per the schema in step 3.
   The walker passes catalog entries (not bare paths) to per-hop merge
   so the hash guard in step 4 can run. CLI `--accept-theirs` paths
   remain a separate `set[str]` and are unioned at the merge call site
   only after the hash guard has decided each catalog entry. The two
   inputs **must not** be merged into a single set, otherwise a
   customized file would be silently auto-accepted.
3. `core/migrations/<version>/migration.json` schema v1 gains an
   **optional** field `known_conflicts: [{path, baseline_sha256: [string]}]`.
   Unknown fields are already ignored, so this is additive. Backfill
   entry for `0.8.0/migration.json`:
   `[{"path": "scripts/agent-eval.sh", "baseline_sha256":
   ["<sha of rendered scripts/agent-eval.sh as produced by the 0.7.0
   bootstrap pipeline>"]}]`. The hash list is **multiple** because
   different render-time inputs (e.g. token expansion of
   `{{TEMPLATE_VERSION}}`) produce different bytes for the same logical
   baseline; tests/migrations fixtures provide the empirical set.

   **Governance for `baseline_sha256` values** (documented in
   `core/migrations/README.md` as part of Stage 1.1):
   - Every hash in `known_conflicts[].baseline_sha256` must be
     reproducible from a committed migration fixture. No hand-entered
     or ad-hoc hashes.
   - PRs adding or updating `known_conflicts` must include, in the PR
     body, (a) the exact shell command that produced each hash (e.g.
     `sha256sum <work>/scripts/agent-eval.sh` after running
     `tests/migrations/multi-hop/run.sh` up to the relevant hop), and
     (b) the fixture version / source path the hash came from.
   - Hash catalog changes go through the same review as schema
     changes; reviewers reproduce at least one entry locally before
     approval.
   - Tests must assert the catalog hashes match the fixture's clean
     baseline bytes (not only that apply succeeds). This closes the
     loop against a catalog entry drifting away from its fixture.
4. Per-file decision in `merge.py`:
   - If `sha256(target/<entry.path>)` ∈ `entry.baseline_sha256` →
     auto-accept for this hop. Append to merge's
     `accepted: list[AcceptedRecord]` (per D-12) as
     `{path: entry.path, reason: "catalog-baseline-match",
     source: f"{from}->{to} catalog"}`. Sync-log emits the D-12 line
     `- <path> [reason=catalog-baseline-match, source=<from>-><to> catalog]`.
   - Otherwise → conflict surfaces as today; user must pass explicit
     `--accept-theirs <path>` (which records as `{reason: "user-flag",
     source: "cli"}`). Honors `core/migrations/README.md:20` hard bar.
5. Runner emits preflight lines that distinguish the two states:
   - `"Auto-accepting catalog conflict: scripts/agent-eval.sh
     [reason=catalog-baseline-match]"` (same token as the sync-log
     line per D-12), OR
   - `"Catalog conflict but file customized: scripts/agent-eval.sh
     (sha differs from all known baselines; pass --accept-theirs to
     proceed)"`.

Fixture `tests/migrations/auto-fallback/run.sh`:
- Case 1 (clean fixture, hash matches catalog): builds a `0.4.0`
  fixture (reuse `build_040_fixture` pattern), runs
  `agent-sync.sh --target <fixture> --to 0.10.0 --apply` with **no**
  `--multi-hop`, no `--accept-theirs`. Asserts exit 0, manifest
  `synced_to_template_version == 0.10.0`, sync-log contains the
  multi-hop heading line (existing format `## <ts> multi-hop from
  0.4.0 to 0.10.0` with the `Chain:` line listing intermediate
  versions, per the current `sync_log.py` multi-hop formatter) and the
  D-12 token
  `[reason=catalog-baseline-match, source=0.7.0->0.8.0 catalog]` on
  the line for `scripts/agent-eval.sh`. Stdout contains the
  "auto-walking" notice.
- Case 2 (user-customized file, hash differs): same fixture but
  `echo "# user comment" >> <work>/scripts/agent-eval.sh && git commit`
  before the run. Same command must **fail** at the `0.7.0 → 0.8.0`
  hop with the catalog-but-customized message and exit non-zero.
  Re-running with explicit `--accept-theirs scripts/agent-eval.sh`
  succeeds. This proves the `core/migrations/README.md:20` hard bar.
- Case 3 (no `--to` supplied): run `agent-sync.sh --target <fixture>
  --apply` from the `0.4.0` fixture with no `--to` flag. Asserts exit
  0 and manifest `synced_to_template_version == <latest migratable>`.
  This proves the Stage 1.1 step 1b guard that assigns
  `args.to = to_version` before falling through to `run_multi_hop`
  (otherwise `multi_hop.py:133` raises `UsageError`).
- Case 4 (catalog hash provenance): for each
  `known_conflicts[].baseline_sha256` entry referenced by the matrix,
  recompute the hash from the clean fixture tree at the matching hop
  and assert equality. This is the test leg of the governance rule
  and guards against a catalog entry drifting from its fixture.

Stage 1.1 implementation is still scoped to the existing migration graph
before the D-11 backfill lands. In that pre-backfill state, `0.11.0`
has no migration dir and `single_hop.py:50-53` correctly raises
NoPathError for `--to 0.11.0`. Once the Stage 2.3 Option-A backfill is
merged, latest-migratable advances to `0.11.0` and the AC matrix
expectations below apply to `0.11.0`.

#### Stage 1.2 Rich Preflight Summary

Managed-entry source: iterate `expand_file_entries(template_root,
migration, args.with_adapters, manifest)` and use the full entry dicts
(`{source, target, kind, ...}`). Customization detection per entry:

- `current_sha = sha256(target/<entry["target"]>)` (downstream path,
  e.g. `.agent/rulebase.md`).
- `base_sha = compute_base_sha(entry, template_root, from_version)`
  which wraps `git show v<from>:<entry["source"]>` (template-side path,
  e.g. `core/rulebase.template.md`) and returns `None` if the path did
  not exist at that tag.
- Report statuses: `untouched`, `customized`, `new`, `deleted`.

Source and target are distinct keys in `expand_file_entries` because
template-side paths (`core/...`, `.skills/...`) differ from downstream
paths (`.agent/...`, `scripts/...`). Conflating them produces wrong
hashes for any rendered or relocated file.

Sample output (reference only, exact format in implementation PR):

```
Pre-flight summary
  Target:           /path/to/myrepo
  Current version:  0.4.0
  Target version:   0.10.0
  Walk:             0.4.0 → 0.5.0 → 0.6.0 → 0.7.0 → 0.8.0 → 0.8.1 → 0.9.0 → 0.10.0
  Worktree:         clean
  Customized files: 0
  Planned changes:  63 updates, 4 patches, 0 orphans
  Backup:           disabled (pass --backup to enable)
```

Call sites: `single_hop.py` dry-run branch at line 149 and apply branch
immediately before `apply_writes` at line 159; equivalent site in
`multi_hop.py` rehearsal loop. Output is skipped when stdout is not a
TTY **and** `--verbose` is not set, so CI logs stay short.

#### Stage 1.3 Opt-in Auto-backup

Activation: **only when** `--backup` is passed. Default behavior is
unchanged (this keeps existing fixture asserts green).

Location: `$XDG_CACHE_HOME/agent-bootstrap/backups/<target-sha1>/<id>/`
where `<target-sha1> = sha1(abspath(target))[:12]` and `<id> = <ISO8601>-
<from>-<to>`. Fallback when `$XDG_CACHE_HOME` is unset:
`~/.cache/agent-bootstrap/backups/...` (stdlib `Path.home()`).

Scope: only the files present in the pre-apply `writes` dict plus
`.agent/manifest.json` and `.agent/sync-log.md`. Not a full repo
snapshot.

Layout:

```
<backup_dir>/
  manifest.json             # pre-apply copy
  sync-log.md.snapshot      # pre-apply copy
  files/<relative-path>     # pre-apply content per touched file that
                            #   existed before apply
  meta.json                 # {target, from_version, to_version, mode, entries[], created_at}
```

`meta.json::entries` is the authoritative restore map. Each entry has:

```json
{
  "path": "<relative-target-path>",
  "pre_state": "present" | "absent",
  "sha256": "<sha of pre-apply bytes, or null when absent>"
}
```

`pre_state == "absent"` is the **sentinel for files the migration
creates**. No bytes are stored in `files/<relative-path>` for those.
This is required because Stage 1 migrations frequently introduce new
managed files (e.g. `.agent/constitution.md`); without the sentinel,
restore would silently leave them in place and break the round-trip
contract.

CLI subcommands (thin dispatch in `cli.py`, implemented in
`backups.py`):

- `agent-sync.sh backups list [--target <path>]`
- `agent-sync.sh backups restore <id> [--target <path>]`
- `agent-sync.sh backups prune --keep N [--target <path>]`
- Default retention on next `--backup` apply: keep 5 most recent for the
  same `<target-sha1>`. Configurable via `--keep`.

Restore semantics (corrected vs. revision 1):

- Refuses on dirty worktree (same rule as apply).
- For each entry in `meta.json::entries`:
  - `pre_state == "present"` → overwrite
    `<target>/<entry.path>` with backed-up bytes; verify
    `sha256(written) == entry.sha256` and abort if mismatched.
  - `pre_state == "absent"` → **delete** `<target>/<entry.path>` if it
    currently exists, otherwise leave it absent. This is the sentinel
    handling for files the migration created.
- Rewrites `.agent/manifest.json` from `manifest.json` snapshot.
- **Appends** a new entry to `.agent/sync-log.md` of shape:
  `Restore <id>: reverted N files to state at <from>, source =
  <backup_dir>`. The log is never truncated.
- Does not re-run validation; user re-runs `agent-validate.sh`.

Round-trip contract: after `apply --backup` followed by `backups
restore`, the target tree must be byte-identical to its state
**before** `apply` (not just byte-identical to backed-up files).
Fixture `tests/migrations/backup-restore/run.sh` verifies via
`git status` and `git diff` against the pre-apply commit.

Because the backup dir lives outside the target repo, no
`.gitignore` changes are required anywhere.

#### Stage 1 Tests

- `tests/migrations/auto-fallback/run.sh` — see Stage 1.1 above.
- `tests/migrations/backup-create-opt-in/run.sh` — run with `--backup`,
  assert backup dir exists under a temp `XDG_CACHE_HOME`, assert target
  repo `git status` is identical to an existing fixture's (no new files
  inside target).
- `tests/migrations/backup-restore/run.sh` — apply with `--backup`,
  restore, assert touched files byte-identical to pre-apply, assert
  sync-log has two new lines (apply + restore), not truncated.
- `tests/migrations/preflight-output/run.sh` — dry-run emits the header
  block and customization count.

Regression proofs for existing fixtures (no edits):
- `tests/migrations/0.3.0/run.sh` — `diff -r` must still pass because no
  default-on feature writes into the target.
- `tests/migrations/0.5.0/run.sh:119` — post-apply status stays exactly
  `' M .agent/manifest.json\n M .agent/sync-log.md'`.

#### Stage 1 Exit Criteria

- Auto multi-hop fallback plus hash-guarded `known_conflicts` catalog
  lets the AC-1 matrix (`0.3.0`, `0.4.0`, `0.8.1`, `0.9.0` → latest
  migratable) succeed with only `--target --to --apply`.
- The customized-file Case 2 in `auto-fallback/run.sh` proves the
  `core/migrations/README.md:20` hard bar is not regressed.
- Preflight output is visible in TTY dry-runs and applies.
- `--backup` produces a snapshot that round-trips byte-identically to
  pre-apply state, including absent-file sentinel handling; default
  off keeps old fixtures green.
- Sync-log emits the D-12 `[reason=..., source=...]` token for every
  accepted conflict, and `tests/lib/test_sync_log.py` passes.
- Existing fixtures pass without modification.
- `scripts/agent-validate.sh` is unchanged (no hook guard shipping here).

#### Stage 1 Risk

- Auto-fallback silently routing through a revoked intermediate version.
  Mitigation: schema v1 gains optional
  `migration["block_auto_walk_through"]: bool`; walker refuses to chain
  through when true. Default false = no behavior change. Documented in
  `core/migrations/README.md`.
- Backup disk growth. Mitigation: default `--keep 5`; `prune` command.

### Stage 2 — Release ergonomics (target release: 0.13.0)

#### Files To Change

- `scripts/bump-version.sh` — **new** helper.
- `scripts/lib/check_version_consistency.py` — extend error messages /
  add `--fix` flag that calls the bumper.
- `.github/workflows/ci.yml` — wire bumper check (already present;
  confirm coverage).
- `scripts/lib/agent_sync/doctor.py` — **new** module.
- `scripts/agent-sync.sh` — add `doctor` subcommand.
- `core/release-process.md` — document bump-version flow and the
  resolution of D-11 / Q-1 (the `0.11.0` minor-without-migration
  exception). Whichever option ships, this file is the source of truth
  and must be updated.
- `core/release-tags.md` — backfill rows for `0.4.0` through the
  current latest release (`core/release-tags.md:5` currently stops at
  `0.3.1`) and have `scripts/bump-version.sh` append a row for every
  new version. `core/release-process.md:31` requires this file to map
  every released tag.

#### Stage 2.1 Version Bump Automation (extends existing check)

The existing `scripts/lib/check_version_consistency.py` already covers 5
canonical sources. This stage **does not** introduce a new source of
truth. It automates the write side:

- `scripts/bump-version.sh <new-version>` updates in one pass:
  `scripts/bootstrap-request.sh`, `.claude-plugin/plugin.json`,
  `.claude-plugin/marketplace.json` (two positions), `CHANGELOG.md`
  (inserts a new `## <version> - <today>` heading above the prior top
  entry), **and `core/release-tags.md`** (inserts a row
  `| <version> | v<version> | <PENDING> | ... |` in semver order,
  which the human finalises after `git tag -a` per
  `core/release-process.md:28-31`). The `<PENDING>` sentinel is
  enforced by `check_version_consistency.py --strict` against the
  latest-semver row (not simply the topmost row, since the file is
  maintained in semver order): if that row still contains `<PENDING>`
  after the tag-push step, the release CI job fails.
- Atomic via `tempfile + os.replace`.
- Re-runs `check_version_consistency.py` at the end; non-zero exit
  rolls back (undo written via the staged tempfile copies).
- `core/manifest.template.json` is **not** updated here because it
  stores the token `{{TEMPLATE_VERSION}}` (`core/manifest.template.json:2`),
  not a concrete version.

CI check already exists at `ci.yml:106`; this stage only verifies the
bumper itself under `tests/lib/test_bump_version.sh` (new).

#### Stage 2.2 Doctor Subcommand

New module: `scripts/lib/agent_sync/doctor.py`. Subcommand:
`agent-sync.sh doctor [--target <path>] [--json]`. Checks:

- `.agent/manifest.json` exists and parses.
- `synced_to_template_version` is valid semver.
- If template_root is a git repo, report `N releases behind latest
  migratable version` where "latest migratable" = max version with a
  `core/migrations/<ver>/migration.json`. If the latest release
  (`CHANGELOG.md`) is newer than latest migratable, print a note:
  `"Template 0.11.0 is released as a minor without a migration
  directory (violating core/release-process.md:7); see D-11 for the
  resolution path. doctor cannot offer an upgrade target beyond
  0.10.0 until D-11 is resolved."`
- For each path returned by `expand_file_entries(..., latest_migration)`,
  report customized vs. untouched using `compute_base_sha` from Stage
  1.2.
- Detect orphans (paths in manifest.canonical_files scope that were
  removed from disk).
- `--json` emits a machine-parseable document; default is human text.

Doctor is read-only. It does not fix state; `--fix` is deferred to a
future stage if demand appears.

#### Stage 2.3 Implement D-11 (Option A): Backfill `0.11.0` Migration

This is the open question flagged by reviewer finding H1. `0.11.0` is
a minor release that shipped without `core/migrations/0.11.0/`,
violating the rule at `core/release-process.md:7` that minor releases
must have a migration dir "even when the migration is intentionally
empty". This is **not** a patch-without-migration case (that rule at
`:8` covers only patch releases).

Selected behavior (final):

- Backfill `core/migrations/0.11.0/migration.json` mirroring the
  existing `core/migrations/0.5.0/migration.json` shape. Concretely:
  `{schema_version: 1, version: "0.11.0", from_versions: ["0.10.0"],
  to: "0.11.0", safe_overwrite: [], patches: [], manifest_updates:
  {replace: {template_version: "0.11.0",
  synced_to_template_version: "0.11.0"}, replace_from_git_tag:
  {synced_to_template_commit: "0.11.0"}, append_to_array_unique:
  {notes: "Synced to v0.11.0 (no downstream-facing changes)."},
  merge_array_unique: {}}}`.
- Empty `manifest_updates: {}` is **wrong** because
  `scripts/lib/agent_sync/manifest_ops.py:55` would otherwise leave
  `synced_to_template_version` and `synced_to_template_commit` stale.
- No runner behavior change is required for this fix.

Release-tags scope note:

- D-11 implementation PR must add the `0.11.0` row now (policy repair).
- The broader `core/release-tags.md` backfill (`0.4.0` through latest)
  remains Stage 2.1 scope unless maintainers decide to complete it in
  the same PR.

#### Stage 2 Tests

- `tests/lib/test_bump_version.sh` — bumper updates 5 sources, idempotent
  on re-run, rollback works.
- `tests/lib/test_doctor.sh` — doctor output schema is stable under
  `--json`, human output contains expected lines.
- `tests/migrations/0.11.0/run.sh` — new fixture proving
  `0.10.0 -> 0.11.0` apply updates manifest sync metadata correctly and
  remains idempotent.
- `tests/migrations/auto-fallback/run.sh` matrix/default-latest case is
  updated post-backfill so latest-migratable resolves to `0.11.0`.

#### Stage 2 Exit Criteria

- Releasing a new version is one command plus a human tag push.
- `agent-sync.sh doctor` gives a self-service diagnostic that reconciles
  the "released vs. migratable" asymmetry.

#### Stage 2 Risk

- The Stage 2.3 decision blocks the AC refactor at §Acceptance Criteria
  below. If undecided at merge time, keep Option B's "0 exit on minor
  above latest migratable" behind a flag (note: this is a
  minor-without-migration case per D-11, not patch-without-migration).

### Stage 3 — Trust layer (target release: 1.0.0)

#### Files To Change

- `scripts/lib/agent_sync/manifest_ops.py` — extend manifest schema
  read/write with `tracked_files` map.
- `scripts/lib/agent_sync/merge.py` — add checksum fast-path branch,
  update `tracked_files` post-apply.
- `scripts/lib/agent_sync/single_hop.py:74-82` — move tag existence
  check out of this block. New policy: tag existence is verified
  **per file, lazily**, only when that file falls through to 3-way
  merge.
- `scripts/lib/agent_sync/multi_hop.py:146` — mirror the same lazy
  strategy.
- `scripts/lib/agent_sync/git_ops.py` — add `try_git_show(path,
  version) -> Optional[bytes]` that returns `None` on missing tag
  instead of raising.
- `core/migrations/README.md` — document `tracked_files` schema.
- New migration `core/migrations/1.0.0/migration.json` with a **backfill
  step** that walks every managed file at post-apply state and populates
  `tracked_files[path].synced_checksum_sha256`.
- Fixtures below.

#### Stage 3.1 Schema Additions (manifest)

Additive only. Backward compatible: manifest without `tracked_files`
triggers the current 3-way merge path for every file.

```json
{
  "tracked_files": {
    ".agent/rulebase.md": {
      "synced_at_version": "0.10.0",
      "synced_checksum_sha256": "abc123..."
    }
  }
}
```

Write order (revised in Stage 3.1 implementation): the writer is
invoked from `plan_manifest` immediately before serializing
`.agent/manifest.json`, looping every `writes[path]` and setting
`tracked_files[path].synced_checksum_sha256 = sha256(new_content)` and
`synced_at_version = migration["to"]`. This is functionally equivalent
to a post-`apply_writes` loop because the bytes hashed are exactly
those queued for write — `apply_writes` is the single funnel and
performs no transformation. Computing during planning lets the
manifest's own bytes capture the new `tracked_files` map in the same
write, avoiding a second manifest write per hop. The Stage 3.2
fast-path uses the same `tracked_files` schema; revisit only if
fast-path semantics need a true post-write hook.

#### Stage 3.2 Merge Decision (merge.py)

Per entry returned by `expand_file_entries` (each carries
`{source, target, kind, ...}`):

1. If `manifest.tracked_files[entry["target"]]` absent → current 3-way
   merge path (unchanged). Tag `v<from>` and `v<to>` must exist;
   preflight reports "tag-required" for this entry.
2. Else compute `current_sha = sha256(target/<entry["target"]>)`.
3. If `current_sha == tracked_files[entry["target"]].synced_checksum_sha256`:
   **fast-path**. Need only `theirs` from the template side
   (`git show v<to>:<entry["source"]>`). If `v<to>` is missing, fall
   through to (4).
4. Otherwise fall through to 3-way merge; require both tags; raise
   `UsageError` with the existing "try git fetch --tags" hint.

The `tracked_files` map is keyed by **downstream target path** because
that is what the user sees on disk; the source path is recovered via
`expand_file_entries` at runtime, not stored in the manifest. This
keeps schema small and avoids stale entries when a migration relocates
a source.

The preflight pass emits a per-path classification line and sums:
`fast-path: N, 3-way-merge: M, tag-required-but-missing: K`.

This design makes the "no tag fetch attempted" claim scoped: it holds
only when all tracked files are unmodified. Mixed modifications still
require tags, as today. That scoping is the correction to revision 1.

#### Stage 3.3 Backfill Migration (1.0.0)

- One-shot pass at `agent-sync.sh --to 1.0.0 --apply`:
  - Enumerate paths from `expand_file_entries` for the 1.0.0 migration
    **plus** every path under `manifest.canonical_files` scope.
  - For each, compute and store `synced_checksum_sha256 = sha256(disk
    content)` and `synced_at_version = current` (not `to`), because the
    content on disk is what the user has right now, and the checksum is
    declaring "this is my baseline".
  - After the rest of the 1.0.0 migration writes run, the post-apply
    loop at §Stage 3.1 refreshes these entries for touched files.

Backfill scope decision (open question O-3 in revision 1, now resolved):
**"touched + canonical scope on first run"**. Enumerating every file on
disk is O(n) on fixtures (<1 s) and removes the need for a second
backfill pass in a later release.

#### Stage 3.4 Semantic-release Scaffold (mechanical release)

Mechanical only. Migration JSON authoring stays human.

- `commitlint` config + conventional-commit enforcement in CI.
- `semantic-release` config that: runs `scripts/bump-version.sh` (Stage
  2.1), generates CHANGELOG entry, creates annotated tag via human
  approval step (no silent tag push; `core/release-process.md:21` still
  applies — tag push is human-triggered).
- `scripts/scaffold-migration.sh <from> <to>` diffs tags under `core/`
  and emits a skeleton `migration.json` with `safe_overwrite` entries
  pre-populated.

#### Stage 3 Tests

- `tests/migrations/fastpath-clean/run.sh` — untouched managed file,
  fast-path taken, `v<from>` tag deliberately absent (ephemeral repo
  without that tag) proves no base-tag fetch.
- `tests/migrations/fastpath-modified/run.sh` — user-edited managed
  file, checksum mismatch, falls back to 3-way merge, existing tag
  hint reappears.
- `tests/migrations/checksum-backfill/run.sh` — runs the 1.0.0 backfill
  from a 0.10.0 fixture; asserts every managed path now has
  `tracked_files[path].synced_checksum_sha256`.
- `tests/migrations/checksum-refresh/run.sh` — after a subsequent hop,
  asserts checksums updated to new content.

#### Stage 3 Exit Criteria

- With tracked_files populated and no local modifications, upgrading
  does not require `v<from>` tag presence for fast-path files.
- Byte-exact 3-way merge still enforced for modified files.
- All legacy fixtures pass; new fixtures pass.

#### Stage 3 Risk

- Silent overwrite if a user edits a managed file in a way that
  coincidentally preserves sha256. Mitigation: not defensible in
  general, but `sync-log.md` records the fast-path decision so audit is
  possible. Document explicitly in `core/migrations/README.md`.
- Schema additions risk stale entries if a file is renamed in a later
  migration. Mitigation: on rename, the old path's entry is deleted in
  `manifest_updates` of that migration.

## Acceptance Criteria

AC-1 — One-command upgrade across a covered version matrix.
From each starting version listed below, a single invocation of
`scripts/agent-sync.sh --target <path> --to <latest-migratable> --apply`
succeeds with no additional flags, provided every conflict encountered
is either (a) on a file the user has not modified, or (b) recorded in
the `migration.known_conflicts` catalog **and** the file's current
sha256 matches one of the catalog's `baseline_sha256` entries.
Customized files outside both conditions still raise a conflict and
require explicit `--accept-theirs`, per `core/migrations/README.md:20`.

Minimum required version matrix (each is its own fixture case in
`tests/migrations/auto-fallback/run.sh` or a sibling fixture):

- `0.3.0` → latest migratable (covers earliest supported `from`).
- `0.4.0` → latest migratable (mid-chain, 6+ hops).
- `0.8.1` → latest migratable (post-eval-rename hop).
- `0.9.0` → latest migratable (recent, exercises shorter chain).

"Latest migratable" resolves to the maximum version with a
`core/migrations/<ver>/migration.json` directory. After D-11 Option-A
backfill merges, this advances to `0.11.0`.

Evidence: `tests/migrations/auto-fallback/run.sh` (matrix loop).
Verification: fixture run plus grep of stdout for the auto-walk notice,
and grep of `.agent/sync-log.md` for the literal token
`reason=catalog-baseline-match` on the `0.7.0 → 0.8.0` hop in matrix
entries that traverse it. The sync-log line shape is fixed by D-12
(`- <path> [reason=catalog-baseline-match, source=<from>-><to> catalog]`);
fixtures grep that exact substring, not any older `auto-accept-theirs
(...)` wording.

AC-2 — Existing fixtures remain unchanged.
No edits to any `tests/migrations/<version>/run.sh` file. Evidence:
`git diff --stat origin/main tests/migrations/` shows only additions of
new `<slug>/run.sh` files. Verification: CI runs the whole fixture
matrix and `git diff --stat` is inspected in PR review.

AC-3 — Sync-log invariant and doctor write-freedom.
On apply, multi-hop, backup, and restore flows, `.agent/sync-log.md`
is only ever appended to. No existing line is modified or removed.
`agent-sync.sh doctor` performs **no writes** to the target repo at
all (not to sync-log, not to manifest, not to any managed file).
Evidence: diff check in `tests/migrations/backup-restore/run.sh` for
the append-only contract; `git status` and stat-mtime check before/
after doctor in `tests/lib/test_doctor.sh` for the no-write contract.
Verification: fixture asserts the pre-apply log content is a prefix of
the post-restore log content; doctor test asserts target tree is
byte-identical post-doctor.

AC-4 — Backup is off by default and external to the target.
With no `--backup` flag, `git status` after apply is byte-identical to
baseline fixtures; with `--backup`, the snapshot lives under
`$XDG_CACHE_HOME/agent-bootstrap/backups/...` and restore round-trips
every touched file. Verification:
`tests/migrations/backup-create-opt-in/run.sh` plus
`tests/migrations/backup-restore/run.sh`.

AC-5 — Doctor reconciles released vs. migratable.
`agent-sync.sh doctor --target <repo>` prints both "latest released
template version" and "latest migratable template version" when they
differ. Verification: `tests/lib/test_doctor.sh` scenario simulating a
future released-vs-migratable mismatch (D-11 is resolved by Option A).

AC-6 — Checksum fast-path does not require base tag.
With `tracked_files` populated and an unmodified managed file, an
upgrade hop fetches only `v<to>` (for `theirs`). If `v<from>` is absent,
the hop still completes for that file. Verification:
`tests/migrations/fastpath-clean/run.sh` in an ephemeral repo missing
`v<from>`.

AC-7 — Schema changes are additive.
A repo with a pre-1.0.0 `.agent/manifest.json` lacking `tracked_files`
runs the 0.12.0 and 0.13.0 migrations without error and without
requiring backfill. Backfill only runs on the 1.0.0 hop. Verification:
`tests/migrations/0.5.0/run.sh` chained with
`tests/migrations/auto-fallback/run.sh`.

AC-8 — Release bumper covers 5 canonical version sources plus
`core/release-tags.md` placeholder.
`scripts/bump-version.sh 0.13.0` updates all 5 sources checked by
`scripts/lib/check_version_consistency.py` (leaving that checker
passing) **and** appends a `| 0.13.0 | v0.13.0 | <PENDING> | ... |` row
to `core/release-tags.md`. `core/release-tags.md` is maintained in
semver order, so the `<PENDING>` sentinel is enforced by
`check_version_consistency.py --strict` across **any** row whose
version matches the CHANGELOG's top entry (equivalently: any row still
containing `<PENDING>` for the latest released semver). A release CI
job fails if that row is not finalised after the tag-push step.
`core/manifest.template.json` is intentionally not touched. Verification:
`tests/lib/test_bump_version.sh` covers both writes and the
strict-mode failure path.

AC-9 — Plan discipline.
This plan document passes `scripts/agent-validate-plan.sh
docs/2026-05-05-migration-ux-improvement-plan.md` with 0 High findings.
Verification: CI runs `agent-validate-plan.sh` on changed plan files.

## Existing Behaviors Preserved

One anchor evidence block is embedded below (per the BEH-001 contract),
backed by a content hash so reviewers can detect drift. All other
behaviors carry inline `` `path:line` `` citations, which the validator
accepts for BEH-002.

<!-- current-code path=core/README.md lines=42-43 ref=HEAD region_sha256=ffcf48d655b3d6d44c92a7d82241d7c1c87a5b35f553fd6a56e7cc0d45cd51be -->
`.gitignore` if they prefer not to commit generated telemetry. Bootstrap does
not modify the target repository's `.gitignore`.
<!-- /current-code -->

This anchor protects the "bootstrap never modifies target `.gitignore`"
invariant that forces Stage 1.3 backups to live in an external cache.

Behaviors preserved (citation on the `-` line per BEH-002):

- `scripts/lib/agent_sync/merge.py:28` — byte-exact 3-way merge remains the default merge path when a file has been modified.
- `core/release-process.md:18` — tag-is-source-of-truth contract; 3-way merge still resolves `base` from `git show v<from>:<path>`.
- `core/migrations/README.md:341` — append-only `.agent/sync-log.md` rule, unchanged.
- `scripts/lib/agent_sync/single_hop.py:88-91` — clean-worktree requirement for `--apply` unless `--allow-dirty`.
- `scripts/lib/agent_sync/single_hop.py:106-184` — lock acquisition and try/finally release preserved 1:1.
- `core/README.md:42-43` — bootstrap never modifies the target repo's `.gitignore` (see anchor block above).
- `tests/migrations/0.3.0/run.sh:17` — `diff -r` tree-equality assertion still passes without edits.
- `tests/migrations/0.5.0/run.sh:119` — exact 2-file post-apply status still passes without edits.
- `core/manifest.template.json:17` — `manifest.canonical_files` remains the only pre-1.0.0 file index; `tracked_files` is strictly additive.
- `tests/migrations/multi-hop/run.sh:105-112` — known-conflict carry in auto multi-hop matches the existing manual `--accept-theirs` usage.

## Decision Ledger

| Decision | Chosen Behavior | Rationale | Alternatives Rejected | Caller/User Impact | Verification |
|----------|-----------------|-----------|-----------------------|--------------------|--------------|
| D-1 Auto multi-hop fallback trigger | Fallback fires only when `current ∉ candidate_sources and current != to_version` at `scripts/lib/agent_sync/single_hop.py:97-104` | Narrowest condition that unblocks the 0.8.1 → latest case without bypassing direct migrations | Always auto-chain through multi-hop (loses single-hop idempotency tests); require explicit `--multi-hop` forever (current UX pain) | User no longer needs `--multi-hop` when `--to` is non-adjacent; no change for adjacent upgrades | `tests/migrations/auto-fallback/run.sh` asserts fallback; existing `tests/migrations/0.9.0/run.sh` proves single-hop unchanged |
| D-2 `--backup` default state | **off** | Default-on would write `.agent/.sync-backups/` and break `tests/migrations/0.5.0/run.sh:119` exact-status assertion | Default-on with fixture rewrites; default-on with `.gitignore` patch (forbidden by `core/README.md:42-43`) | Users must opt in; fresh users have no silent behavior change | `tests/migrations/backup-create-opt-in/run.sh` with and without flag |
| D-3 Backup retention limit | Keep 5 most recent per `<target-sha1>`; user-overridable via `--keep N` (count limit, not size limit) | Bounds disk size growth on repeated applies; aligns with claudekit precedent | Unbounded count (disk risk); keep 1 (loses history); time-based limit (complex) | Old backups auto-pruned; CI can raise `--keep` to extend retention count | `tests/migrations/backup-restore/run.sh` seeds 7, asserts retention limit 5 holds |
| D-4 Backup location | `$XDG_CACHE_HOME/agent-bootstrap/backups/<target-sha1>/<id>/`, fallback `Path.home() / ".cache" / ...` | Honors `core/README.md:42-43` (no target `.gitignore` modification) | In-target `.agent/.sync-backups/` (violates invariant); system `/tmp` (ephemeral) | Users run `backups restore` from any cwd via `--target` resolution | Fixture sets ephemeral `$XDG_CACHE_HOME`, asserts target tree unchanged |
| D-5 Restore + sync-log | Append a single `Restore <id>: reverted files to state at <from>` entry; log is never truncated | `core/migrations/README.md:341` invariant is append-only | Truncate-to-snapshot (breaks invariant); parallel restore-log file (audit split) | Audit trail remains linear; `tail sync-log.md` shows both apply and restore | `tests/migrations/backup-restore/run.sh` asserts pre-log is a prefix of post-log |
| D-6 `tracked_files` schema | Additive map keyed by relative path; absent map = current 3-way path | Backward compat with pre-1.0.0 manifests (`core/manifest.template.json:17`) | Bump `schema_version` to 2 (forces all migration JSON to be re-validated); store checksums in separate file (state split) | Old repos keep working until they hit the 1.0.0 backfill hop | AC-7 fixture chain |
| D-7 Stage 3 backfill scope | All `expand_file_entries` paths + `canonical_files` scope walked once at the 1.0.0 hop | One-shot at minor-bump boundary; avoids a second backfill later | Backfill only touched files (leaves coverage gaps); lazy per-file backfill on first access (user-surprising) | First 1.0.0 apply is O(n) in managed files; negligible on fixtures | `tests/migrations/checksum-backfill/run.sh` |
| D-8 Degraded: missing `v<from>` tag with fast-path mismatch | Fall through to 3-way merge and surface the existing tag-required error; never silently skip or overwrite | Prevents data loss when checksum mismatches but base tag is unavailable | Auto-apply `theirs` (data loss); skip file silently (partial apply) | User sees actionable error pointing to `git fetch --tags`; no corruption | `tests/migrations/fastpath-modified/run.sh` in ephemeral repo without `v<from>` |
| D-9 Degraded: `$XDG_CACHE_HOME` unset or unwritable | Fall back to `Path.home() / ".cache"`; if that is still unwritable, fail with actionable error and do **not** apply | Avoids partial apply where backup silently disappears | Proceed without backup (user loses recovery); write inside target (violates D-4) | User gets a clear early-exit message; `--apply` is atomic w.r.t. backup | Unit test in `tests/lib/test_backups.py` simulating unwritable cache |
| D-10 Version sources for bumper | 5 canonical sources (align with `scripts/lib/check_version_consistency.py`); exclude `core/manifest.template.json` | `core/manifest.template.json:2` uses the `{{TEMPLATE_VERSION}}` token, not a literal | Treat the template file as a 6th source (would rewrite a token into a literal and break bootstrap rendering) | Maintainers run one command per release; CI enforces parity | `tests/lib/test_bump_version.sh` |
| D-11 Minor release `0.11.0` missing migration dir | **FINAL (selected): Option A** — backfill `core/migrations/0.11.0/migration.json` mirroring the `core/migrations/0.5.0/migration.json` shape — `{schema_version: 1, version: "0.11.0", from_versions: ["0.10.0"], to: "0.11.0", safe_overwrite: [], patches: [], manifest_updates: {replace: {template_version: "0.11.0", synced_to_template_version: "0.11.0"}, replace_from_git_tag: {synced_to_template_commit: "0.11.0"}, append_to_array_unique: {notes: "Synced to v0.11.0 (no downstream-facing changes)."}, merge_array_unique: {}}}`. **Empty `manifest_updates: {}` is incorrect** — it would leave `synced_to_template_version` and `synced_to_template_commit` stale per `scripts/lib/agent_sync/manifest_ops.py:55`. | Restores `core/release-process.md:7` compliance with no runner-surface expansion; preserves the existing migration contract. | Empty `manifest_updates: {}` (manifest remains stale); policy-amend Option B (not selected). | Unblocks AC-1 so latest migratable can advance to `0.11.0` once this backfill lands. | Verified by new `tests/migrations/0.11.0/run.sh`; release-tags handling split: add `0.11.0` now, broader row backfill remains Stage 2.1 unless combined deliberately. |
| D-12 Accepted-record schema in merge.py / sync-log.py | Replace `accepted: list[str]` with `list[AcceptedRecord]` where `AcceptedRecord = {path, reason, source}`. Sync-log line becomes `- <path> [reason=<reason>, source=<source>]` | Stage 1.1 hash-guarded catalog needs a machine-readable reason in the audit trail; bare path strings cannot distinguish user-flag from catalog auto-accept | Embed reason in path string (parsing-fragile); separate catalog-accept log file (audit split, harder to grep) | Tooling that greps sync-log gains a stable token; existing sync-log readers must update; this plan deliberately bumps the format and updates tests in lockstep | `tests/migrations/0.5.0/run.sh:119` continues to pass because that fixture has zero accepted entries (renders `- none`). Format-shape tests in `tests/lib/test_sync_log.py` cover both rendering and parsing |

## Test Delta

| Test | Action | Why |
|------|--------|-----|
| `tests/migrations/auto-fallback/run.sh` | ADD | Matrix loop over `0.3.0`, `0.4.0`, `0.8.1`, `0.9.0` → latest migratable (AC-1); Case 2 customized-file conflict for `core/migrations/README.md:20` hard bar; Case 3 no-`--to` fallback exercises the `args.to = to_version` guard against `multi_hop.py:133`; Case 4 catalog-hash provenance recompute enforces the governance rule |
| `tests/lib/test_sync_log.py` | ADD | Locks the new `AcceptedRecord` rendering in **both** `sync_log.py:28` (single-hop) and `sync_log.py:76-82` (multi-hop) formatters, plus the reader-side compat window that still parses legacy path-only accepted lines; required by D-12 format change |
| `tests/migrations/preflight-output/run.sh` | ADD | Greps Stage 1.2 dry-run header and customization count |
| `tests/migrations/backup-create-opt-in/run.sh` | ADD | Asserts D-2 default-off behavior and D-4 external cache location |
| `tests/migrations/backup-restore/run.sh` | ADD | Covers D-3 retention and D-5 append-only restore invariant |
| `tests/lib/test_bump_version.sh` | ADD | Exercises D-10 5-source bumper + rollback |
| `tests/lib/test_doctor.sh` | ADD | Verifies Stage 2.2 human and `--json` output, plus Stage 2.3 released-vs-migratable note |
| `tests/migrations/fastpath-clean/run.sh` | ADD | D-8 happy path: unmodified file + missing `v<from>` tag + populated `tracked_files` |
| `tests/migrations/fastpath-modified/run.sh` | ADD | D-8 degraded path: checksum mismatch falls through to 3-way merge |
| `tests/migrations/checksum-backfill/run.sh` | ADD | D-7 one-shot backfill at the 1.0.0 hop |
| `tests/migrations/checksum-refresh/run.sh` | ADD | Stage 3.1 post-apply loop updates `synced_checksum_sha256` |
| `tests/lib/test_backups.py` | ADD | D-9 unwritable cache edge cases |
| `tests/migrations/0.3.0/run.sh` | KEEP | `diff -r` assertion must continue to pass without edits (AC-2) |
| `tests/migrations/0.5.0/run.sh` | KEEP | Exact 2-file post-apply status must continue to pass (AC-2) |
| `tests/migrations/multi-hop/run.sh` | KEEP | Existing manual-flag multi-hop scenario remains valid |

No existing fixture's `run.sh` is modified; `git diff --stat
tests/migrations/` across all three stages shows only additions.

## Verification

Per-stage fixtures listed in the Implementation Plan run via the same
loop CI uses today (`.github/workflows/ci.yml:99-103`):

```bash
for f in tests/migrations/*/run.sh; do bash "$f"; done
```

No `tests/run_all.sh` aggregator exists in the repo; do not invent one
in this plan. Additional verification steps:

- `scripts/agent-validate-plan.sh docs/2026-05-05-migration-ux-improvement-plan.md`
  reports 0 High and 0 Medium findings (AC-9). Run locally before merge.
- `scripts/lib/check_version_consistency.py` is run after every
  `scripts/bump-version.sh` invocation in Stage 2.
- Each stage's PR must include:
  - All new fixtures listed in its "Tests" subsection.
  - A `git diff --stat tests/migrations/` summary in the PR body
    proving no existing fixture was edited.
  - An `agent-validate.sh` run on a representative fixture target.
- Manual smoke test for Stage 1.1: take a real downstream repo at
  `0.8.1`, run `--to 0.10.0 --apply`, confirm success without
  `--multi-hop`.

## Open Questions

- Q-1: How should the project handle the `0.11.0` minor release that
  shipped without a `core/migrations/0.11.0/` directory, contrary to
  `core/release-process.md:7`?
  - RESOLVED: Option A selected. Backfill
    `core/migrations/0.11.0/migration.json` with required
    `manifest_updates` and add `0.11.0` release-tags row in the D-11
    implementation PR. Option B remains documented only as a rejected
    alternative.

- Q-2: Should `migration["block_auto_walk_through"]` ship in Stage 1.1
  or wait until a concrete need arises?
  - RESOLVED: ship in Stage 1.1, default false. Documented risk
    mitigation outweighs the cost of one unused optional field.

- Q-3: Backfill scope for Stage 3.1 — only files in the active
  migration, or every managed file on first run?
  - RESOLVED: every managed file on first run (touched + canonical
    scope). See Stage 3.3 rationale.

- Q-4: Should Stage 2 add a zip release artifact?
  - DEFERRED: moved to Backlog. Current runner depends on `.git/` for
    baseline reads (`scripts/lib/agent_sync/migrations.py:103-124`).
    A zip becomes viable only after a baseline-provider abstraction
    that can read from a pre-extracted tree or prefetched blobs.

- Q-5: Should a self-contained `bin/agent-sync` fetcher be introduced
  now to close the "must clone template" gap?
  - DEFERRED: depends on Q-4. Fetcher needs a zip or equivalent
    artifact to download; without that, `git clone --depth 1 --tag
    v<latest>` already suffices.

## Backlog

- Zip release artifact + self-contained `bin/agent-sync` fetcher
  (blocked on baseline-provider abstraction — see Q-4).
- Manifest 3-tier ownership (`template-managed | user-editable |
  user-created`) as a superset of `tracked_files`.
- TUI wizard — only if Stages 1–3 do not achieve the one-command goal
  in practice.
- Single-hop / multi-hop code path unification.
- Doctor `--fix` auto-heal.

## Sequence Summary

```
Stage 1 (0.12.0)  ─┬─ 1.1 auto multi-hop + known_conflicts catalog
                   ├─ 1.2 rich preflight + compute_base_sha helper
                   └─ 1.3 opt-in --backup + restore (external cache dir)

Stage 2 (0.13.0)  ─┬─ 2.1 bump-version.sh + extend existing 5-source check
                   ├─ 2.2 agent-sync.sh doctor (read-only)
                   └─ 2.3 implement D-11 Option-A backfill (`0.11.0`)

Stage 3 (1.0.0)   ─┬─ 3.1 tracked_files schema (additive)
                   ├─ 3.2 checksum fast-path + lazy per-file tag check
                   ├─ 3.3 backfill migration at 1.0.0 hop
                   └─ 3.4 semantic-release scaffold + migration scaffolder

Backlog (2.x)     ─── zip artifact, self-contained fetcher, 3-tier
                      ownership, TUI, doctor --fix
```

End of plan.
