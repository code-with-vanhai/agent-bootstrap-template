# Migration: 0.5.0 -> 0.6.0

## Source Acceptance

This migration accepts only `0.5.0` as a source version (`from_versions: ["0.5.0"]`).

Repos still on 0.3.x or 0.4.0 must sync one release at a time:

```bash
scripts/agent-sync.sh --target /path/to/repo --to 0.4.0 --apply
scripts/agent-sync.sh --target /path/to/repo --to 0.5.0 --apply
scripts/agent-sync.sh --target /path/to/repo --to 0.6.0 --apply
```

`agent-sync.py` is single-step by design. Direct jumps across missing
intermediate migrations fail with `migration metadata mismatch`.

## What This Migration Ships

0.6.0 updates downstream planning discipline files. It safe-overwrites clean,
template-managed copies of:

- `.agent/commands/plan.md`
- `scripts/agent-validate-plan.sh`
- `scripts/lib/validate_plan.py`

It patches these files additively instead of overwriting the whole file,
because existing 0.5.0 targets received their 0.4.0 planning discipline
through additive migration patches and may also carry repo-specific notes:

- `.agent/workflows/feature-workflow.md`
- `.agent/roles/planner.md`
- `.agent/roles/prompts/planner-subagent.md`
- `.agent/gates.md`

## Behavior

The updated plan validator adds decision-completeness checks beyond the 0.5.0
grounding rules:

- `OQ-001` and `IMPL-001` require open questions to be resolved/deferred and
  implementation bullets to avoid behavior-affecting hedges.
- `AC-003` and `AC-004` require literal targets for code/status/enum ACs and
  prevent documentation-only ACs from being verified by `TYPECHECK` alone.
- `CVT-*`, `COMPAT-*`, `TEST-*`, and `RISK-001` require the corresponding
  contract, compatibility, test delta, and risk mitigation details when their
  triggers appear in a plan.

## Idempotency

Re-running `agent-sync.sh --target <repo> --to 0.6.0 --apply` on an
already-synced repo prints `Target already synced to 0.6.0; no-op.` and exits
0 without writing.

## Verification

`tests/migrations/0.6.0/run.sh` builds a genuine 0.5.0 fixture by syncing the
canonical 0.3.0 baseline through 0.4.0 and 0.5.0 first, then applies 0.6.0 and
asserts the updated planner docs, validator checks, manifest values, sync log,
and idempotent re-apply.
