# Migration: 0.6.0 -> 0.7.0

## Source Acceptance

This migration accepts only `0.6.0` as a source version (`from_versions: ["0.6.0"]`).

Repos still on earlier versions must sync one release at a time:

```bash
scripts/agent-sync.sh --target /path/to/repo --to 0.6.0 --apply
scripts/agent-sync.sh --target /path/to/repo --to 0.7.0 --apply
```

`agent-sync.py` is single-step by design. Direct jumps across missing
intermediate migrations fail with `migration metadata mismatch`.

## What This Migration Ships

0.7.0 updates downstream planning discipline for semantic decision closure. It
safe-overwrites clean, template-managed copies of:

- `.agent/commands/plan.md`
- `scripts/lib/validate_plan.py`

It patches these files additively instead of overwriting the whole file,
because downstream repos may carry repo-specific notes:

- `.agent/workflows/feature-workflow.md`
- `.agent/roles/planner.md`
- `.agent/roles/prompts/planner-subagent.md`
- `.agent/workflows/review-workflow.md`

## Behavior

The updated plan validator keeps the 0.6.0 grounding and conditional-table
checks, then adds semantic decision checks:

- `DEC-001` requires a `Decision Ledger` when implementation/AC/risk/test-delta
  text contains fallback, threshold, matcher/classifier, or test-harness
  decision triggers.
- `NUM-001` requires threshold, timeout, debounce, limit, and memory-budget
  decisions to include rationale and verification.
- `FALLBACK-001` requires fallback, empty, null, degraded, and no-content
  behavior to include caller/user impact.
- `HARNESS-001` requires mock, stub, fake-timer, `MutationObserver`, and
  `defineContentScript` test-harness decisions to include setup details and
  verification.
- `CVT-003` flags `Contract Value Table` sections that contain only preserved
  or unchanged literals. Threshold constants no longer trigger CVT by
  themselves; they belong in `Decision Ledger`.

## Idempotency

Re-running `agent-sync.sh --target <repo> --to 0.7.0 --apply` on an
already-synced repo prints `Target already synced to 0.7.0; no-op.` and exits
0 without writing.

## Verification

`tests/migrations/0.7.0/run.sh` builds a genuine 0.6.0 fixture by syncing the
canonical 0.3.0 baseline through 0.4.0, 0.5.0, and 0.6.0 first, then applies
0.7.0 and asserts the updated planner docs, review workflow, validator,
manifest values, sync log, and idempotent re-apply.
