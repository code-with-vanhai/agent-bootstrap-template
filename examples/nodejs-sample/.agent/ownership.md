# Ownership

| Path pattern | Owner role | Coordination required when |
|---|---|---|
| `src/**` | `implementer` | API behavior, auth, validation, or public contracts change |
| `tests/**` | `implementer` | Tests define cross-module behavior |
| `scripts/**` | `gate-runner` | Verification or deploy behavior changes |
| `.agent/**` | `planner` | Rules, gates, roles, or workflows change |
| `README.md` | `reviewer` | Public usage instructions change |

## Cross-Boundary Protocol

If a change touches implementation and gates, state the affected paths and run at least `scripts/agent-eval.sh fast`.

## High-Risk Areas

- `package.json` deploy scripts.
- Future auth, token, or secret handling code.

