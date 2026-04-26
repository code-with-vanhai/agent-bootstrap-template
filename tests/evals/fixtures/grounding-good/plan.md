# Plan: Grounded fixture (good)

**Status:** Proposed

## Goal

Trivial change to `helloWorld` return value.

<!-- current-code path=src/app.ts lines=2-2 ref=HEAD region_sha256=a65173caddf22495e757774fdb50046fbfe01755c4aed23114124b05e537156f -->
```ts
  return "ok";
```
<!-- /current-code -->

## Acceptance Criteria

| # | Criterion | Verification Method |
|---|---|---|
| 1 | helloWorld returns updated string | `AUTOMATED-UNIT` |

## Existing Behaviors Preserved

- `helloWorld` currently returns `"ok"` at `src/app.ts:2-2` (PRESERVED until AFTER step).

## Verification

```bash
npm test
```
