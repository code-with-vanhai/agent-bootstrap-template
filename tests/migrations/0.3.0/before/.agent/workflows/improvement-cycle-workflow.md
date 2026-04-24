# Improvement Cycle Workflow

Use this workflow for repeated, metric-driven improvement of an existing subsystem.

This is the production-software adaptation of the candidate/champion loop used in repository-scale agent evolution. It is not fully autonomous by default; a human may approve goals, rule changes, and high-risk edits.

## When To Use

- Performance optimization.
- Reliability hardening.
- Developer experience improvement.
- Test coverage improvement.
- Bundle/runtime/query-size reduction.
- Search, ranking, AI, scheduling, or other heuristic tuning.

## Inputs

- Target subsystem.
- Primary metric.
- Auxiliary metrics.
- Baseline measurement.
- Allowed edit scope.
- Relevant gate.

## Steps

1. Define the champion baseline:
   - current commit or working tree state
   - current primary metric
   - current relevant gate result
2. Define candidate constraints:
   - allowed paths
   - forbidden paths
   - max dependency change
   - max public contract change
3. Implement one candidate change.
4. Run correctness gates before metric evaluation.
5. Measure primary and auxiliary metrics.
6. Accept, reject, or revise:
   - Accept if primary metric improves and correctness is preserved.
   - Reject if correctness, security, data safety, or public contracts regress.
   - Revise if auxiliary metrics reveal likely synergy but primary proof is incomplete.
7. Record durable findings in `lessons.md` only if they guide future work.

## Metric Template

```md
Champion:
- Baseline reference:
- Primary metric:
- Auxiliary metrics:
- Gate:

Candidate:
- Hypothesis:
- Changed paths:
- Primary metric result:
- Auxiliary metric result:
- Gate result:
- Decision: accept | reject | revise
- Reason:
```

## Rules

- Correctness gates come before performance or quality claims.
- Do not optimize a benchmark by weakening real behavior.
- Do not keep a candidate that violates `rulebase.md`, even if a metric improves.
- If a candidate requires rule relaxation, use `rule-evolution-workflow.md`.

