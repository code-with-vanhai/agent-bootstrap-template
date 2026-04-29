# Plan: PreToolUse Secret Guard Hook (P0-3)

**Status:** Verified with evidence: agent-validate.sh @ 2026-04-29T04:21:17Z (exit=0); test_secret_guard_hook.sh @ same window (12 cases pass); 84 unittest pass
**Date:** 2026-04-29
**Ref commit:** `c525be4` (pre-implementation; impl-stale evidence blocks below converted to `historical-code`)
**Plan location note:** Stored under `docs/plans/bootstrap-090/p0-3-pretooluse-secret-guard/` because this template repo dogfoods plans there; generated target repos should use `.agent/runs/<date>-<slug>/`.

## Goal

Add an off-by-default PreToolUse secret-guard hook template that repository owners can stage during bootstrap, review, and manually register in their harness to block write tools from editing secrets and high-risk `.agent/` governance files.

## Run Artifact

`docs/plans/bootstrap-090/p0-3-pretooluse-secret-guard/{spec.md,plan.md}`

## Affected Areas

- `core/hooks/pre-tool-use-secret-guard.py.template` — new standalone Python hook template with no dependency on `jq`.
- `core/hooks/README.md` — new hook documentation and manual registration notes.
- `scripts/bootstrap-request.sh` — hook option parsing, staging behavior, status text, and warning output.
- `tests/lib/test_secret_guard_hook.sh` — new shell fixture test for hook behavior.
- `scripts/lib/test_validate_agent_system.py` — generated bootstrap tests for hook option modes.

## Owner

Implementer role. Reviewer should inspect hook output shape and stdout behavior because hooks run with user credentials and must not leak tool input.

## Implementation Plan

1. Replace the internal `install_hook` boolean in `scripts/bootstrap-request.sh` with a hook mode variable such as `install_hook_mode="none"`.
2. Preserve bare `--install-hook` as `session-start`, and add parsing for `--install-hook=session-start`, `--install-hook=secret-guard`, and `--install-hook=both`.
3. Reject unknown `--install-hook=<value>` values with a clear `die` message.
4. Add `core/hooks/pre-tool-use-secret-guard.py.template` as a standalone executable Python script with `#!/usr/bin/env python3`, JSON stdin parsing, and no third-party dependencies.
5. In the hook script, allow only `Edit`, `Write`, and `MultiEdit` checks to make a deny decision; non-write tools should exit `0` with no stdout.
6. Match protected paths using `os.path.basename`, normalized path segments, and literal substring checks for the protected list in `spec.md`.
7. When denying, print only `hookSpecificOutput.hookEventName`, `permissionDecision`, and `permissionDecisionReason`; do not print the incoming payload or any `tool_input.content`.
8. On malformed JSON, exit `0` with no stdout and document this as fail-open for template robustness.
9. Update `copy_hook()` to stage `session-start.sh`, `pre-tool-use-secret-guard.py`, or both, setting mode `755` for executable hooks.
10. Update `write_pending()` to report staged SessionStart and secret-guard hooks separately.
11. Add `core/hooks/README.md` with warning language: hooks run with user credentials, the template is a shape, current harness schema must be verified before registration, and bootstrap does not edit `.claude/settings.json`.
12. Add shell fixtures in `tests/lib/test_secret_guard_hook.sh` for deny, allow, non-write, malformed JSON, and payload leak behavior.
13. Add generated bootstrap tests for bare `--install-hook`, `--install-hook=secret-guard`, and `--install-hook=both`.
14. Run verification gates listed below.

## Acceptance Criteria

| ID | Criterion | Verification Method | Gate |
|---|---|---|---|
| AC-1 | Bare `--install-hook` keeps staging `.agent/hooks/session-start.sh` only | `AUTOMATED-UNIT` | `python3 -m unittest scripts.lib.test_validate_agent_system` |
| AC-2 | `--install-hook=secret-guard` stages `.agent/hooks/pre-tool-use-secret-guard.py` with executable mode and does not stage SessionStart | `AUTOMATED-UNIT` | same |
| AC-3 | `--install-hook=both` stages both hook files | `AUTOMATED-UNIT` | same |
| AC-4 | The secret-guard hook denies `Edit` on `.env` with `hookSpecificOutput.permissionDecision: deny` | `AUTOMATED-UNIT` | `bash tests/lib/test_secret_guard_hook.sh` |
| AC-5 | The hook exits `0` with no stdout for `Edit` on `src/foo.ts` | `AUTOMATED-UNIT` | same |
| AC-6 | The hook exits `0` with no stdout for `Read` on `.env` | `AUTOMATED-UNIT` | same |
| AC-7 | The hook exits `0` with no stdout for malformed JSON | `AUTOMATED-UNIT` | same |
| AC-8 | The hook output does not include `tool_input.content` for a denied write | `AUTOMATED-UNIT` | same |
| AC-9 | `core/hooks/README.md` documents off-by-default staging, schema verification, credential warning, and manual registration | `AUTOMATED-UNIT` | `python3 -m unittest scripts.lib.test_validate_agent_system` or dedicated doc assertion |
| AC-10 | `scripts/agent-validate.sh` passes in the source repo | `AUTOMATED-INTEGRATION` | `scripts/agent-validate.sh` |
| AC-11 | Deterministic evals remain green | `AUTOMATED-INTEGRATION` | `bash scripts/agent-evals.sh --fast` |
| AC-12 | P0-3 plan artifact validates with strict mode before implementation | `AUTOMATED-INTEGRATION` | `scripts/agent-validate-plan.sh --force --strict docs/plans/bootstrap-090/p0-3-pretooluse-secret-guard` |

## Evidence

The evidence blocks below ground the current hook CLI, SessionStart hook behavior, and generated-repo test fixture style before P0-3 implementation.

<!-- historical-code path=scripts/bootstrap-request.sh lines=23-31 ref=c525be4 region_sha256=288826a11b162388fb0a1ed69751e2252bf7613ee5a2186f6fad94af7366409a -->
```bash
Options:
  --target <path>          Target repository path (default: .)
  --template <path>        agent-bootstrap-template path (default: script parent)
  --features <level>      minimal, standard, or full (default: standard)
  --harness <name>        generic, codex, claude, cursor, copilot, or gemini (default: generic)
  --install-hook          Stage optional SessionStart hook under .agent/hooks/
  --force                 Overwrite existing generated files
  --dry-run               Print actions without writing files
  -h, --help              Show this help
```
<!-- /historical-code -->

<!-- historical-code path=scripts/bootstrap-request.sh lines=70-72 ref=c525be4 region_sha256=0147160c599b084024d47a93b464c164870d61634ac88ad7a2c59c9529a24ea2 -->
```bash
    --install-hook)
      install_hook="1"
      shift
```
<!-- /historical-code -->

<!-- current-code path=core/hooks/session-start.sh lines=1-7 ref=c525be4 region_sha256=fc4303be193fe9c9187fff33f620218f97cedf03e85d6e0f1149efdffe43fa16 -->
```bash
#!/usr/bin/env bash
set -euo pipefail

# Optional SessionStart hook template for harnesses that support context injection.
# This script is off by default. Copy it into the target harness hook location only
# when the project intentionally wants rulebase reminders injected at session start.

```
<!-- /current-code -->

<!-- current-code path=core/hooks/session-start.sh lines=53-59 ref=c525be4 region_sha256=4d84f5e91a539c1b40bf2d0731a0475113f7c10887dbe53691c006ebda29cc45 -->
```bash
if [ -n "${CURSOR_PLUGIN_ROOT:-}" ]; then
  printf '{\n  "additional_context": "%s"\n}\n' "$context_escaped"
elif [ -n "${CLAUDE_PLUGIN_ROOT:-}" ]; then
  printf '{\n  "hookSpecificOutput": {\n    "hookEventName": "SessionStart",\n    "additionalContext": "%s"\n  }\n}\n' "$context_escaped"
else
  printf '{\n  "additionalContext": "%s"\n}\n' "$context_escaped"
fi
```
<!-- /current-code -->

<!-- historical-code path=scripts/lib/test_validate_agent_system.py lines=32-49 ref=c525be4 region_sha256=60ab13f25f024c56f2c4dc47c184f8290a571c74b315a0344ab06b787d5ae56e -->
```python
    def make_target(self, *, features: str = "standard", harness: str = "generic") -> Path:
        target = Path(tempfile.mkdtemp(prefix="agent-system-validator-"))
        self.addCleanup(lambda: shutil.rmtree(target, ignore_errors=True))
        subprocess.run(
            [
                str(ROOT / "scripts" / "bootstrap-request.sh"),
                "--target",
                str(target),
                "--features",
                features,
                "--harness",
                harness,
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return target
```
<!-- /historical-code -->

## Existing Behaviors Preserved

- `scripts/bootstrap-request.sh:23-31` — CLI usage is `PRESERVED` except that the `--install-hook` line will document the new value forms while keeping the bare flag behavior.
- `scripts/bootstrap-request.sh:70-72` — bare `--install-hook` parsing is `PRESERVED` as an alias for SessionStart staging, even though named modes are added.
- `core/hooks/session-start.sh:1-7` — the existing SessionStart hook remains off by default and opt-in. P0-3 adds a second staged hook path; it does not auto-register SessionStart.
- `core/hooks/session-start.sh:53-59` — existing SessionStart output shape is `PRESERVED`; the new PreToolUse hook uses its own `hookSpecificOutput` contract and does not change this file's output behavior.
- `scripts/lib/test_validate_agent_system.py:32-49` — generated-repo fixture creation stays based on `scripts/bootstrap-request.sh`; P0-3 adds hook mode tests using the same fixture style.

## Verification

Pre-implementation plan validation:

```bash
scripts/agent-validate-plan.sh --force --strict docs/plans/bootstrap-090/p0-3-pretooluse-secret-guard
```

Post-implementation gates:

```bash
bash tests/lib/test_secret_guard_hook.sh
python3 -m unittest scripts.lib.test_validate_agent_system
scripts/agent-validate.sh
bash scripts/agent-evals.sh --fast
scripts/agent-validate-plan.sh --force --strict docs/plans/bootstrap-090/p0-3-pretooluse-secret-guard
```

## Required Gates

- `scripts/agent-validate-plan.sh --force --strict docs/plans/bootstrap-090/p0-3-pretooluse-secret-guard` before implementation.
- `bash tests/lib/test_secret_guard_hook.sh` after implementation.
- `python3 -m unittest scripts.lib.test_validate_agent_system` after implementation.
- `scripts/agent-validate.sh` after implementation.
- `bash scripts/agent-evals.sh --fast` after implementation.

## Docs/Tests/Contracts To Update

- Docs: `core/hooks/README.md`; `scripts/bootstrap-request.sh --help` text; `bootstrap-pending.md` hook status text.
- Tests: `tests/lib/test_secret_guard_hook.sh`; `scripts/lib/test_validate_agent_system.py`.
- Contracts: `--install-hook=<mode>` accepted values; PreToolUse deny JSON shape.

## Decision Ledger

| Decision | Chosen Behavior | Rationale | Alternatives Rejected | Caller/User Impact | Verification |
|---|---|---|---|---|---|
| Hook language | Standalone Python executable `.py.template` | Python stdlib JSON parsing avoids `jq` and avoids heredoc stdin collisions | Bash plus `jq`; adds dependency. Bash heredoc Python; consumes stdin as source instead of hook payload | Users get a reviewable file that can read hook stdin correctly | `bash tests/lib/test_secret_guard_hook.sh` |
| Registration | Stage only, never edit `.claude/settings.json` | Hooks run with user credentials and should be reviewed before registration | Auto-register during bootstrap; too much privilege for a template | Repo owners opt in after review | README assertion and bootstrap smoke test |
| CLI compatibility | Bare `--install-hook` remains SessionStart | Preserves current behavior for existing users | Require `--install-hook=session-start`; would break existing command usage | Existing bootstrap commands keep working | generated hook mode tests |
| Named hook modes | Support `session-start`, `secret-guard`, and `both` | Clear explicit modes without adding multiple flags | Separate `--install-secret-guard`; grows CLI surface | Users can stage exactly one or both hooks | generated hook mode tests |
| Deny output | Use `hookSpecificOutput.permissionDecision: deny` | Matches current PreToolUse output contract and avoids deprecated root-level `decision` | Root-level `decision` and `reason`; deprecated shape | Claude Code can interpret the deny decision | hook fixture parses stdout JSON |
| Allowed behavior | Exit `0` with no stdout for allowed paths, non-write tools, and malformed JSON | Avoids leaking payload and avoids blocking on schema mismatch in a template | Echo input; leaks content. Exit nonzero on parse error; can break sessions | Safer default for a staged template | no-stdout fixture tests |
| Protected surface | Block secrets plus `.agent/rulebase.md` and `.agent/gates.md` for write tools | Covers credential leakage and governance weakening paths | Only block `.env`; too narrow. Block all `.agent`; too broad for normal planning artifacts | High-risk edits require explicit human path outside this hook | deny fixtures for representative paths |

## Contract Value Table

| Literal | Producer | Consumer | User-facing behavior | Test |
|---|---|---|---|---|
| `--install-hook=secret-guard` | `scripts/bootstrap-request.sh` CLI parser | Bootstrap users | Stages only `.agent/hooks/pre-tool-use-secret-guard.py` | generated hook mode test |
| `--install-hook=both` | `scripts/bootstrap-request.sh` CLI parser | Bootstrap users | Stages SessionStart and secret-guard hooks | generated hook mode test |
| `.agent/hooks/pre-tool-use-secret-guard.py` | `scripts/bootstrap-request.sh::copy_hook` | Repo owner / harness hook config | Reviewable executable hook path in target repo | generated hook mode test |
| `hookSpecificOutput` | secret-guard hook stdout | Claude Code PreToolUse hook runner | Uses current hook-specific output envelope | hook deny fixture |
| `permissionDecision` | secret-guard hook stdout | Claude Code PreToolUse hook runner | Denies protected write attempts | hook deny fixture |

## Test Delta

| Action | Test | Why | Expected |
|---|---|---|---|
| ADD | `tests/lib/test_secret_guard_hook.sh` `Edit` `.env` | Covers protected secret write denial | stdout JSON contains `permissionDecision: deny` |
| ADD | `tests/lib/test_secret_guard_hook.sh` `Edit` `src/foo.ts` | Covers allowed write path | exit `0`, no stdout |
| ADD | `tests/lib/test_secret_guard_hook.sh` `Read` `.env` | Covers non-write tool pass-through | exit `0`, no stdout |
| ADD | `tests/lib/test_secret_guard_hook.sh` malformed JSON | Covers schema mismatch handling | exit `0`, no stdout |
| ADD | `tests/lib/test_secret_guard_hook.sh` denied payload with `tool_input.content` | Covers payload leak regression | stdout does not contain the content |
| ADD | `scripts/lib/test_validate_agent_system.py` bare `--install-hook` | Preserves existing CLI behavior | SessionStart only |
| ADD | `scripts/lib/test_validate_agent_system.py` `--install-hook=secret-guard` | Covers new secret-guard mode | secret guard only |
| ADD | `scripts/lib/test_validate_agent_system.py` `--install-hook=both` | Covers combined hook mode | both hooks |
| KEEP | `scripts/lib/test_validate_agent_system.py` generated standard/bootstrap validation | Guards unrelated bootstrap behavior | still passes |

## Risks

- Risk: Claude Code hook input shape may change. Mitigation: keep the hook off by default, document schema verification, and fail open on malformed JSON.
- Risk: A deny message could leak sensitive tool input. Mitigation: construct the reason only from the path and never echo the payload.
- Risk: Users may assume staging means registration. Mitigation: README and bootstrap-pending status must state manual registration is still required.
- Risk: Protected path matching may block legitimate rule evolution work. Mitigation: deny message points users to rule-evolution workflow and explicit human approval.
