# Verification Gates

Use `scripts/agent-eval.sh <mode>` as the entrypoint for verification.

Do not invent missing gates. If a command is not configured in this repo, mark it as `not configured` and explain the residual risk.

## Verification Discipline

```text
NO COMPLETION CLAIMS WITHOUT FRESH VERIFICATION EVIDENCE
NO INVENTED GATES OR COMMANDS
```

Before reporting that work is complete, fixed, passing, or ready:

1. Identify the narrowest gate that proves the claim.
2. Run the gate or explain why it is blocked or not configured.
3. Read the full command output and exit status.
4. Report the command, result, relevant failure excerpts, skipped checks, and residual risk.

Do not use a previous run, another agent's summary, package-manager convention, or manual inspection as a substitute for fresh gate evidence.

## Gate Rationalization Checks

| Excuse | Reality |
|---|---|
| "This repo probably has the standard command." | Only configure commands found in checked-in build, package, task, or CI files. |
| "The gate is missing, so I will use a likely equivalent." | Mark it `not configured` unless the equivalent is documented in the repo. |
| "The command failed for unrelated reasons, so the change is done." | Report the failure, assess whether the patch caused it, and state residual risk. |
| "I ran part of the gate." | Partial verification must be reported as partial. |
| "It passed earlier in the session." | Completion claims require fresh evidence from the current task state. |

## Gate Selection

| Gate | Use when | Command |
|---|---|---|
| `changed` | The repo supports changed-file focused checks | `scripts/agent-eval.sh changed` |
| `fast` | Most code changes | `scripts/agent-eval.sh fast` |
| `frontend` | Frontend/UI/routes/client state changed | `scripts/agent-eval.sh frontend` |
| `backend` | API/server/jobs/database integration changed | `scripts/agent-eval.sh backend` |
| `shared` | Shared types/contracts/libraries changed | `scripts/agent-eval.sh shared` |
| `e2e` | User flows, auth, routing, or critical workflows changed | `scripts/agent-eval.sh e2e` |
| `full` | Before merge/release or broad refactors | `scripts/agent-eval.sh full` |
| `security` | Auth, authorization, secrets, data exposure, or trust boundaries changed | `scripts/agent-eval.sh security` |
| `release` | Release candidate verification | `scripts/agent-eval.sh release` |

Gate names are a stable convention. Do not add a new mode unless `scripts/agent-eval.sh`, this file, and any command prompt that routes to gates are updated together.

## Configured Commands

Replace these with repo-specific commands after scanning.

### `changed`

Status: `{{CONFIGURED_OR_NOT_CONFIGURED}}`

```bash
{{CHANGED_GATE_COMMANDS}}
```

### `fast`

Status: `{{CONFIGURED_OR_NOT_CONFIGURED}}`

```bash
{{FAST_GATE_COMMANDS}}
```

### `frontend`

Status: `{{CONFIGURED_OR_NOT_CONFIGURED}}`

```bash
{{FRONTEND_GATE_COMMANDS}}
```

### `backend`

Status: `{{CONFIGURED_OR_NOT_CONFIGURED}}`

```bash
{{BACKEND_GATE_COMMANDS}}
```

### `shared`

Status: `{{CONFIGURED_OR_NOT_CONFIGURED}}`

```bash
{{SHARED_GATE_COMMANDS}}
```

### `e2e`

Status: `{{CONFIGURED_OR_NOT_CONFIGURED}}`

```bash
{{E2E_GATE_COMMANDS}}
```

### `full`

Status: `{{CONFIGURED_OR_NOT_CONFIGURED}}`

```bash
{{FULL_GATE_COMMANDS}}
```

### `security`

Status: `{{CONFIGURED_OR_NOT_CONFIGURED}}`

```bash
{{SECURITY_GATE_COMMANDS}}
```

### `release`

Status: `{{CONFIGURED_OR_NOT_CONFIGURED}}`

```bash
{{RELEASE_GATE_COMMANDS}}
```

## AC Verification Taxonomy

Every acceptance criterion in `.agent/runs/*/plan.md` must declare a Verification Method drawn from this enum. The validator at `scripts/agent-validate-plan.sh` (when available) enforces these classifications.

| Method | Definition |
|---|---|
| `AUTOMATED-UNIT` | Vitest, Jest, or equivalent unit harness. Deterministic. No real layout. |
| `AUTOMATED-INTEGRATION` | Real browser or Node integration (Playwright, Puppeteer, Testcontainers, etc.). |
| `AUTOMATED-E2E` | Full user-flow E2E. |
| `BUILD-OUTPUT` | File, size, manifest, or other artifact assertion against a build output. |
| `TYPECHECK` | `tsc --noEmit` or equivalent type checker run. |
| `MANUAL` | Human verification with documented residual risk. |

**jsdom layout rule.** If acceptance behavior depends on real layout APIs (`clientHeight`, `getBoundingClientRect`, `scrollTop`, `IntersectionObserver`, computed CSS), it MUST NOT be classified as `AUTOMATED-UNIT` in a jsdom environment. Promote to `AUTOMATED-INTEGRATION`, `AUTOMATED-E2E`, or `MANUAL` with documented residual risk.

## Plan Discipline Command

`scripts/agent-validate-plan.sh` is a plan discipline command, not a gate mode. It validates evidence blocks, banned self-claim patterns, required sections, decision-lock checks, and AC verification classifications in `.agent/runs/*/plan.md`. It does not replace `scripts/agent-eval.sh <mode>` and is not added to the gate enum.

## Acceptance Criteria

A gate result must include:

- Gate name.
- Commands run.
- Pass/fail status.
- Relevant failure excerpts.
- Any skipped command and reason.
- Residual risk if a required gate cannot be run.

## Metric Rules

Primary metrics are correctness gates: tests, typecheck, build, contract validation, migration validation, and critical user flows.

Auxiliary metrics may include coverage, bundle size, lint count, runtime, query count, logs, and performance budgets.

Do not trade away primary correctness to improve auxiliary metrics.
