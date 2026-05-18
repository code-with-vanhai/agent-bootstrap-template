# Stage 4 — Agent Coordination Protocol

Status: Implemented in 1.1.0 (commit `341f235c`)
Owner: Maintainers (agent-bootstrap-template)
Parent proposal: [`docs/2026-05-13-gate-safety-validation-improvements-proposal.md`](../../2026-05-13-gate-safety-validation-improvements-proposal.md)

## Goal

Provide advisory file-path locking for multi-agent scenarios sharing a
single working tree on a single machine. The lock is acquired
atomically through an `O_CREAT|O_EXCL` open on a JSON file under
`.agent/locks/`, expires by a configurable TTL, and is released either
explicitly by the caller or automatically when a wrapper `agent-lock.sh
run` subcommand's `trap EXIT INT TERM HUP` fires. This stage delivers
tooling and documentation, not enforcement.

## Background and Current Code

The only existing concurrency guard in this repo is the sync lock used
by `agent-sync`. It already establishes the `O_CREAT|O_EXCL` pattern
and the `.agent/.sync.lock` location convention this stage reuses for
its per-agent locks:

<!-- current-code path=scripts/lib/agent_sync/preflight.py lines=43-62 ref=341f235ccb425acd0fd60bbefd26dbe942384119 region_sha256=ac2b8dabb609ed2331804af848f057302a2e600907ab7e65db0e6edb3bca81fb -->
```python
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
```
<!-- /current-code -->

The current `.gitignore` is two lines long and has no entry for
`.agent/locks/`. This stage adds an idempotent anchored patch so the
new lock directory is ignored everywhere it is created:

<!-- current-code path=.gitignore lines=1-2 ref=341f235ccb425acd0fd60bbefd26dbe942384119 region_sha256=524a80550d87cbe8a0ec6e066a3ae7f223a0f4fad99d0bce186d880e31506edf -->
```
__pycache__/
*.pyc
```
<!-- /current-code -->

Ownership today is documentation-only — the template ownership file
maps path patterns to role labels but does not gate anything at
runtime. This is precisely why a separate advisory lock is needed:

<!-- current-code path=core/ownership.template.md lines=1-13 ref=341f235ccb425acd0fd60bbefd26dbe942384119 region_sha256=65ae6a90737fa390e94afac73c04a7636e9d789fe3bf4439482989fcf342eb08 -->
```
# Ownership

Ownership maps files and subsystems to the agent role that should lead changes.

## Path Ownership

| Path pattern | Owner role | Coordination required when |
|---|---|---|
| `{{FRONTEND_PATH_PATTERN}}` | `{{FRONTEND_ROLE_OR_IMPLEMENTER}}` | API contracts, shared types, auth, routing, e2e flows change |
| `{{BACKEND_PATH_PATTERN}}` | `{{BACKEND_ROLE_OR_IMPLEMENTER}}` | Public API, schema, auth, infra, queues, background jobs change |
| `{{SHARED_PATH_PATTERN}}` | `{{SHARED_CONTRACT_ROLE_OR_IMPLEMENTER}}` | Any consumer in another app/package is affected |
| `{{DOCS_PATH_PATTERN}}` | `{{REVIEWER_OR_IMPLEMENTER}}` | Docs describe public behavior, API, schema, or deployment |
| `{{TEST_PATH_PATTERN}}` | `{{REVIEWER_OR_IMPLEMENTER}}` | Tests encode cross-subsystem behavior |
```
<!-- /current-code -->

The existing shell wrapper pattern this stage borrows for
`agent-lock.sh run` is the EXIT trap in `agent-eval.template.sh`:

<!-- current-code path=scripts/agent-eval.template.sh lines=42-42 ref=341f235ccb425acd0fd60bbefd26dbe942384119 region_sha256=b4bdc848109722a383d0a972c6eb859f2abd29565b8c4cc7199e7c9eb708f1b7 -->
```bash
  fi
```
<!-- /current-code -->

## Affected Areas

- New file `scripts/lib/agent_lock.py` (library + argparse-based CLI
  exposing `acquire`, `release`, `list`, `prune`, `check-overlap`).
- New file `scripts/lib/test_agent_lock.py` (unit tests + threading
  smoke).
- New file `scripts/agent-lock.sh` (wraps the Python CLI; adds a `run`
  subcommand with `trap EXIT INT TERM HUP` cleanup).
- `.gitignore` (anchored patch adds `.agent/locks/`).
- `scripts/lib/bootstrap/copy_scripts.sh` (two new `copy_file` lines
  for `agent_lock.py` and `agent-lock.sh`).
- `core/workflows/feature-workflow.md` and
  `core/workflows/bugfix-workflow.md` (advisory note about the new
  wrapper).
- `core/README.md` (new "Multi-Agent Coordination (Optional)"
  subsection pointing at the wrapper).
- `core/migrations/<next-version>/migration.json` (delivers
  `agent_lock.py`, `agent-lock.sh`, the updated workflow docs, and
  the `.gitignore` patch to existing generated repos).

All affected areas live inside the local agent-system tree; this stage
does not touch any runtime boundary other than the wrapper and the
Python helper that lives next to it.

## Implementation Plan

- Add `scripts/lib/agent_lock.py` with:
  - An `AgentLockManager` class exposing `acquire(paths, *, task, ttl_minutes, root) -> str`,
    `release(session_id, *, root) -> bool`,
    `list_locks(root, *, include_expired=False) -> list[dict]`,
    `prune(root, *, stale_minutes=None) -> list[str]`, and
    `check_overlap(paths, *, root) -> list[str]`.
  - A module-level `_paths_overlap(paths_a, paths_b) -> bool` helper
    using bidirectional `fnmatch.fnmatch` plus a common-prefix check
    on the substring before the first `*`.
  - A `main(argv)` function wired through `argparse` with subcommands
    `acquire`, `release`, `list`, `prune`, `check-overlap`. `acquire`
    accepts `--paths` (comma-separated globs), `--task`, `--ttl-minutes`,
    `--root`; it prints the new session UUID on stdout and exits `0`.
    `release` requires `--session-id` and `--root`; it exits `0` when
    the lock existed and was removed, `1` otherwise.
  - Lock file shape:
    `{"v": 1, "session_id": <uuid4>, "paths": [...], "acquired_at": "<utc-iso8601>", "ttl_minutes": <int>, "task": "<str>", "pid": <int>}`,
    written via `os.open(..., O_WRONLY|O_CREAT|O_EXCL, 0o644)` exactly
    as `acquire_lock` already does in
    `scripts/lib/agent_sync/preflight.py`.
- Add `scripts/lib/test_agent_lock.py` covering: acquire on an empty
  lock directory succeeds, acquire while an overlapping non-expired
  lock exists raises `LockConflictError`, release removes the lock
  and returns `True`, release of an unknown session id returns `False`,
  expired locks are ignored during overlap detection, `prune` removes
  expired locks and preserves active ones, the threading test launches
  N concurrent acquires for the same glob and asserts exactly one
  succeeds, and the CLI subcommands exit with the documented codes.
- Add `scripts/agent-lock.sh` exposing `run`, `acquire`, `release`,
  `list`, `prune` subcommands. The `run` subcommand acquires a lock,
  then sets `rc=0` **before** installing the trap so the variable is
  always defined when any signal path fires. The trap is shaped as:
  ```bash
  rc=0
  cleanup() {
    trap - EXIT INT TERM HUP   # disarm so cleanup runs at most once
    release_via_python "$session_id" || true
    exit "$rc"
  }
  trap cleanup EXIT INT TERM HUP

  "${cmd[@]}"
  rc=$?
  ```
  The wrapped command's exit code is captured into `rc` immediately
  after the call returns, and the trap's `exit "$rc"` preserves it on
  normal EXIT. On signal paths (INT, TERM, HUP) the shell aborts the
  wrapped command, the trap fires with `rc` still at its last assigned
  value (or `0` if the wrapped command never returned), runs
  `release_via_python`, and exits with that `rc`. The `acquire` and
  `release` subcommands are exposed unchanged for long-running
  sessions whose caller manages their own trap.
- Edit `.gitignore` via an anchored insert so the new `.agent/locks/`
  entry is appended exactly once, idempotently. The migration uses a
  `patches` entry with an anchor like
  `^\*\.pyc$` and a `skip_if_contains` rule
  matching the new line so re-running the migration is safe.
- Add `scripts/lib/agent_lock.py` and `scripts/agent-lock.sh` to the
  `copy_scripts()` function in `scripts/lib/bootstrap/copy_scripts.sh`
  so new bootstraps receive both files.
- Add a short advisory section to `core/workflows/feature-workflow.md`
  and `core/workflows/bugfix-workflow.md` describing when to wrap a
  multi-agent task with `scripts/agent-lock.sh run`. Add a new
  "Multi-Agent Coordination (Optional)" section to `core/README.md`
  pointing at the wrapper. None of these docs make the wrapper
  mandatory.
- Author a new migration directory `core/migrations/<next-version>/`
  whose `migration.json` lists, under `safe_overwrite`:
  `scripts/lib/agent_lock.py`,
  `scripts/agent-lock.sh`,
  `core/workflows/feature-workflow.md`, and
  `core/workflows/bugfix-workflow.md`; and under `patches`: an
  anchored `.gitignore` insert that adds `.agent/locks/`. It sets
  `"update_tracked_files": true`.

## Decision Ledger

| Decision | Chosen Behavior | Rationale | Alternatives Rejected | Caller/User Impact | Verification |
|----------|-----------------|-----------|------------------------|--------------------|--------------|
| `lock-ttl-minutes` (numeric TTL_MINUTES limit) | Default `TTL_MINUTES_LIMIT = 60`, configurable per-acquire via `--ttl-minutes`. The lock's `acquired_at` plus `ttl_minutes` defines the expiry boundary; entries past the boundary are ignored during overlap checks and may be removed by `prune`. | A bounded expiry prevents stale locks from killed processes accumulating indefinitely; 60 is long enough that ordinary single-task sessions never have to extend, short enough that crash-stale locks clear within an hour | No TTL (manual cleanup required, locks accumulate); 5-minute TTL (forces long tasks to refresh constantly, regresses against advisory-only intent) | Caller sees a one-line warning when a prune sweeps an expired lock; otherwise the TTL is invisible | Unit test creates an artificially old lock (mutate `acquired_at` to past minus 2 hours), asserts overlap check ignores it, asserts `prune` removes it; second test asserts a fresh lock is preserved by `prune` |
| `lock-acquire-on-overlap-fallback` (fallback when acquire fails) | If `_paths_overlap` returns `True` against any non-expired lock in `.agent/locks/`, the acquire returns `LockConflictError` immediately without touching the filesystem; the CLI surfaces this as exit `1` and prints the conflicting `session_id` and `task` to stderr. No fallback to a non-overlapping subset and no implicit wait. | Advisory locks are most useful when conflicts are loud; silently degrading to a partial acquire would mask the real overlap. The error message names the conflicting session so the operator can decide whether to wait, release, or `prune` | Implicit wait with backoff (multi-agent caller likely wants to fail fast and re-plan); fallback to acquire only the non-overlapping subset (caller's mental model breaks; partial protection feels like total protection) | Caller sees `exit 1` plus a stderr line identifying the conflicting session; the wrapper's `run` subcommand propagates the same exit code | Unit test acquires lock A, asserts a second acquire that overlaps returns `LockConflictError`, and asserts the CLI prints the conflicting session id |
| `lock-cleanup-harness` (test harness for crash and signal paths) | Unit tests mock `os.getpid()` and `time.time()` to drive expiry edges; the trap-cleanup case is covered by a shell smoke that runs `scripts/agent-lock.sh run -- bash -c 'kill -INT $$'` inside a temp directory and asserts the lock directory is empty afterwards. | Stdlib-only test surface; the shell smoke mirrors the real signal path without needing real subprocess group manipulation in Python | `subprocess.Popen` + `os.killpg` style stubs (more code; no closer to the real exit-trap path); pure-Python signal simulation (does not exercise the actual `trap` in `agent-lock.sh`) | Caller-visible behavior is unchanged; only the test harness setup is new | Mock-based unit tests for time / pid edges plus the shell smoke in the per-migration suite |

## Acceptance Criteria

| ID | Criterion | Verification Method |
|----|-----------|---------------------|
| AC-1 | `python3 scripts/lib/agent_lock.py acquire --paths 'src/auth/**' --task t --ttl-minutes 60 --root .` creates exactly one file under `.agent/locks/<uuid>.lock.json`, prints `<uuid>` to stdout, and exits `0` | AUTOMATED-UNIT |
| AC-2 | A second `acquire` against any path that overlaps an existing non-expired lock exits `1` with `LockConflictError` and prints the conflicting session id to stderr; the second lock file is **not** created | AUTOMATED-UNIT |
| AC-3 | `release --session-id <uuid> --root .` removes the lock file and exits `0` for a known session, exits `1` for an unknown session, and never deletes a file outside `.agent/locks/` | AUTOMATED-UNIT |
| AC-4 | `list --root . [--json]` enumerates active locks and never includes expired entries unless `--include-expired` is passed; `--json` output is valid JSON with one object per active lock | AUTOMATED-UNIT |
| AC-5 | `prune --root . --stale-minutes 60` removes lock files whose `acquired_at + ttl_minutes` is older than now and preserves all others | AUTOMATED-UNIT |
| AC-6 | `bash scripts/agent-lock.sh run --paths 'src/test/**' --task t -- echo done` exits `0`, prints `done` to stdout, and leaves `.agent/locks/` empty when the wrapped command completes normally | AUTOMATED-INTEGRATION |
| AC-7 | `bash scripts/agent-lock.sh run --paths 'src/test/**' -- bash -c 'kill -INT $$'` exits with a non-zero code matching the wrapped command and still leaves `.agent/locks/` empty (trap cleanup ran on signal) | AUTOMATED-INTEGRATION |
| AC-8 | `.gitignore` contains the line `.agent/locks/` after the migration applies, and a second migration apply is a no-op | AUTOMATED-INTEGRATION |
| AC-9 | The new migration's `safe_overwrite` list contains `scripts/lib/agent_lock.py`, `scripts/agent-lock.sh`, `core/workflows/feature-workflow.md`, and `core/workflows/bugfix-workflow.md`; its `patches` list contains the anchored `.gitignore` insert; its `manifest_updates.update_tracked_files` is `true` | AUTOMATED-UNIT |

## Existing Behaviors Preserved

- The `agent-sync` preflight lock continues to use `.agent/.sync.lock` with the same `O_CREAT|O_EXCL` pattern; the new advisory locks live under `.agent/locks/` and never collide with the sync lock path (current-code `scripts/lib/agent_sync/preflight.py:43-62`, lines=43-62).
- Ownership documentation stays advisory: `core/ownership.template.md` keeps its existing path-to-role mapping and is not consulted by the new wrapper (current-code `core/ownership.template.md:1-13`, lines=1-13).
- The `agent-eval.sh` EXIT trap stays at one line and is untouched; the new wrapper installs its own trap inside `scripts/agent-lock.sh` only (current-code `scripts/agent-eval.template.sh:42`, lines=42-42).
- The current `.gitignore` retains its `__pycache__/` and `*.pyc` lines; the migration appends `.agent/locks/` via an anchored, idempotent patch (current-code `.gitignore:1-2`, lines=1-2).

## Test Delta

| Test | Action | Why |
|------|--------|-----|
| `scripts/lib/test_agent_lock.py` | ADD | New unit-test module covering acquire, release, list, prune, overlap detection (bidirectional `fnmatch` + common-prefix), TTL expiry edges, threading smoke for atomic acquire, and CLI exit codes |
| `tests/lib/test_agent_lock_shell.sh` | ADD | New shell smoke that exercises `scripts/agent-lock.sh run` for the normal-exit, signal-exit, and overlap-exit paths and asserts `.agent/locks/` is empty after each |
| `tests/migrations/<next-version>/run.sh` | ADD | Per-migration smoke that applies the new migration to a fixture repo, asserts both new files exist, asserts `.gitignore` contains `.agent/locks/`, and asserts a re-apply is a no-op |
| `tests/lib/test_validate_agent_system.py` | KEEP | The existing validator suite must keep passing untouched; this stage does not add new entries to the validator's required-file lists |

## Risks

- False overlap detection on broad globs: the bidirectional `fnmatch` plus common-prefix heuristic is intentionally over-protective. Mitigation: ship the heuristic with unit tests covering the four canonical pairings (containment, equal pattern, sibling, unrelated) and document the trade-off in the workflow notes so operators know to scope their `--paths` arguments narrowly when they want concurrent work.
- Stale locks after `kill -9` (the trap never runs). Mitigation: the TTL-minutes guard makes any such lock expire within an hour by default, and `scripts/agent-lock.sh prune` is callable at any time to remove expired entries; tests assert the TTL boundary and the `prune` behavior.
- Migration conflict on the workflow markdown files for repos that customized them. Mitigation: rely on the existing `safe_overwrite` 3-way conflict detection so the migration refuses to overwrite a customized file silently; the operator must resolve the conflict and re-run `agent-sync`.
- Path normalization differences between Windows and POSIX. Mitigation: the helper normalizes input globs to POSIX form via `PurePosixPath` before storing and comparing, and the unit tests include a Windows-style input (`src\\auth\\login.ts`) that must be normalized identically to its POSIX form.

## Verification

Run from the repo root:

```bash
python3 -m unittest scripts.lib.test_agent_lock
bash -n scripts/agent-lock.sh
bash tests/lib/test_agent_lock_shell.sh
bash scripts/agent-validate.sh --mode template
bash scripts/agent-evals.sh --fast
for f in tests/migrations/*/run.sh; do bash "$f"; done
```

The first command exercises every unit assertion. The second
type-checks the wrapper shell. The third drives the wrapper through
its normal, signalled, and conflicting code paths. The fourth confirms
template-mode validation still passes after the new files and
docs land. The fifth runs the existing fast gate suite. The sixth
re-runs every migration smoke including the new one introduced by
this stage.

## Open Questions

- Q: Should `scripts/agent-lock.sh run` integrate with the
  `agent-eval.sh` audit log so lock acquisitions emit a `subagent_run`
  or new `agent_lock` event kind?
  - DEFERRED: out of scope for the MVP. The proposal lists "Lock
    contention metrics in audit log" under Future Work. Revisit once
    advisory adoption is real.
- Q: Should the wrapper enforce locks (block on conflict) rather than
  fail fast?
  - RESOLVED: no. The Decision Ledger row `lock-acquire-on-overlap-fallback`
    codifies fail-fast on conflict. Enforcement requires workflow
    integration that the parent proposal explicitly defers.
- Q: What is the exact `<next-version>` slug for the migration
  directory?
  - DEFERRED: chosen at merge time by `scripts/release-prepare.sh`; the
    plan uses `<next-version>` as a placeholder.
