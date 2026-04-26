# Plan: Fictional line range fixture (bad)

**Status:** Proposed

## Goal

The plan cites lines 821-821 of `src/app.ts`, which does not exist (the file
is only a few lines). Reviewers using the grounding pass must flag this as a
P0 defect (EV-002 / EV-003).

<!-- current-code path=src/app.ts lines=821-821 ref=HEAD region_sha256=0000000000000000000000000000000000000000000000000000000000000000 -->
```ts
<main className="flex-1 h-full min-h-0 p-4 overflow-y-auto">
```
<!-- /current-code -->

## Acceptance Criteria

| # | Criterion | Verification Method |
|---|---|---|
| 1 | scroll container behaves correctly | `MANUAL` |

## Existing Behaviors Preserved

- (claimed but unverifiable because the citation is fictional)

## Verification

```bash
npm test
```
