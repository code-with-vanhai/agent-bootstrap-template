# Migration: 0.7.0 -> 0.8.0

## Source Acceptance

This migration accepts only `0.7.0` as a source version.

Repos on earlier versions must sync one release at a time.

## What This Migration Ships

0.8.0 updates downstream generated repos with:

- structured `scripts/agent-validate.sh` wrapper plus `scripts/lib/validate_agent_system.py`;
- evidence-backed candidate gate discovery;
- modular `scripts/lib/plan_validation/` package with a compatibility `validate_plan.py` wrapper;
- updated gate/rulebase text for secret scanning and gate suggestions;
- updated `scripts/agent-eval.sh security` scanner path.

Every `scripts/lib/plan_validation/*` file is listed individually in
`safe_overwrite`; this migration does not add directory overwrite semantics.

## Verification

`tests/migrations/0.8.0/run.sh` builds a clean 0.7.0 fixture, applies 0.8.0,
asserts the new files and manifest values, runs the generated validator through
`AGENT_ROOT`, and checks idempotent re-apply behavior.
