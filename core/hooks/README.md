# Hook Templates

This directory holds **off by default** hook templates that bootstrap can stage
into a target repository under `.agent/hooks/`. None of these hooks run during
bootstrap, and bootstrap never edits harness settings (for example,
`.claude/settings.json`). Repository owners review the staged file, verify the
current harness hook schema, and **register the hook manually** in the harness
configuration before it takes effect.

Available templates:

| Template | Staged path (target repo) | Purpose |
|---|---|---|
| `session-start.sh` | `.agent/hooks/session-start.sh` | Inject rulebase reminders at session start (SessionStart event). |
| `pre-tool-use-secret-guard.py.template` | `.agent/hooks/pre-tool-use-secret-guard.py` | Block write tools (`Edit`, `Write`, `MultiEdit`) on secret files and high-risk `.agent/` governance paths (PreToolUse event). |
| `pre-tool-use-rulebase-guard.py.template` | `.agent/hooks/pre-tool-use-rulebase-guard.py` | Deny direct writes to `.agent/constitution.md` and require explicit approval (`ask`) for `.agent/rulebase.md` (PreToolUse event). |

## Why off by default

Hooks run with the **user credentials** of whoever launches the harness. A hook
can observe tool inputs and influence tool decisions. A template repo cannot
guarantee:

- the current input/output schema of any specific harness;
- that a generic policy matches the repo's threat model;
- that the repo owner has reviewed the script before registration.

Because of these constraints, bootstrap stages the file and prints a warning,
but never registers the hook. The repo owner is the only party that can
confirm policy fit and verify schema compatibility.

## Staging hooks during bootstrap

```bash
scripts/bootstrap-request.sh --install-hook                    # SessionStart only (alias for =session-start)
scripts/bootstrap-request.sh --install-hook=session-start
scripts/bootstrap-request.sh --install-hook=secret-guard
scripts/bootstrap-request.sh --install-hook=rulebase-guard
scripts/bootstrap-request.sh --install-hook=both                # session-start + secret-guard (legacy)
scripts/bootstrap-request.sh --install-hook=all                 # session-start + secret-guard + rulebase-guard
```

Any other `--install-hook=<value>` is rejected.

After bootstrap, the staged file lives under `.agent/hooks/` and is marked
executable, but is not connected to any tool. Confirm the harness PreToolUse
or SessionStart **schema** in the official harness documentation before you
register the hook in your harness settings. Bootstrap leaves harness settings
untouched.

## PreToolUse secret-guard contract

`pre-tool-use-secret-guard.py.template` is a standalone Python 3 script with
no third-party dependencies. It reads a PreToolUse JSON payload from stdin
and emits a JSON decision on stdout only when denying a write attempt.

Behavior:

- Write tool (`Edit`, `Write`, `MultiEdit`) on a protected path → exit `0`,
  stdout JSON with `hookSpecificOutput.permissionDecision: deny`.
- Write tool on a non-protected path → exit `0`, no stdout.
- Non-write tool (`Read`, `Grep`, `Bash`, etc.) → exit `0`, no stdout.
- Malformed JSON or unexpected shape → exit `0`, no stdout (fail-open).

The deny payload contains only the protected path inside
`permissionDecisionReason`. The hook never echoes the incoming payload and
never reads or prints `tool_input.content`, so editor content stays out of
hook stdout.

Protected paths (initial policy; review and adjust to fit your repo):

- `.env`, `.env.<anything>`, basenames matching `.env.<anything>`
- `credentials`, `credentials.json`
- `.npmrc`, `.pypirc`
- any path segment containing `secrets/`
- `.aws/credentials`
- `.ssh/` directory contents
- `id_rsa`, `id_ed25519`
- `.agent/rulebase.md`, `.agent/gates.md`

## PreToolUse rulebase-guard contract

`pre-tool-use-rulebase-guard.py.template` is a focused PreToolUse hook for
governance files. Like the secret-guard, it has no third-party dependencies,
reads PreToolUse JSON from stdin, and emits a JSON decision on stdout only
when intervening on a write attempt.

Behavior:

- Write tool (`Edit`, `Write`, `MultiEdit`) on `.agent/constitution.md` →
  exit `0`, stdout JSON with `permissionDecision: "deny"`. The constitution
  is non-negotiable safety policy and amendments require explicit human
  approval.
- Write tool on `.agent/rulebase.md` → exit `0`, stdout JSON with
  `permissionDecision: "ask"`. Rulebase changes must follow
  `.agent/workflows/rule-evolution-workflow.md`; the harness asks the user
  before allowing the edit.
- Anything else → exit `0`, no stdout (allow).
- Malformed JSON, non-write tools, or unexpected payload shape → exit `0`,
  no stdout (fail-open, identical to secret-guard).
- The hook never reads `tool_input.content`, never echoes payloads, and
  never relies on commit message, branch name, or conversation context.

The decision reason is built from the file path only and points the operator
at the rule-evolution workflow. Adjust `PROTECTED_DECISIONS` if your repo
uses a different governance layout.

## Manual registration

After staging:

1. Read the staged hook file under `.agent/hooks/` and confirm the policy.
2. Verify the current PreToolUse / SessionStart schema in your harness docs.
3. Register the hook in the harness configuration (for Claude Code, that is
   typically `.claude/settings.json`).
4. Run a smoke test against a known-protected path before relying on the hook
   in real workflows. The included tests under `tests/lib/` exercise the
   secret-guard contract for the template repo.

If the harness schema diverges from the contract documented above, update the
hook before registration. Treat staged files as a starting shape, not a
finished policy.
