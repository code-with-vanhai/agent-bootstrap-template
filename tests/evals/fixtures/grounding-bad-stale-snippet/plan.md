# Plan: Stale snippet fixture (bad)

**Status:** Proposed

## Goal

Refactor `helloWorld`. The BEFORE quote below intentionally does not match the
working-tree content of `src/app.ts:2` — reviewers using the grounding pass
must catch this as a P0 defect.

<!-- current-code path=src/app.ts lines=2-2 ref=HEAD region_sha256=0000000000000000000000000000000000000000000000000000000000000000 -->
```ts
  return "DIFFERENT VALUE THAT IS NOT IN THE FILE";
```
<!-- /current-code -->

## Acceptance Criteria

| # | Criterion | Verification Method |
|---|---|---|
| 1 | helloWorld returns "ok-v2" | `AUTOMATED-UNIT` |

## Existing Behaviors Preserved

- `helloWorld` returns the (stale) value above.

## Verification

```bash
npm test
```
