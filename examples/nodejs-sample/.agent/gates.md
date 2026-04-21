# Verification Gates

Use `scripts/agent-eval.sh`.

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
| `fast` | Most code changes | `scripts/agent-eval.sh fast` |
| `backend` | API/backend behavior changed | `scripts/agent-eval.sh backend` |
| `full` | Broad changes before merge | `scripts/agent-eval.sh full` |
| `frontend` | Frontend changed | `not configured: no frontend found` |
| `e2e` | User-flow tests needed | `not configured: no e2e framework found` |
| `release` | Release candidate verification | `not configured: deploy requires manual approval` |

## Configured Commands

Evidence source: `package.json`.

### `fast`

```bash
npm run typecheck
npm test
npm run lint
```

### `backend`

```bash
npm run typecheck
npm test
npm run lint
npm run build
```

### `full`

```bash
npm run typecheck
npm test
npm run lint
npm run build
```

## Acceptance Criteria

- Gate name and commands are reported.
- Failures include actionable excerpts.
- Not-configured gates are explicitly listed.
