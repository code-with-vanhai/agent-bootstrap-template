# Feature Workflow

Use this workflow for new user-visible or system behavior.

## Steps

1. Planner defines goal, affected areas, owner, acceptance criteria, and gates.
2. Implementer inspects existing patterns and nearby tests.
3. Implementer makes a scoped patch.
4. Implementer updates tests and docs for changed behavior.
5. Gate Runner runs the selected gate.
6. Reviewer checks the diff if the change affects public contracts, data, auth, infra, or broad UI flows.
7. Record durable lessons or decisions only when needed.

## Multi-Agent Coordination

When more than one agent may edit overlapping paths in the same working tree,
wrap the task command with `scripts/agent-lock.sh run --paths '<glob>' --task '<summary>' -- <command>`.
The lock is advisory and fail-fast; use narrow path globs so unrelated work can
proceed concurrently.

## Grounding Requirements

The planner re-reads every file it cites in the same planning turn. Stale session memory is not acceptable.

Every "BEFORE" / "Existing" / "Current code" quote in `spec.md` or `plan.md` MUST use this evidence block grammar:

````md
<!-- current-code path=<repo-relative-posix> lines=A-B ref=<short-sha> region_sha256=<full-hex> -->
```<lang>
<exact snippet>
```
<!-- /current-code -->
````

Rules:

- `path`: repo-root-relative POSIX. No `..`, no absolute paths.
- `lines`: `A-B`, 1-indexed inclusive. Single line uses `A-A`.
- `ref`: git short SHA (≥ 7 chars) of the commit when the planner read the file.
- `region_sha256`: SHA-256 of the entire whitespace-normalized snippet (collapse runs of whitespace, strip trailing). The validator hashes full content; tampering after N characters is still detected.
- The validator parses by HTML comment boundaries, not by markdown fence, so snippets may contain triple-backticks.
- Inner fence language is free-form (`tsx`, `ts`, `py`, `text`, ...) for GitHub rendering.

If the snippet expected at the cited region is not present at the working tree, the planner stops and revises the plan goal. Do not fabricate a "BEFORE" snippet that fits the proposed AFTER.

The non-trivial plan must contain four sections enforced by `scripts/agent-validate-plan.sh` (when available):

- `Implementation Plan` — concrete implementation steps. Do not leave behavior-affecting choices as `consider`, `maybe`, `could`, `or add`, or similar hedges; make the decision explicit, or move the question to `Open Questions` with a resolution.
- `Acceptance Criteria` — every row classified with a Verification Method (`AUTOMATED-UNIT`, `AUTOMATED-INTEGRATION`, `AUTOMATED-E2E`, `BUILD-OUTPUT`, `TYPECHECK`, or `MANUAL`). Layout-dependent behavior cannot be `AUTOMATED-UNIT` in jsdom.
- `Existing Behaviors Preserved` — for each modified function, current side effects with evidence-block citations and classification (`PRESERVED`, `INTENTIONALLY REMOVED`, `BUG FIX`).
- `Verification` — gate name and command(s).

`Open Questions` is optional. If present, each question must use this exact shape:

```md
- Q: <question>
  - RESOLVED: <binding decision>
```

or:

```md
- Q: <question>
  - DEFERRED: <why this is out of scope for this plan>
```

For `Status: Proposed` plans, unresolved open questions are rejected. For `Status: Draft`, unresolved open questions are warnings.

When the plan adds or changes an enum, status, error code, message literal, or similar contract value, include a `Contract Value Table` section before implementation:

| Literal | Producer | Consumer | User-facing behavior | Test |
|---|---|---|---|---|
| `EXAMPLE_CODE` | `path/to/producer.ts` | `path/to/consumer.ts` | Existing or intended visible behavior | `path/to/test.ts` |

`Contract Value Table` is only for added or behavior-changed contract values. Do not list unchanged existing literals just to satisfy validation; unchanged invariants belong in `Existing Behaviors Preserved` or `Decision Ledger`.

When the plan includes fallback/empty/null/degraded behavior, thresholds/timeouts/debounce/limits/`MAX_*` constants, matchers/classifiers/parsers/blocklists/allowlists, or test harness choices such as mocks/stubs/fake timers/`MutationObserver`/`defineContentScript`, include a `Decision Ledger` section:

| Decision | Chosen Behavior | Rationale | Alternatives Rejected | Caller/User Impact | Verification |
|---|---|---|---|---|---|
| DOM-size guard threshold | Use `MAX_DOM_NODES = 15000` before cloning | Prevents heavy-page allocations | Clone then catch OOM-like failure | On-demand clipping gets existing empty-content path | `page-extractor-size-guard.test.ts` |

Use `Decision Ledger` to bind semantic choices. The implementer should not infer node-count method, hostname matching, fallback UX, or fake-timer/test-harness setup from vague prose.

When the plan touches a boundary with separate lifecycles (for example background ↔ side panel, worker ↔ UI, server ↔ client, extension ↔ webpage), include a `Compatibility Matrix` section covering these rows:

| Scenario | Behavior | Test |
|---|---|---|
| old producer + new consumer | Fallback/compat behavior | Gate or test |
| new producer + old consumer | Fallback/compat behavior | Gate or test |
| unknown value | Fallback/compat behavior | Gate or test |
| empty value | Fallback/compat behavior | Gate or test |
| missing field | Fallback/compat behavior | Gate or test |

When the plan adds, updates, or preserves tests, include a `Test Delta` section:

| Test | Action | Why |
|---|---|---|
| `path/to/existing.test.ts` | `KEEP` / `UPDATE` / `ADD` | Behavior or branch covered |

Every non-empty `Risks` bullet must include `Mitigation:` in the same bullet:

```md
- Risk: <risk>. Mitigation: <mitigation>.
```

When adding a new literal to an existing field or contract, cite the current convention with an evidence block. Do not ask the implementer to infer naming or fallback behavior.

Status field whitelist: `Draft`, `Proposed`, or `Verified with evidence: <gate> @ <UTC> (exit=<code>)`. Self-assigned quality scores, ✅ checkmarks, and bare `Ready for ...` stamps are forbidden.

## Acceptance Criteria

- Feature behavior matches the request.
- Public contracts are preserved or updated intentionally.
- Docs and tests reflect the behavior.
- Relevant gates pass or residual risk is explicit.

## Escalate Before Editing When

- The feature requires new infrastructure, external services, or paid APIs.
- The feature changes authentication, authorization, billing, data retention, or privacy behavior.
- The feature needs a new architecture decision.
