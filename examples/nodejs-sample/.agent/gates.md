# Verification Gates

Use `scripts/agent-eval.sh`.

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

