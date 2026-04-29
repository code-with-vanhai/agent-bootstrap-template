# Spec: PreToolUse Secret Guard Hook (P0-3)

**Status:** Verified with evidence: agent-validate.sh @ 2026-04-29T04:21:17Z (exit=0); test_secret_guard_hook.sh 12 cases pass
**Date:** 2026-04-29
**Ref commit:** `c525be4` (pre-implementation reference; impl landed in working tree)
**Plan location note:** Stored under `docs/plans/bootstrap-090/p0-3-pretooluse-secret-guard/` because this template repo dogfoods plans under `docs/plans/`, not `.agent/runs/`. Generated target repos should use `.agent/runs/<date>-<slug>/`.
**Track:** 0.9.0 P0-3, after P0-1 commit `c525be4`; P0-2 changes may still be in the working tree.

## Problem

The template currently provides one optional hook, `core/hooks/session-start.sh`, and `scripts/bootstrap-request.sh --install-hook` only stages that SessionStart helper. It does not provide a deterministic PreToolUse example for blocking writes to secrets or high-risk `.agent/` governance files.

This leaves secret and rulebase protection as prompt-level policy only. A staged, off-by-default PreToolUse hook template would give repository owners a concrete implementation pattern while preserving human review before hook registration.

## Goals

- Add a standalone Python executable template at `core/hooks/pre-tool-use-secret-guard.py.template`.
- Keep the hook off by default and staged only when requested.
- Extend bootstrap hook staging to support `--install-hook=session-start`, `--install-hook=secret-guard`, and `--install-hook=both`.
- Preserve bare `--install-hook` as an alias for `session-start`.
- Emit current Claude PreToolUse output shape with `hookSpecificOutput.permissionDecision`.
- Avoid echoing hook input to stdout.
- Avoid extra runtime dependencies such as `jq`.
- Add documentation in `core/hooks/README.md` that explains the template status, schema verification requirement, and manual harness registration.
- Add tests for deny/pass-through/malformed input/no content leak behavior.

## Non-Goals

- No automatic `.claude/settings.json` registration.
- No hook execution during bootstrap.
- No policy change to `.agent/rulebase.md` or `.agent/gates.md`.
- No cryptographic signing or permission-locking for rulebase files.
- No support for non-Claude hook schemas beyond documenting that the script shape must be verified before use.
- No implementation in this spec/plan turn.

## Hook Input Assumption

The hook assumes the current Claude Code PreToolUse payload contains:

```json
{
  "tool_name": "Edit",
  "tool_input": {
    "file_path": ".env"
  }
}
```

The hook must also accept `tool_input.path` because some tool payloads use `path` instead of `file_path`.

## Deny Output Contract

For protected write attempts, stdout should be a JSON object like:

```json
{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "deny",
    "permissionDecisionReason": "Path .env is protected by .agent/ secret-guard hook."
  }
}
```

The script should exit `0` after printing the denial JSON. For allowed tools/paths, malformed JSON, or non-write tools such as `Read`, it should exit `0` with no stdout.

## Protected Paths

The first version should block `Edit`, `Write`, and `MultiEdit` when the target path matches:

- `.env`, `.env.*`, or basename starting with `.env.`
- `credentials`, `credentials.json`
- `.npmrc`, `.pypirc`
- any path segment containing `secrets/`
- `.aws/credentials`
- `.ssh/`
- `id_rsa`, `id_ed25519`
- `.agent/rulebase.md`
- `.agent/gates.md`

This is intentionally conservative and file-path based. It should not inspect or print `tool_input.content`.

## Bootstrap CLI Contract

`scripts/bootstrap-request.sh` should support:

```text
--install-hook
--install-hook=session-start
--install-hook=secret-guard
--install-hook=both
```

Bare `--install-hook` keeps the current behavior and stages only `session-start.sh`.

When `secret-guard` is requested, the script should copy `core/hooks/pre-tool-use-secret-guard.py.template` to `.agent/hooks/pre-tool-use-secret-guard.py`, set mode `755`, and print a clear warning that the hook is only staged and must be reviewed and registered manually in the harness.

## Validation Expectations

- `scripts/agent-validate.sh` must pass in the source template.
- Hook behavior fixtures must pass through `tests/lib/test_secret_guard_hook.sh`.
- Generated standard bootstrap with bare `--install-hook` must keep staging only `.agent/hooks/session-start.sh`.
- Generated bootstrap with `--install-hook=secret-guard` must stage only `.agent/hooks/pre-tool-use-secret-guard.py`.
- Generated bootstrap with `--install-hook=both` must stage both hooks.
- `scripts/agent-validate-plan.sh --force --strict docs/plans/bootstrap-090/p0-3-pretooluse-secret-guard` must pass before implementation starts.
