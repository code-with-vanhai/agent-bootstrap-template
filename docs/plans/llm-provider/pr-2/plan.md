# PR-2 Plan: Codex provider + `--provider` CLI + plugin-eval gate + harness fixture + mocks

**Status:** Draft
**Date:** 2026-04-28
**Parent proposal:** `docs/2026-04-27-llm-provider-abstraction-proposal.md` (revision 3.1, approved)
**Plan location note:** Stored under `docs/plans/llm-provider/pr-2/plan.md` for the same reason PR-1 was: `scripts/agent-validate.sh:244` treats existence of `.agent/` as "downstream repo" mode, so template-repo dogfooding plans live under `docs/plans/`.
**Scope:** PR-2 of 3 in the 0.5.0 LLM provider abstraction series. Adds the Codex branch and the user-facing `--provider` flag. PR-1 added the seam; PR-2 fills it.
**Ref commit:** `619bd2d`

---

## Goal

Make `--provider codex` actually route to the Codex CLI:

1. Fill in the codex branch of every `llm_provider_*` function (registry was claude-only after PR-1).
2. Add `--provider <name>` flag and `AGENT_LLM_PROVIDER` env handling in `scripts/agent-evals.sh`, including provider-aware bin lookup and SKIP wording.
3. SKIP `tests/evals/plugin-command-load.sh` cleanly when `provider != claude` (it is intentionally Claude-Code-specific).
4. Add `tests/evals/codex-harness-fixture.sh` — a deterministic eval that asserts `bootstrap-request.sh --harness codex --features full` produces the expected SKILL.md tree. **No real Codex CLI invocation.**
5. Check in the remaining 3 mocks (`claude-misaligned.sh`, `codex-quota.sh`, `codex-auth.sh`).
6. Extend `tests/lib/test_llm_provider.sh` with full codex-branch coverage.

PR-2 is additive. `--provider claude --behavior` and `--provider claude --integration` preserve PR-1 behavior byte-for-byte. Two intentional changes apply on the default provider as well:

1. **`--provider codex` now works** (the entire point of PR-2).
2. **`--fast` runs 2 deterministic evals instead of 1**: the new `tests/evals/codex-harness-fixture.sh` is added to `deterministic_evals` unconditionally because it is a pure filesystem check (no LLM CLI invoked) and exists regardless of provider. Default `--fast` exit code is unchanged (still 0 in CI), but the set is one larger. Documented in Existing Behaviors Preserved as ADDITIVE.

---

## Context (Grounding)

### Registry codex branches are stubs after PR-1

<!-- current-code path=scripts/lib/llm_provider.sh lines=22-27 ref=619bd2d region_sha256=7461ff4a8b1f6e3a9e3afa0ff406b8145e2fa64880d2f03d496b8fcab7c603bf -->
```bash
llm_provider_is_known() {
  case "$1" in
    claude) return 0 ;;
    *) return 1 ;;
  esac
}
```
<!-- /current-code -->

<!-- current-code path=scripts/lib/llm_provider.sh lines=77-82 ref=619bd2d region_sha256=76d74ebf52b6467595ea2fa51294c6e9178becb532e3263523ed94413b61fc82 -->
```bash
llm_provider_run() {
  case "$1" in
    claude) _llm_invoke_claude "$2" "$3" ;;
    *) printf 'Unknown LLM provider: %s\n' "$1" >&2; return 2 ;;
  esac
}
```
<!-- /current-code -->

PR-2 replaces both `*) return 1` / `*) printf 'Unknown...'` arms with `codex)` arms before falling through to the unknown handler. `llm_provider_default_bin`, `llm_provider_bin`, and `llm_provider_is_unavailable` get the same treatment.

(Line ranges above are 22-27 and 77-82, not the file-leading comment lines; these are the actual function bodies.)

### Runner is hard-coded to Claude

<!-- current-code path=scripts/agent-evals.sh lines=11-11 ref=619bd2d region_sha256=553b7e672b6ab357ed6d060ced95c34e865396f9d3e48bca62bc6e141634d062 -->
```bash
claude_bin="${CLAUDE_BIN:-claude}"
```
<!-- /current-code -->

<!-- current-code path=scripts/agent-evals.sh lines=118-125 ref=619bd2d region_sha256=8ae46974baabef9d18cd98a5cbe2a77be9cd48d1671b431d01610b3b89cc117b -->
```bash
if [ "$needs_claude" = "1" ] && ! command -v "$claude_bin" >/dev/null 2>&1; then
  if [ "$skip_on_missing_cli" = "1" ]; then
    printf 'SKIP: %s CLI not found; LLM-driven evals were not run.\n' "$claude_bin"
    exit 0
  fi
  printf 'FAIL: %s CLI not found.\n' "$claude_bin" >&2
  exit 1
fi
```
<!-- /current-code -->

<!-- current-code path=scripts/agent-evals.sh lines=137-154 ref=619bd2d region_sha256=c2a9cb57783653b79a28477d5a489f96463b7ec220ee7bcdf5e5bd05f80d64ac -->
```bash
  printf '\n>>> %s\n' "$eval_script"
  set +e
  CLAUDE_BIN="$claude_bin" EVAL_TIMEOUT="$timeout_seconds" EVAL_VERBOSE="$verbose" "$eval_script"
  rc=$?
  set -e
  case "$rc" in
    0)
      printf 'PASS: %s\n' "$eval_script"
      ;;
    77)
      printf 'SKIP: %s (claude CLI unavailable)\n' "$eval_script"
      skipped=$((skipped + 1))
      ;;
    *)
      printf 'FAIL: %s\n' "$eval_script" >&2
      failures=$((failures + 1))
      ;;
  esac
```
<!-- /current-code -->

The variable `claude_bin`, the SKIP wording `"%s CLI unavailable"` (hard-coded "claude" in line 147), and the missing-CLI wording `"%s CLI not found"` are all PR-2 surfaces. PR-2 replaces them with provider-aware lookups that resolve through `llm_provider_bin "$provider"` and use `"$provider"` (not the literal string `"claude"`) in user-facing messages.

### plugin-command-load.sh is Claude-Code-specific by design

<!-- current-code path=tests/evals/plugin-command-load.sh lines=11-17 ref=619bd2d region_sha256=f6a4775d782632958980db7bf0f6358109be60c01d89e0c9f110f7d2e7fdcb78 -->
```bash
claude_bin="${CLAUDE_BIN:-claude}"
timeout_seconds="${EVAL_TIMEOUT:-30}"

if ! command -v "$claude_bin" >/dev/null 2>&1; then
  printf 'SKIP: %s CLI not found; plugin command load eval was not run.\n' "$claude_bin"
  finish_test_skip
fi
```
<!-- /current-code -->

The probe uses `--plugin-dir`/`--debug-file`/`--print` which are **only** supported by Claude Code. PR-2 inserts an early guard: if `${AGENT_LLM_PROVIDER:-claude}` is not `claude`, SKIP with reason `"plugin probe is Claude-Code-specific"`. The existing Claude-bin-missing skip remains unchanged for the `claude` case.

### Codex harness fixture grounding

<!-- current-code path=scripts/bootstrap-request.sh lines=385-405 ref=619bd2d region_sha256=6593e3863e9f173ac7186617917779e75ec46d1e35caaf5e264727d9ce249aec -->
```bash
copy_skills() {
  [ "$features" = "full" ] || return 0

  skill_dest=""
  case "$harness" in
    codex)
      skill_dest="$TARGET_ROOT/.agents/skills/agent-bootstrap"
      ;;
    claude)
      skill_dest="$TARGET_ROOT/.claude/skills/agent-bootstrap"
      ;;
    *)
      return 0
      ;;
  esac

  for skill_file in "$TEMPLATE_ROOT"/core/skills/*/SKILL.md; do
    skill_name="$(basename "$(dirname "$skill_file")")"
    copy_file "$skill_file" "$skill_dest/$skill_name/SKILL.md"
  done
}
```
<!-- /current-code -->

`tests/evals/codex-harness-fixture.sh` will assert exactly the files this loop produces under `--harness codex`: `.agents/skills/agent-bootstrap/<skill>/SKILL.md` for each of the 7 entries in `core/skills/` (excluding `README.md`), plus the `agent-<command>` SKILL.md files written by `copy_codex_command_skills` for each of the 9 entries in `core/commands/`.

---

## Plan

### 1. Extend `scripts/lib/llm_provider.sh` with codex branches

In each of the 5 functions, add a `codex)` arm before the unknown fallthrough:

- `llm_provider_is_known`: `claude|codex) return 0`.
- `llm_provider_default_bin`: `codex) printf 'codex'`.
- `llm_provider_bin`: `codex) printf '%s' "${CODEX_BIN:-codex}"`.
- `llm_provider_run`: `codex) _llm_invoke_codex "$2" "$3"`.
- `llm_provider_is_unavailable`: codex regex (conservative — Q2 partially open).

Add `_llm_invoke_codex`. Per Q1 (verified `codex-cli 0.124.0`):

```bash
codex exec --skip-git-repo-check --color never --sandbox workspace-write $CODEX_EXTRA_ARGS "$prompt"
```

`CODEX_EXTRA_ARGS` is positioned **before** the prompt (review #3). `--sandbox workspace-write` is the default because integration evals (`no-unrelated-changes`, `bootstrap-pending-completion`) mutate temp repos; users tightening to read-only override via `CODEX_EXTRA_ARGS="--sandbox read-only"`.

Codex quota regex (conservative initial set, documented Q2 gap):

```text
(rate limit|usage limit|quota exceeded|insufficient (credits|quota)|invalid api key|authentication (error|failed)|please (log ?in|sign ?in|authenticate)|http (status )?(401|403|429)|too many requests)
```

### 2. Refactor `scripts/agent-evals.sh`

- Source `scripts/lib/llm_provider.sh` near the top (after `cd "$ROOT"`).
- Replace `claude_bin="${CLAUDE_BIN:-claude}"` with provider-aware resolution: `provider="${AGENT_LLM_PROVIDER:-claude}"` then `bin="$(llm_provider_bin "$provider")"`.
- Add `--provider <name>` arg parsing. Validate via `llm_provider_is_known "$provider"` — exit 2 with `"Unknown LLM provider: $provider"` + help suggestion if not.
- Update missing-CLI handling: `"$provider CLI not found"` (was hard-coded "claude").
- Update eval-loop SKIP wording: `"$provider CLI unavailable"` (was hard-coded "claude").
- Pass `AGENT_LLM_PROVIDER="$provider"` env to eval scripts so `run_llm` inside dispatches correctly.
- Continue passing `CLAUDE_BIN` for back-compat AND set `<PROVIDER>_BIN` derived from `bin` so the eval child reads the resolved bin even if CLI flag overrode env.
- **Normalize relative-with-slash bin paths to absolute** right after `llm_provider_bin` resolution. Eval helpers `cd` into temp project dirs before exec; a relative `CODEX_BIN=tests/evals/mocks/codex-quota.sh` would pass the repo-root precheck and then ENOENT when the eval child `cd`s away. The fix preserves bare-name bins (no slash) so PATH lookup still works. Same fix applies to `CLAUDE_BIN` (transparent improvement; PR-1 worked around this with `$(pwd)/...` in the verification command).
- Update `--help` to document `--provider`, `AGENT_LLM_PROVIDER`, `CLAUDE_BIN`, `CODEX_BIN`, `CODEX_EXTRA_ARGS` (the existing `CLAUDE_EXTRA_ARGS` is already implicit in `run_claude` documentation).
- Add `tests/evals/codex-harness-fixture.sh` to the `deterministic_evals` array so `--fast` exercises it.

### 3. Refactor `tests/evals/plugin-command-load.sh`

Insert before the existing `command -v "$claude_bin"` check:

```bash
if [ "${AGENT_LLM_PROVIDER:-claude}" != "claude" ]; then
  printf 'SKIP: plugin probe is Claude-Code-specific (provider=%s)\n' "${AGENT_LLM_PROVIDER:-claude}"
  finish_test_skip
fi
```

The existing claude-bin-missing skip stays. `is_claude_unavailable_output` continues to be called against Claude output (this eval is pinned to claude by the new guard).

### 4. New file: `tests/evals/codex-harness-fixture.sh`

Deterministic eval. No LLM CLI invoked. Steps:

1. `tmp=$(mktemp -d)`
2. `scripts/bootstrap-request.sh --harness codex --features full --target "$tmp"`
3. For each `core/skills/<name>/SKILL.md` (excluding `core/skills/README.md`), assert `$tmp/.agents/skills/agent-bootstrap/<name>/SKILL.md` exists.
4. For each `core/commands/<cmd>.md`, assert `$tmp/.agents/skills/agent-bootstrap/agent-<cmd>/SKILL.md` exists.
5. `rm -rf "$tmp"` on EXIT.

Hard-coded list expectations: 7 skills + 9 commands = 16 expected SKILL.md files. The exact list is computed at runtime from `core/skills/` and `core/commands/` so adding a future skill/command does not break the eval.

### 5. New mocks under `tests/evals/mocks/`

- `claude-misaligned.sh` — emits a benign assistant-style response that does NOT match any assertion regex; used to demonstrate a real FAIL path (not just SKIP).
- `codex-quota.sh` — emits a Codex-shaped quota error matching the new conservative regex.
- `codex-auth.sh` — emits an authentication-required error.

All three are checked in with `chmod +x`. Each is a 1-line `printf` plus `exit 0`. Same shape as the existing `claude-quota.sh` from PR-1.

### 6. Extend `tests/lib/test_llm_provider.sh` with codex coverage

Replace the PR-1 codex stub group (3 PR-1 cases that asserted "codex returns Unknown") with:

- `llm_provider_is_known codex` returns 0.
- `llm_provider_default_bin codex` prints `codex`.
- `llm_provider_bin codex` honors `CODEX_BIN=/tmp/x` override; defaults to `codex` when unset.
- `llm_provider_is_unavailable codex` matches each known codex error variant from the regex.
- `llm_provider_is_unavailable codex` does NOT match a benign assistant response.
- `llm_provider_run codex` with mock `CODEX_BIN` actually invokes the bin; mock receives `exec --skip-git-repo-check --color never --sandbox workspace-write` AND respects `CODEX_EXTRA_ARGS` placement before the prompt (review #3).
- `llm_provider_run unknown` still exits 2 with `Unknown LLM provider: unknown`.

---

## Acceptance Criteria

| ID | Criterion | Verification Method |
|---|---|---|
| AC-1 | `scripts/agent-evals.sh --help` lists `--provider` and documents `AGENT_LLM_PROVIDER`, `CLAUDE_BIN`, `CODEX_BIN`, `CODEX_EXTRA_ARGS`. | AUTOMATED-INTEGRATION (`scripts/agent-evals.sh --help \| grep -q -- '--provider'` AND `\| grep -q AGENT_LLM_PROVIDER`) |
| AC-2 | Codex routing produces 4 SKIP exit 0 (NOT 4 FAIL exit 1) under BOTH absolute and relative `CODEX_BIN`. Both `CODEX_BIN="$(pwd)/tests/evals/mocks/codex-quota.sh" scripts/agent-evals.sh --behavior --provider codex` AND `CODEX_BIN=tests/evals/mocks/codex-quota.sh scripts/agent-evals.sh --behavior --provider codex` must pass. The relative variant is a regression test for the path-normalization fix (eval helpers `cd` into temp dirs before exec). Closes proposal AC-4 / review blocker #1. | AUTOMATED-INTEGRATION |
| AC-3 | `scripts/agent-evals.sh --provider unknown` exits 2 and stderr contains `"Unknown LLM provider: unknown"`. Closes proposal AC-5. | AUTOMATED-INTEGRATION |
| AC-4 | `AGENT_LLM_PROVIDER=codex scripts/agent-evals.sh --fast` runs `tests/evals/codex-harness-fixture.sh` AND skips `tests/evals/plugin-command-load.sh` with reason `"plugin probe is Claude-Code-specific"`. Closes proposal AC-6. | AUTOMATED-INTEGRATION |
| AC-5 | `tests/lib/test_llm_provider.sh` passes both claude branch (PR-1) AND codex branch (new). At least 40 cases run, 0 failures. Closes proposal AC-7 codex extension. | AUTOMATED-UNIT |
| AC-6 | `CODEX_BIN=/nonexistent scripts/agent-evals.sh --behavior --provider codex` exits 0 and stdout contains `"codex CLI not found"` (NOT `"claude CLI not found"`). Closes proposal AC-14. | AUTOMATED-INTEGRATION |
| AC-7 | Env precedence: `AGENT_LLM_PROVIDER=codex CLAUDE_BIN="$(pwd)/tests/evals/mocks/claude-quota.sh" scripts/agent-evals.sh --behavior --provider claude` runs the **claude** path (4 SKIP via Claude regex), proving `--provider claude` overrides `AGENT_LLM_PROVIDER=codex`. Closes proposal AC-15. | AUTOMATED-INTEGRATION |
| AC-8 | `tests/evals/codex-harness-fixture.sh` runs in isolation, exits 0, asserts every `core/skills/<name>/SKILL.md` and every `core/commands/<cmd>.md` produces the expected `.agents/skills/agent-bootstrap/...` SKILL.md in the bootstrapped target. Closes proposal AC-16. | AUTOMATED-INTEGRATION |
| AC-9 | `tests/evals/mocks/{claude-quota,claude-misaligned,codex-quota,codex-auth}.sh` are all checked in, executable (`-rwxr-xr-x`), and produce the expected SKIP/FAIL/SKIP/SKIP behavior when wired into the corresponding regex paths. Closes proposal AC-17. | TYPECHECK + AUTOMATED-INTEGRATION |
| AC-10 | `bash -n` passes on every modified shell file: `scripts/lib/llm_provider.sh`, `scripts/agent-evals.sh`, `tests/evals/plugin-command-load.sh`, `tests/evals/codex-harness-fixture.sh`, `tests/lib/test_llm_provider.sh`, and the 3 new mocks. Closes proposal AC-8 for PR-2. | TYPECHECK |
| AC-11 | `scripts/agent-validate.sh` template self-check still passes (skill count unchanged at 7). Closes proposal AC-9 for PR-2. | AUTOMATED-INTEGRATION |
| AC-12 | `python3 scripts/lib/test_validate_plan.py` still passes 27/27. Closes proposal AC-11 for PR-2. | AUTOMATED-UNIT |
| AC-13 | `scripts/agent-evals.sh --fast` (default provider, no env) exits 0 — no regression in the post-PR-1 default mode. The deterministic set now contains 2 evals (`plugin-command-load.sh` + `codex-harness-fixture.sh`). | AUTOMATED-INTEGRATION |
| AC-14 | `CLAUDE_BIN="$(pwd)/tests/evals/mocks/claude-quota.sh" scripts/agent-evals.sh --behavior` STILL produces 4 SKIP exit 0 (PR-1 AC-6 regression check; PR-2 must not break the claude-default path). | AUTOMATED-INTEGRATION |
| AC-15 | `scripts/agent-validate-plan.sh docs/plans/llm-provider/pr-2/plan.md` exits 0 at plan creation time, before code work begins. After PR-2 lands, the same command produces only EV-003/EV-004 drift (no other findings) — same drift contract as PR-1 AC-9. | AUTOMATED-UNIT |

---

## Existing Behaviors Preserved

Each entry below cites the file and line range that establishes the current behavior. No behavior in this PR is classified `INTENTIONALLY REMOVED` or `BUG FIX`. One ADDITIVE behavior is documented (codex routing).

- **ADDITIVE** — `scripts/agent-evals.sh --fast` deterministic set grows from 1 to 2 evals: `plugin-command-load.sh` (preserved) + `codex-harness-fixture.sh` (new in PR-2). Both are pure filesystem checks; no LLM CLI invoked in either. Default `--fast` exit code is unchanged (still 0 in CI). The fixture is provider-independent and unconditional in the deterministic set so any default-mode CI run gets regression coverage for `bootstrap-request.sh --harness codex` skill copy. Evidence: `scripts/agent-evals.sh:99-103`.
- **PRESERVED** — `scripts/agent-evals.sh --behavior` (no flags) routes to Claude exactly as in PR-1 / 0.4.0. The default value of `AGENT_LLM_PROVIDER` remains `claude`. Evidence: `scripts/agent-evals.sh:104-107`.
- **PRESERVED** — Exit code contract unchanged: `0`=PASS, `77`=SKIP, other=FAIL. Evidence: `scripts/agent-evals.sh:142-154`.
- **PRESERVED** — `CLAUDE_BIN`, `CLAUDE_EXTRA_ARGS`, `EVAL_TIMEOUT` env vars work as before. PR-2 adds `CODEX_BIN`, `CODEX_EXTRA_ARGS` without breaking the Claude variants. Evidence: `tests/evals/test-helpers.sh:5-7`.
- **PRESERVED** — `run_claude`, `skip_if_claude_unavailable`, `is_claude_unavailable_output` shims (PR-1) still pin claude. PR-2 does not touch them. Evidence: `tests/evals/test-helpers.sh:41-59` (claude-pinned skip helper) and `tests/evals/test-helpers.sh:100-108` (run_claude shim).
- **PRESERVED** — Default SKIP wording under provider=claude stays byte-identical to 0.4.0: `SKIP: claude CLI unavailable (quota/auth): <first line>`. The provider-aware SKIP message added in PR-2 substitutes `$provider` only when `$provider != claude`. Evidence: `tests/evals/test-helpers.sh:30-39`.
- **PRESERVED** — `tests/evals/plugin-command-load.sh` continues to PASS under default provider=claude; the new early-SKIP guard only triggers when `provider != claude`. Evidence: `tests/evals/plugin-command-load.sh:11-17`.
- **PRESERVED** — All 27 `test_validate_plan.py` cases still pass. PR-2 does not touch `scripts/lib/validate_plan.py`. Evidence: `scripts/lib/test_validate_plan.py:1-10`.
- **PRESERVED** — `scripts/agent-validate.sh` template self-check still passes; skill count remains 7 (no skill added or removed). Evidence: `scripts/agent-validate.sh:227-232`.
- **PRESERVED** — `bootstrap-request.sh --harness codex --features full` skill-copy behavior is not modified by PR-2; the new `codex-harness-fixture.sh` only **observes** what bootstrap-request already does. Evidence: `scripts/bootstrap-request.sh:385-405`.
- **ADDITIVE** — `--provider codex` (CLI flag) and `AGENT_LLM_PROVIDER=codex` (env) now route every eval through the Codex branch of the registry. Previously these inputs were rejected (registry stub returned `Unknown LLM provider: codex`). This is the entire point of PR-2 and is documented in AC-2 and AC-7. Evidence: `scripts/lib/llm_provider.sh:22-27` (is_known stub) and `scripts/lib/llm_provider.sh:77-82` (run stub).

## Verification

Pre-merge gates, in order. All must pass:

```bash
# Static checks
bash -n scripts/lib/llm_provider.sh
bash -n scripts/agent-evals.sh
bash -n tests/evals/test-helpers.sh
bash -n tests/evals/plugin-command-load.sh
bash -n tests/evals/codex-harness-fixture.sh
bash -n tests/lib/test_llm_provider.sh
bash -n tests/evals/mocks/claude-quota.sh
bash -n tests/evals/mocks/claude-misaligned.sh
bash -n tests/evals/mocks/codex-quota.sh
bash -n tests/evals/mocks/codex-auth.sh

# Mocks executable
test -x tests/evals/mocks/claude-quota.sh
test -x tests/evals/mocks/claude-misaligned.sh
test -x tests/evals/mocks/codex-quota.sh
test -x tests/evals/mocks/codex-auth.sh

# Unit + plan validators
bash tests/lib/test_llm_provider.sh                                         # AC-5
python3 scripts/lib/test_validate_plan.py                                   # AC-12
scripts/agent-validate-plan.sh docs/plans/llm-provider/pr-2/plan.md         # AC-15
scripts/agent-validate.sh                                                   # AC-11

# Help surface
scripts/agent-evals.sh --help | grep -- '--provider'                        # AC-1
scripts/agent-evals.sh --help | grep -E 'AGENT_LLM_PROVIDER|CODEX_BIN'      # AC-1

# Fast mode (default + codex)
scripts/agent-evals.sh --fast                                               # AC-13
AGENT_LLM_PROVIDER=codex scripts/agent-evals.sh --fast                      # AC-4

# Codex behavior path with quota mock - both absolute AND relative CODEX_BIN
CODEX_BIN="$(pwd)/tests/evals/mocks/codex-quota.sh" \
  scripts/agent-evals.sh --behavior --provider codex                        # AC-2 absolute
CODEX_BIN=tests/evals/mocks/codex-quota.sh \
  scripts/agent-evals.sh --behavior --provider codex                        # AC-2 relative (regression for path-normalization fix)

# Unknown provider
scripts/agent-evals.sh --provider unknown 2>&1; rc=$?
[ "$rc" = "2" ]                                                             # AC-3

# Missing-CLI provider-aware
CODEX_BIN=/nonexistent scripts/agent-evals.sh --behavior --provider codex   # AC-6

# Env-vs-CLI precedence
AGENT_LLM_PROVIDER=codex \
CLAUDE_BIN="$(pwd)/tests/evals/mocks/claude-quota.sh" \
  scripts/agent-evals.sh --behavior --provider claude                       # AC-7

# Standalone harness fixture
tests/evals/codex-harness-fixture.sh                                        # AC-8

# PR-1 regression
CLAUDE_BIN="$(pwd)/tests/evals/mocks/claude-quota.sh" \
  scripts/agent-evals.sh --behavior                                         # AC-14

# Migration regression (Claude-only path)
tests/migrations/0.3.0/run.sh
```

The `tests/migrations/0.4.0/run.sh` script is known to fail on baseline `2bb93a0` for unrelated reasons (see PR-1 commit `619bd2d` body). PR-2 does not address it.

---

## Out of Scope (PR-3)

- Documentation updates: `tests/evals/README.md`, `README.md`, `USAGE.md` (PR-3).
- `0.5.0` version bump in `bin/agent-bootstrap`, `scripts/bootstrap-request.sh`, plugin metadata (PR-3).
- `tests/migrations/0.5.0/run.sh` — clean-from-0.4.0 + customized scenarios (PR-3).
- CHANGELOG `0.5.0` entry summarizing PR-1 + PR-2 + PR-3 (PR-3).
- Resolving Q2 (Codex quota regex expansion against real production samples) — tracked as `Q2-followup.md` per the parent proposal.

---

## Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Codex quota regex misses a real production error string and a quota-exhausted run FAILs instead of SKIPs. | Q2-followup.md tracks the gap. PR-2 ships `codex-quota.sh` and `codex-auth.sh` mocks that exercise the regex against assumed strings. New variants from production CI will be added incrementally to both regex and mocks. |
| `--sandbox workspace-write` opens too much surface for security-sensitive users. | Documented override: `CODEX_EXTRA_ARGS="--sandbox read-only"` placed before the prompt. AC-1 covers visibility in `--help`. |
| `AGENT_LLM_PROVIDER=codex` accidentally leaked into a Claude-pinned eval (`plugin-command-load.sh`). | New early SKIP guard (Plan §3) means the eval bails before invoking the Claude bin. AC-4 verifies the SKIP wording. |
| `codex-harness-fixture.sh` becomes stale if `core/skills/` or `core/commands/` evolves. | Fixture computes the expected list at runtime from the directory contents, not from a hard-coded list. AC-8 verifies it passes against the current tree (7 skills + 9 commands = 16 SKILL.md files). |
| Provider-aware SKIP wording change breaks downstream automation that grepped for the literal string `"claude CLI unavailable"`. | The wording change only triggers when `provider != claude`. Default provider (claude) preserves the byte-identical 0.4.0 string. AC-14 verifies. |
| Bash 3 compat (macOS default shell). | Same constraint as PR-1; only `case` + `printf` + plain `[ ... ]`. AC-10 catches regressions. |
