# Spec: Multi-hop migration walker (P1-2)

**Status:** Verified with evidence: agent-validate.sh @ 2026-04-30T08:15:34Z (exit=0)
**Date:** 2026-04-30
**Ref commit:** `6b95814`
**Plan location note:** Stored under `docs/plans/bootstrap-090/p1-2-migration-walker/`. Generated target repos should use `.agent/runs/<date>-<slug>/`.
**Track:** 0.9.0 P1-2 — safe multi-hop sync orchestration on top of existing `agent-sync.py` single-hop engine.

## Problem

`scripts/agent-sync.py` only migrates **one** template version per invocation (`current` → `--to`). A repo at `0.4.0` that needs `0.8.1` must run sync repeatedly with monotonically increasing `--to` values. The tool does not compute or execute a version chain, and the design doc still states cross-hop chaining is deferred.

## Goal

Add a **Phase 1 migration walker** that:

1. Builds a **directed migration chain** from the target’s current template version to a requested `--to`, using existing `core/migrations/<version>/migration.json` metadata (schema v1 only).
2. Defaults to **dry-run** semantics that **never modify the user’s target worktree**.
3. With `--apply`, proves the full chain on an **ephemeral writable clone**, then applies **one** atomic-ish batch of resulting file changes to the target (no hop-by-hop writes to the target).
4. Appends **one** coherent `.agent/sync-log.md` entry on successful `--apply` (aggregated multi-hop narrative, not one entry per intermediate hop).
5. Fails with explicit errors when no chain exists or migration metadata does not match `load_migration()` rules.

## Explicitly out of scope (P1-2)

- Rewriting `agent-sync.py` into a new atomic migration engine (reuse planning/apply primitives).
- Migration schema v2, interactive conflict UI, or auto-commit in the target repo.
- Guaranteeing a single POSIX `rename()`-level atomic transaction across all files (acceptable: best-effort batch with existing dirty-worktree + lock behavior).

## Acceptance criteria

| ID | Criterion | Verification Method | Gate |
|:---|:---|:---|:---|
| AC-1 | Plan/spec pass `scripts/agent-validate-plan.sh --force --strict` on this folder | `AUTOMATED-INTEGRATION` | `agent-validate-plan.sh` |
| AC-2 | Default multi-hop invocation prints a per-hop summary and exits `0` without changing tracked content under `--target` | `AUTOMATED-INTEGRATION` | `unittest` or `tests/migrations/*/run.sh` |
| AC-3 | `--apply` multi-hop: if every hop succeeds on the temp clone, target ends at `synced_to_template_version == --to` and matches the proven temp end state for migrated paths | `AUTOMATED-INTEGRATION` | `tests/migrations/multi-hop/run.sh` |
| AC-4 | `--apply` multi-hop: if any hop fails on the temp clone, the target worktree contents are byte-identical pre/post | `AUTOMATED-INTEGRATION` | `tests/migrations/multi-hop/run.sh` |
| AC-5 | Dirty target (without `--allow-dirty`) is rejected before any temp work, matching single-hop policy | `AUTOMATED-UNIT` | `unittest` or shell harness |
| AC-6 | `.agent/sync-log.md` gains at most **one** new section on successful multi-hop `--apply`, summarizing the chain | `AUTOMATED-INTEGRATION` | `tests/migrations/multi-hop/run.sh` |

## Risks & mitigations

| Risk | Mitigation |
|:---|:---|
| Intermediate-hop validation cost hides failures until late in the chain | P1-2 does **not** run `run_validation` against the temp clone; gateway is conflict-free rehearsal + post-apply validation on the real target (when `--verify-fast`), matching the engine that had only single-hop before. |
| Temp simulation diverges from replay on target | Build apply batch from deterministic final temp tree vs. original target snapshot; reject if target changes between dry-run and apply (lock + clean tree). |
| Migration graph ambiguity (multiple shortest paths) | Document deterministic tie-break (e.g., lowest next version) in plan; BFS by semver ordering. |

## Open Questions

- **Q:** Should `--verify-fast` run after every hop on the temp clone, or only after the final hop?
- **RESOLVED:** **Neither on temp.** The temp clone is used only for planning + applying hop writes to advance rehearsal state. `run_validation` runs **once** on the **real target** after the aggregated batch apply, when `--verify-fast` is set — same as single-hop `main()` (one post-apply validation), not a second run on a disposable tree.
