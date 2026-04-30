# Spec: Add JSON output for plan validator (P1-5)

**Status:** Verified with evidence: agent-validate.sh @ 2026-04-30T07:29:00Z (exit=0)
**Date:** 2026-04-30
**Ref commit:** `d22e029`
**Plan location note:** Stored under `docs/plans/bootstrap-090/p1-5-plan-validator-json-format/` because this template repo dogfoods plans there. Generated target repos should use `.agent/runs/<date>-<slug>/`.
**Track:** 0.9.0 P1-5, after P1-4 audit-log and P1-3 data-safety landed.

## Problem

`scripts/lib/plan_validation/cli.py` currently supports only `--format human|github`. This is enough for local reading and GitHub annotations, but not enough for machine consumers that need structured fields (`check_id`, severity, file, line, message, strict, counts) without parsing text lines. We now have append-only audit events (P1-4), but `plan_validation` payload quality still depends on parsing human summary lines in `scripts/agent-validate-plan.sh`. That is fragile and format-specific.

P1-5 adds a first-class JSON output contract for the plan validator while preserving the existing human/github contracts and exit semantics.

## Goals

- Extend `scripts/lib/plan_validation/cli.py` to accept `--format json` in addition to `human|github`.
- Add a stable JSON payload that includes:
  - top-level execution metadata (`target`, `repo_root`, `strict`, `format`, `high_count`, `medium_count`, `failure_count`, optional repo signals),
  - ordered findings with fields already present in `Finding` (`check_id`, `severity`, `message`, `file`, `line`),
  - per-file grouping parity with current human output (`plan.md`, `spec.md`) so downstream tools can map findings to artifacts deterministically.
- Preserve existing output contracts:
  - `--format human` output remains byte-compatible enough for current wrappers/tests (`Summary: <h> High, <m> Medium ...` still present).
  - `--format github` output remains GitHub annotation lines (no summary footer).
- Preserve exit code behavior exactly:
  - `0` when `filter_for_exit(all_findings, strict)` is empty,
  - `1` when non-empty,
  - `2` for usage/target errors.
- Keep `scripts/agent-validate-plan.sh` behavior for human/github unchanged in this phase. JSON support is additive; wrapper logging in P1-4 must not regress.

## Non-Goals

- No schema negotiation/versioning in this phase; JSON shape is introduced as v1 implicit contract in docs/tests.
- No change to validation rules, findings classification, or check IDs.
- No change to `scripts/agent-audit-log.sh` payload schema in P1-5; wrapper improvements can be follow-up work.
- No new gate mode, no harness changes, no migration logic.
- No changes to existing markdown plan/spec grammar.

## JSON Contract (proposed)

Output for `--format json` is one JSON object to stdout:

```json
{
  "format": "json",
  "strict": true,
  "target": "/abs/path/to/.agent/runs/x",
  "repo_root": "/abs/path/to/repo",
  "high_count": 1,
  "medium_count": 2,
  "failure_count": 3,
  "detected_signals": ["package.json: react@19.0.0"],
  "react_version": "19.0.0",
  "files": [
    {
      "path": "/abs/path/to/.agent/runs/x/plan.md",
      "findings": [
        {
          "check_id": "SECT-001",
          "severity": "High",
          "message": "plan is missing required sections: ...",
          "file": "/abs/path/to/.agent/runs/x/plan.md",
          "line": 1
        }
      ]
    },
    {
      "path": "/abs/path/to/.agent/runs/x/spec.md",
      "findings": []
    }
  ],
  "findings": [
    {
      "check_id": "SECT-001",
      "severity": "High",
      "message": "plan is missing required sections: ...",
      "file": "/abs/path/to/.agent/runs/x/plan.md",
      "line": 1
    }
  ]
}
```

Notes:
- `findings` is the flattened ordered list (execution order, same as current rendering pass).
- `files[*].findings` are grouped views to avoid downstream regroup logic.
- When no findings exist, counts are zero and `findings` is an empty list.

## Failure-mode Contract

- JSON serialization failure is treated as validator runtime error: print concise error to stderr and return `2`.
- `--format json` must still honor `--force`, `--repo-root`, strict mode, and template-version skip behavior.
- If no plan/spec files found, behavior stays unchanged: stderr message + exit `2` for all formats.
- `file`/`line` fields remain nullable when missing from a finding.

## Validation Expectations

- Add/extend unit tests in `scripts/lib/test_validate_plan.py`:
  - new test for `--format json` payload structure + field presence + deterministic counts,
  - exit code parity tests for strict and non-strict under json format,
  - regression test that `--format human` still emits `Summary: ...`,
  - regression test that `--format github` still emits `::error` / `::warning` lines.
- `scripts/agent-validate.sh` passes.
- Full unittest gate passes.
- `scripts/agent-evals.sh --fast` passes.
- Strict plan validation passes on this P1-5 plan folder.
