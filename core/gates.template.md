# Verification Gates

Use `scripts/agent-eval.sh` as the entrypoint for verification.

Do not invent missing gates. If a command is not configured in this repo, mark it as `not configured` and explain the residual risk.

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
| `release` | Release candidate verification | `scripts/agent-eval.sh release` |

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

### `release`

Status: `{{CONFIGURED_OR_NOT_CONFIGURED}}`

```bash
{{RELEASE_GATE_COMMANDS}}
```

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

