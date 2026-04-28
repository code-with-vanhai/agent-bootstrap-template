# Plan: LLM Provider Abstraction (Codex + Claude switchable)

**Status:** Revision 3.1 — **APPROVED** for proceeding to formal PR-1 plan (3 nits applied: AC-13 ripgrep alternation, Q1 sandbox flag, 6-eval row mentions both helpers)
**Date:** 2026-04-27
**Author:** Cascade
**Target release:** `0.5.0` (semver minor; surface change but additive)
**Document type:** *Discussion proposal in `docs/`*, not a formal grounded-plan artifact under `.agent/runs/`. `scripts/agent-validate-plan.sh` is intentionally **not** applied here; evidence blocks are illustrative for discussion only. Formal plans for each implementation PR will live under `.agent/runs/llm-provider/<pr-id>/plan.md` and will pass the validator.

## Revision History

- **v1 (2026-04-27 14:02)** — Initial draft.
- **v2 (2026-04-27 14:11)** — Review findings addressed: migrate evals to `run_llm` in PR-1 (was PR-3); explicit Codex `exec` invocation; provider-aware missing-CLI in runner; deterministic Codex fixture eval; README/USAGE in scope; project-profile.template.md removed from migration; conservative Codex quota regex with documented gap.
- **v3 (2026-04-27 14:21)** — v2 review fixes: also migrate `skip_if_claude_unavailable` → `skip_if_llm_unavailable` (review #1); removed stale project-profile config paragraph (review #2); reframed `--fast` semantics so adding `codex-harness-fixture.sh` is documented as additive, not a PRESERVED behavior change (review #3); refreshed stale Codex section (review #4); switched `/tmp/fake*` to `tests/evals/mocks/*` in Verification (review #5); AC-13 grep now excludes `test-helpers.sh` and covers both helpers (review #6); added Codex sandbox decision — invoke with `--sandbox workspace-write` so integration evals can mutate temp repos (review #7); registry snippet labeled final-state with PR-1 partial-state staging note (review #8).

---

## Goal

Make the agent-bootstrap-template's **internal eval driver** provider-agnostic so a user can choose between **Claude CLI** and **Codex CLI** (and add more providers later) with a single setting, without rewriting eval scripts.

Out of scope for this plan: harness adapter generation (`bootstrap-request.sh --harness claude|codex|...`) is already implemented and working; we will not touch it except to align documentation.

---

## Why Now

1. The 4 LLM-driven behavior evals are flaky on Claude and currently advisory. Being able to dogfood them on a second provider gives us cross-provider signal and reduces single-vendor risk.
2. Quota for Claude CLI is finite per 5h block. If a contributor has Codex credits but not Claude credits (or vice versa), they cannot run behavior evals today.
3. We just hardened the eval runner with a SKIP/FAIL classifier and quota-detection helper. The right time to generalize that helper is now, while the abstraction surface is small.
4. The user explicitly requested this in the Apr 26 task list.

---

## Two Distinct "LLM provider" Surfaces in the Repo

This plan only touches **Surface B**. Surface A is already done.

### Surface A — Harness target (NOT in scope)

`scripts/bootstrap-request.sh --harness <name>` generates harness-specific
adapter files in **downstream** repos.

<!-- current-code path=scripts/bootstrap-request.sh lines=97-100 ref=2bb93a0 region_sha256=PLACEHOLDER -->
```bash
case "$harness" in
  generic|codex|claude|cursor|copilot|gemini) ;;
  *) die "--harness must be generic, codex, claude, cursor, copilot, or gemini" ;;
esac
```
<!-- /current-code -->

Codex is already a first-class harness with dedicated branches for
`copy_skills` (`.agents/skills/agent-bootstrap/`) and
`copy_codex_command_skills` (Codex wrapper SKILL.md per command). No work
required here.

### Surface B — Internal eval driver (THIS PLAN)

`tests/evals/test-helpers.sh::run_claude` and `tests/evals/plugin-command-load.sh`
invoke the Claude CLI directly to grade prompts/role files.

<!-- current-code path=tests/evals/test-helpers.sh lines=67-86 ref=2bb93a0 region_sha256=PLACEHOLDER -->
```bash
run_claude() {
  prompt="$1"
  workdir="${2:-$PWD}"

  if command -v timeout >/dev/null 2>&1; then
    if [ -n "${CLAUDE_EXTRA_ARGS:-}" ]; then
      # shellcheck disable=SC2086
      (cd "$workdir" && timeout "$EVAL_TIMEOUT" "$CLAUDE_BIN" -p "$prompt" $CLAUDE_EXTRA_ARGS)
    else
      (cd "$workdir" && timeout "$EVAL_TIMEOUT" "$CLAUDE_BIN" -p "$prompt")
    fi
  else
    if [ -n "${CLAUDE_EXTRA_ARGS:-}" ]; then
      # shellcheck disable=SC2086
      (cd "$workdir" && "$CLAUDE_BIN" -p "$prompt" $CLAUDE_EXTRA_ARGS)
    else
      (cd "$workdir" && "$CLAUDE_BIN" -p "$prompt")
    fi
  fi
}
```
<!-- /current-code -->

Surface B is currently bound to Claude semantics: `-p <prompt>` invocation,
and the quota-detection regex in `is_claude_unavailable_output` recognizes
only Claude CLI error strings.

---

## Affected Files (Surface B only)

| File | PR | Touch type | Why |
|---|---|---|---|
| `scripts/lib/llm_provider.sh` | PR-1 | NEW | Single source of truth for provider registry. Per-provider data + invoke function + quota regex. Sourced by `test-helpers.sh` and `agent-evals.sh`. |
| `tests/evals/test-helpers.sh` | PR-1 | Refactor | Add `run_llm` that dispatches via registry. `run_claude` retained as thin shim that calls `run_llm` with `provider=claude` (back-compat). `is_claude_unavailable_output` becomes a thin shim around `llm_provider_is_unavailable claude`. |
| `tests/evals/verify-before-claim.sh`, `root-cause-first.sh`, `no-invented-gates.sh`, `plan-grounding.sh`, `bootstrap-pending-completion.sh`, `no-unrelated-changes.sh` | PR-1 | Migrate | Replace `run_claude` → `run_llm` AND `skip_if_claude_unavailable` → `skip_if_llm_unavailable` (both helpers). No-op when provider=claude. Required so `--provider codex` actually routes to Codex AND so Codex auth/quota strings SKIP cleanly instead of FAILing through the Claude regex (review blockers #1 v1 + #1 v2). |
| `tests/lib/test_llm_provider.sh` | PR-1 | NEW | Bash unit tests for the registry: bin resolution + env override, default bin, unknown provider error, quota-detect per provider. |
| `scripts/agent-evals.sh` | PR-2 | Add CLI flag + provider-aware missing-CLI | New `--provider <name>` flag; honors `AGENT_LLM_PROVIDER`; default `claude`. Provider-aware bin lookup and skip wording (no Claude-specific strings when provider=codex). Update `--help`. |
| `tests/evals/plugin-command-load.sh` | PR-2 | Conditional | `--plugin-dir`/`--debug-file`/`--print` are Claude-Code-specific; SKIP cleanly with reason `"plugin probe is Claude-Code-specific"` when `provider != claude`. |
| `tests/evals/codex-harness-fixture.sh` | PR-2 | NEW | Deterministic Codex fast-mode eval. Runs `bootstrap-request.sh --harness codex --features full --target <tmp>` and asserts the expected `.agents/skills/agent-bootstrap/<skill>/SKILL.md` files are generated. **No real Codex CLI invocation — pure fs check.** Closes Q5. |
| `tests/evals/mocks/claude-quota.sh` | PR-2 | NEW | Stable check-in of the ad-hoc `/tmp/fakequota.sh` Claude quota mock. |
| `tests/evals/mocks/claude-misaligned.sh` | PR-2 | NEW | Stable Claude mock that emits non-matching positive output (formerly `/tmp/fakeclaude.sh`). |
| `tests/evals/mocks/codex-quota.sh` | PR-2 | NEW | Codex CLI quota-error mock (one or two known error variants from Q2; conservative). |
| `tests/evals/mocks/codex-auth.sh` | PR-2 | NEW | Codex CLI auth/login-required mock. |
| `tests/evals/README.md` | PR-3 | Doc | Document `AGENT_LLM_PROVIDER`, `CODEX_BIN`, per-provider env vars, provider-portable vs provider-specific eval matrix. |
| `README.md` | PR-3 | Doc | Replace Claude-only eval references with provider-agnostic wording; link to `tests/evals/README.md` for matrix. |
| `USAGE.md` | PR-3 | Doc | Update fast-eval list (currently stale), add `--provider` examples, document env precedence. |
| `CHANGELOG.md` | PR-3 | Add entry | `0.5.0` entry. |
| `scripts/bootstrap-request.sh` | PR-3 | Bump version | `template_version="0.5.0"`. |
| `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json` | PR-3 | Bump version | Plugin metadata `"version": "0.5.0"`. |
| `core/migrations/0.5.0/migration.json` | PR-3 | NEW | Empty migration manifest with `from_versions: ["0.4.0"]`. Surface B does not modify any generated downstream file — migration is a deliberate no-op version bump. |
| `tests/migrations/0.5.0/run.sh` | PR-3 | NEW | Regression test: clean-from-0.4.0, customized-rulebase/gates/roles, idempotency. |

**Explicit non-changes (response to review #2):**
- `core/project-profile.template.md` — *not modified*. Earlier draft proposed adding an "LLM Eval Provider" line, but that would make the migration non-no-op and risk overwriting downstream customizations. Provider configuration is a CI/env concern, not a project-profile field. Documentation of the env var lives in `tests/evals/README.md` and `USAGE.md` only.

---

## Provider Registry Design

A new `scripts/lib/llm_provider.sh` exposes 3 functions consumed by both
`test-helpers.sh` and `agent-evals.sh`:

```bash
# Returns 0 if provider is registered, 1 otherwise.
llm_provider_is_known()        # arg1: provider_name

# Prints the bin path that will be invoked. Resolves via:
#   1. <PROVIDER>_BIN env var if set
#   2. provider's default bin name (claude / codex)
# Honors PATH lookup; does NOT verify executability (caller decides).
llm_provider_bin()             # arg1: provider_name

# Invokes the provider with a prompt and returns its stdout/stderr.
# Honors EVAL_TIMEOUT and provider-specific extra args
# (CLAUDE_EXTRA_ARGS, CODEX_EXTRA_ARGS).
llm_provider_run()             # arg1: provider_name, arg2: prompt, arg3: workdir

# Returns 0 if output looks like a quota/auth error for that provider.
llm_provider_is_unavailable()  # arg1: provider_name, arg2: output
```

Internal structure: per-provider **explicit invoke function** (not a string
template — review finding #3) plus per-provider data and quota regex. No
associative arrays to keep bash-3 compat for macOS default shell.

**Snippet status:** the listing below is the **final state at end of PR-2**.
During PR-1 the codex branch in every function returns `1` / prints
`"Unknown LLM provider: codex"` so PR-1 is strictly a Claude-only
refactor. PR-2 adds the codex branch wholesale (registry data, invoke
function, quota regex, and unit-test coverage) in one PR.

```bash
# scripts/lib/llm_provider.sh

llm_provider_is_known() {
  case "$1" in claude|codex) return 0 ;; *) return 1 ;; esac
}

llm_provider_default_bin() {
  case "$1" in
    claude) printf 'claude' ;;
    codex)  printf 'codex' ;;
    *) return 1 ;;
  esac
}

llm_provider_bin() {                 # honors <PROVIDER>_BIN env override
  case "$1" in
    claude) printf '%s' "${CLAUDE_BIN:-claude}" ;;
    codex)  printf '%s' "${CODEX_BIN:-codex}"   ;;
    *) return 1 ;;
  esac
}

# Explicit per-provider invocation. Each function MUST honor EVAL_TIMEOUT
# (when `timeout` is available), the provider's BIN env var, and the
# provider's EXTRA_ARGS env var. Args: $1=prompt, $2=workdir.
_llm_invoke_claude() {
  local prompt="$1" workdir="$2" bin
  bin="$(llm_provider_bin claude)"
  if command -v timeout >/dev/null 2>&1; then
    # shellcheck disable=SC2086
    (cd "$workdir" && timeout "$EVAL_TIMEOUT" "$bin" -p "$prompt" ${CLAUDE_EXTRA_ARGS:-})
  else
    # shellcheck disable=SC2086
    (cd "$workdir" && "$bin" -p "$prompt" ${CLAUDE_EXTRA_ARGS:-})
  fi
}

_llm_invoke_codex() {
  local prompt="$1" workdir="$2" bin
  bin="$(llm_provider_bin codex)"
  # Verified Q1: codex-cli 0.124.0 uses `codex exec [OPTIONS] [PROMPT]`.
  # `--skip-git-repo-check` lets evals run in temp dirs not under a git repo.
  # `--color never` avoids ANSI escapes that confuse assert regexes.
  # `--sandbox workspace-write` is required for integration evals
  # (no-unrelated-changes, bootstrap-pending-completion) which mutate temp
  # repos. Default codex sandbox is read-only; without this flag those
  # evals would always FAIL (review #7). Behavior evals also tolerate
  # workspace-write so we set it unconditionally for the eval driver.
  # CODEX_EXTRA_ARGS is positioned BEFORE the prompt (review #3) so users
  # can override (e.g. tighten to `--sandbox read-only` or pass
  # `--config <key=val>`) without touching the registry.
  if command -v timeout >/dev/null 2>&1; then
    # shellcheck disable=SC2086
    (cd "$workdir" && timeout "$EVAL_TIMEOUT" "$bin" exec --skip-git-repo-check --color never --sandbox workspace-write ${CODEX_EXTRA_ARGS:-} "$prompt")
  else
    # shellcheck disable=SC2086
    (cd "$workdir" && "$bin" exec --skip-git-repo-check --color never --sandbox workspace-write ${CODEX_EXTRA_ARGS:-} "$prompt")
  fi
}

llm_provider_run() {
  case "$1" in
    claude) _llm_invoke_claude "$2" "$3" ;;
    codex)  _llm_invoke_codex  "$2" "$3" ;;
    *) printf 'Unknown LLM provider: %s\n' "$1" >&2; return 2 ;;
  esac
}

# Provider-specific quota / auth / rate-limit detection. Output is matched
# case-insensitively. Conservative on Codex pending Q2 real samples.
llm_provider_is_unavailable() {
  local provider="$1" output="$2"
  case "$provider" in
    claude)
      printf '%s' "$output" | grep -Eiq \
        "(hit your (monthly )?(usage )?limit|usage limit (reached|exceeded)|rate limit (reached|exceeded)|limit.*resets|invalid api key|authentication.*failed|please (log ?in|authenticate)|credit balance is too low|quota exceeded|api error.*(401|403|429))"
      ;;
    codex)
      # Conservative initial set — Q2 still open for verified literal
      # quota strings. Includes generic auth/rate-limit forms documented
      # in OpenAI API error contract (the provider Codex authenticates against).
      printf '%s' "$output" | grep -Eiq \
        "(rate limit|usage limit|quota exceeded|insufficient (credits|quota)|invalid api key|authentication (error|failed)|please (log ?in|sign ?in|authenticate)|http (status )?(401|403|429)|too many requests)"
      ;;
    *) return 1 ;;
  esac
}
```

`run_claude` in `test-helpers.sh` becomes a thin wrapper that delegates to
`llm_provider_run "claude" ...` so existing eval scripts continue to work
unchanged. New evals (or migrated ones) call `run_llm` directly:

```bash
run_llm() {
  prompt="$1"
  workdir="${2:-$PWD}"
  llm_provider_run "${AGENT_LLM_PROVIDER:-claude}" "$prompt" "$workdir"
}
```

---

## User-Facing Configuration

Three layers, in priority order (highest first):

1. **CLI flag**: `scripts/agent-evals.sh --provider claude|codex` (overrides env).
2. **Env var**: `AGENT_LLM_PROVIDER=claude|codex` (settable in CI / shell rc).
3. **Default**: `claude` (preserves current behavior if user does nothing).

Per-provider knobs (each provider reads its own):
- `CLAUDE_BIN`, `CLAUDE_EXTRA_ARGS` (existing — unchanged)
- `CODEX_BIN`, `CODEX_EXTRA_ARGS` (new)

Documentation surfaces (no template-generated file is modified — see review #2):
- `tests/evals/README.md` — authoritative provider matrix, env var precedence,
  and per-provider invocation contract.
- `USAGE.md`, `README.md` — cross-link to `tests/evals/README.md`.

Rationale: `core/project-profile.template.md` is generated downstream;
adding fields there would either break the no-op migration contract or
overwrite team customizations. Provider selection is a CI/env concern,
not a project-profile field.

---

## Provider-Specific Considerations

### Claude (existing)
- Invocation: `claude -p "$prompt"` (already in `run_claude`).
- Quota errors: handled by current `is_claude_unavailable_output` regex.
- Plugin probe (`plugin-command-load.sh`) uses Claude-specific
  `--plugin-dir`/`--debug-file`/`--print` flags. **Stays Claude-only.**

### Codex (new)
- Invocation: `codex exec --skip-git-repo-check --color never --sandbox workspace-write $CODEX_EXTRA_ARGS "$prompt"` (Q1 closed; verified `codex-cli 0.124.0`).
- Sandbox: `workspace-write` set by default in the eval driver because
  integration evals mutate temp repos. Users tightening the sandbox can
  override via `CODEX_EXTRA_ARGS="--sandbox read-only"` (review #7). The
  override is positional-aware: extra args go before the prompt.
- Quota / auth errors: conservative regex shipped (Q2 partially open).
  See Q2 status below for documented gap and mock coverage.
- No plugin equivalent. `plugin-command-load.sh` SKIPs on `provider=codex`
  with reason "plugin probe is Claude-Code-specific". Replacement
  deterministic check: `tests/evals/codex-harness-fixture.sh` (filesystem-only).
- Codex natively reads `AGENTS.md`, so existing eval prompts that
  reference `AGENTS.md` / `.agent/rulebase.md` work unchanged.
- Provider-aware skip helper: evals call `skip_if_llm_unavailable`
  (added in PR-1 alongside `run_llm`) which dispatches to
  `llm_provider_is_unavailable "$AGENT_LLM_PROVIDER"`. Without this,
  Codex auth/quota strings would not match the Claude regex and AC-4
  would FAIL instead of SKIP (review #1).

---

## Acceptance Criteria

| ID | Criterion | Verification Method | Gating PR |
|---|---|---|---|
| AC-1 | `scripts/agent-evals.sh --help` lists `--provider` and documents `AGENT_LLM_PROVIDER` env var. | MANUAL | PR-2 |
| AC-2 | `scripts/agent-evals.sh --fast` exits 0 with no provider set (deterministic mode runs without LLM). | AUTOMATED-INTEGRATION | PR-1 |
| AC-3 | `scripts/agent-evals.sh --behavior --provider claude` produces identical PASS/SKIP/FAIL behavior to `0.4.0`'s `--behavior` on equal input. Verified by comparing against pre-PR-1 baseline using fakequota / fakeclaude mocks. | AUTOMATED-INTEGRATION | PR-1 |
| AC-4 | `scripts/agent-evals.sh --behavior --provider codex` actually invokes `_llm_invoke_codex` (verified by `CODEX_BIN=tests/evals/mocks/codex-quota.sh` producing 4 SKIP exit 0; not 4 FAIL exit 1). Closes review blocker #1. | AUTOMATED-INTEGRATION | PR-2 |
| AC-5 | `scripts/agent-evals.sh --provider unknown` rejects with exit 2 and prints `"Unknown LLM provider: unknown"` (or equivalent) including help suggestion. | AUTOMATED-INTEGRATION | PR-2 |
| AC-6 | `tests/evals/plugin-command-load.sh` SKIPs (exit 77) with reason `"plugin probe is Claude-Code-specific"` when `AGENT_LLM_PROVIDER=codex`. | AUTOMATED-INTEGRATION | PR-2 |
| AC-7 | `tests/lib/test_llm_provider.sh` passes: bin env override (CLAUDE_BIN/CODEX_BIN), default bin, `llm_provider_is_known` known/unknown, quota-detect per provider on known sample strings, EXTRA_ARGS placement (Codex EXTRA_ARGS appears before prompt — review #3). | AUTOMATED-UNIT | PR-1 (claude branch); extended PR-2 (codex branch) |
| AC-8 | `bash -n` syntax check passes on every touched `*.sh` file. | TYPECHECK | PR-1, PR-2, PR-3 |
| AC-9 | `scripts/agent-validate.sh` passes throughout. | AUTOMATED-INTEGRATION | PR-1, PR-2, PR-3 |
| AC-10 | `tests/migrations/0.5.0/run.sh` passes: clean-from-0.4.0, customized-rulebase, customized-gates, customized-roles, idempotency. | AUTOMATED-INTEGRATION | PR-3 |
| AC-11 | `python3 scripts/lib/test_validate_plan.py` still passes 27/27. | AUTOMATED-UNIT | PR-1, PR-2, PR-3 |
| AC-12 | CHANGELOG `0.5.0` entry documents: provider abstraction, new env vars (`AGENT_LLM_PROVIDER`, `CODEX_BIN`, `CODEX_EXTRA_ARGS`), provider-portable vs Claude-specific eval matrix, no-op migration rationale. | MANUAL | PR-3 |
| AC-13 | All 6 provider-portable evals are migrated off Claude-specific helpers. Verified by `! rg -l '\b(run_claude|skip_if_claude_unavailable)\b' tests/evals -g '!test-helpers.sh' -g '!plugin-command-load.sh'`. `test-helpers.sh` is excluded because it still defines both as back-compat shims; `plugin-command-load.sh` is excluded because it is Claude-Code-specific by design. Covers both `run_claude` AND `skip_if_claude_unavailable` (review #1, #6). | TYPECHECK | PR-1 |
| AC-14 | Provider-aware missing-CLI handling: `CODEX_BIN=/nonexistent scripts/agent-evals.sh --behavior --provider codex` SKIPs with message `"codex CLI not found"` (NOT `"claude CLI not found"`); exit 0 if `--skip-on-missing-cli` (default). | AUTOMATED-INTEGRATION | PR-2 |
| AC-15 | Env precedence: `AGENT_LLM_PROVIDER=codex` is overridden by explicit `--provider claude`. Verified by mock-CLI integration test. | AUTOMATED-INTEGRATION | PR-2 |
| AC-16 | `tests/evals/codex-harness-fixture.sh` (deterministic, no real Codex) passes: runs `bootstrap-request.sh --harness codex --features full --target <tmp>` and asserts expected `.agents/skills/agent-bootstrap/<skill>/SKILL.md` files exist. Closes Q5. | AUTOMATED-INTEGRATION | PR-2 |
| AC-17 | `tests/evals/mocks/{claude-quota,claude-misaligned,codex-quota,codex-auth}.sh` are checked in, executable, and stable (no `/tmp` ad-hoc generation in test code). Closes Q3. | TYPECHECK + AUTOMATED-INTEGRATION | PR-2 |

---

## Existing Behaviors Preserved

Each item below is a **PRESERVED** behavior unless explicitly classified.
New classification used in this plan: **ADDITIVE** — a documented behavior
change that does not regress prior contracts on the existing default.

| # | Behavior | Classification | Evidence |
|---|---|---|---|
| 1 | `scripts/agent-evals.sh --fast` runs only deterministic, no-real-LLM evals and exits 0. With `provider=claude` (default) the fast set is `plugin-command-load.sh` (current behavior preserved). With `provider=codex` the fast set is `codex-harness-fixture.sh` and `plugin-command-load.sh` SKIPs. | ADDITIVE — documented behavior change (review #3): the fast eval list is now provider-aware, but the contract ("`--fast` is deterministic & token-free, exits 0 in CI") is preserved for both providers. CHANGELOG must call out the provider-aware fast set explicitly. | `scripts/agent-evals.sh:99-103` (case fast) |
| 1b | `scripts/agent-evals.sh --fast` with no provider override (default `claude`) runs `plugin-command-load.sh` and exits 0 — same behavior as 0.4.0. | PRESERVED | `scripts/agent-evals.sh:99-103` |
| 2 | `scripts/agent-evals.sh --behavior` runs the 4 LLM evals and treats failures as advisory. | PRESERVED | `scripts/agent-evals.sh:104-107,157-163` |
| 3 | `scripts/agent-evals.sh --integration` runs deterministic + behavior + integration sets. | PRESERVED | `scripts/agent-evals.sh:108-111` |
| 4 | Exit code contract: `0`=PASS, `77`=SKIP, other=FAIL, runner exit `1` aggregates failures. | PRESERVED | `scripts/agent-evals.sh:142-154,157-163` |
| 5 | `CLAUDE_BIN` env var continues to work as the bin override for Claude. | PRESERVED | `tests/evals/test-helpers.sh:5` and `run_claude` shim |
| 6 | `is_claude_unavailable_output` regex still recognizes the Claude error strings used today (no narrowing). | PRESERVED | `tests/evals/test-helpers.sh:22-26` — regex moved into provider registry but kept verbatim for `provider=claude` |
| 7 | `tests/evals/plugin-command-load.sh` continues to PASS on Claude with real CLI when plugin commands load. | PRESERVED | `tests/evals/plugin-command-load.sh:56-58` |
| 8 | `run_claude` function continues to exist and work for any external caller relying on it. | PRESERVED via shim — `run_claude` becomes a wrapper around `llm_provider_run "claude" ...`. PR-1 also migrates the 6 in-tree callers to `run_llm` (review #1) but the shim remains for any out-of-tree consumers. |
| 9 | `scripts/agent-validate.sh` template self-check passes. | PRESERVED — new lib file added but no skill count change; verified by AC-9. |
| 10 | All 27 plan validator unit tests pass. | PRESERVED — Surface B work does not touch `scripts/lib/validate_plan.py`; verified by AC-11. |
| 11 | Migration framework: downstream repo at 0.4.0 can sync to 0.5.0 with **zero** generated file changes. | PRESERVED — `core/project-profile.template.md` deliberately not modified (review #2). Verified by AC-10's clean-from-0.4.0 scenario expecting no file diffs in `.agent/`. |
| 12 | Existing `is_claude_unavailable_output` regex is not narrowed; all current matches still match. | PRESERVED — regex copied verbatim into `_llm_provider_is_unavailable claude` branch. Verified by AC-7 on known sample strings (`"You've hit your limit · resets ..."`, `"credit balance is too low"`, etc.). |

No behaviors are classified as `INTENTIONALLY REMOVED` or `BUG FIX` in
this plan. One behavior (#1) is `ADDITIVE` because the fast eval list
becomes provider-aware (review #3).

---

## Verification

Run, in order:

```bash
# Deterministic gates (must all pass before merge):
bash -n scripts/agent-evals.sh
bash -n scripts/lib/llm_provider.sh
bash -n tests/evals/test-helpers.sh
bash tests/lib/test_llm_provider.sh                         # AC-7, AC-8
scripts/agent-validate.sh                                   # AC-9
python3 scripts/lib/test_validate_plan.py                   # AC-11
tests/migrations/0.3.0/run.sh
tests/migrations/0.4.0/run.sh
tests/migrations/0.5.0/run.sh                               # AC-10

# Provider-routing integration tests (checked-in mocks, no real quota burn):
scripts/agent-evals.sh --fast                                                                          # AC-2
scripts/agent-evals.sh --provider unknown ; [ $? -eq 2 ]                                               # AC-5
CLAUDE_BIN=tests/evals/mocks/claude-quota.sh      scripts/agent-evals.sh --behavior --provider claude  # AC-3 (4 SKIP, exit 0)
CLAUDE_BIN=tests/evals/mocks/claude-misaligned.sh scripts/agent-evals.sh --behavior --provider claude  # 4 FAIL + advisory, exit 1
CODEX_BIN=tests/evals/mocks/codex-quota.sh        scripts/agent-evals.sh --behavior --provider codex   # AC-4 (4 SKIP, exit 0)
CODEX_BIN=tests/evals/mocks/codex-auth.sh         scripts/agent-evals.sh --behavior --provider codex   # AC-4 (4 SKIP, exit 0)
AGENT_LLM_PROVIDER=codex scripts/agent-evals.sh --fast                                                  # AC-6 + AC-16 (plugin SKIP, codex-harness-fixture PASS)
AGENT_LLM_PROVIDER=codex scripts/agent-evals.sh --provider claude --behavior                            # AC-15 (flag overrides env)
CODEX_BIN=/nonexistent scripts/agent-evals.sh --behavior --provider codex                               # AC-14 ("codex CLI not found", exit 0)

# Optional, advisory (consumes real quota — only run after credits reset):
scripts/agent-evals.sh --behavior --provider claude          # known to FAIL; advisory
scripts/agent-evals.sh --behavior --provider codex           # new signal
```

Mock CLI scripts checked in under `tests/evals/mocks/` (review #5, Q3):
- `claude-quota.sh` — emits a Claude quota-exhausted error string.
- `claude-misaligned.sh` — emits a positive-but-non-matching response (covers FAIL path without quota classifier).
- `codex-quota.sh` — emits a Codex/OpenAI rate-limit / quota error string.
- `codex-auth.sh` — emits a Codex login-required / invalid-key error string.

All four are tracked in git so contributors do not need any setup step
before running the verification commands above.

---

## Implementation Order (sequential PRs)

PR scope revised after review (blocker #1 moves migration of 6 evals from PR-3 → PR-1). Each PR must pass deterministic gates standalone.

**PR-1 — Provider registry + `run_llm` + `skip_if_llm_unavailable` + migrate 6 evals (Claude-only routing)**
- Add `scripts/lib/llm_provider.sh` with claude branch only. Codex branch in every function returns `1` / `"Unknown LLM provider: codex"` so the registry is structurally complete but only claude works.
- Add `run_llm` to `tests/evals/test-helpers.sh`. Keep `run_claude` as back-compat shim that calls `run_llm "claude" ...`.
- Add `skip_if_llm_unavailable` (review #1) that dispatches to `llm_provider_is_unavailable "$AGENT_LLM_PROVIDER"`. Keep `skip_if_claude_unavailable` as a back-compat shim.
- Move quota-regex into `_llm_provider_is_unavailable claude` and reduce `is_claude_unavailable_output` to a shim.
- **Migrate all 6 provider-portable evals** from `run_claude` → `run_llm` AND from `skip_if_claude_unavailable` → `skip_if_llm_unavailable` (verify-before-claim, root-cause-first, no-invented-gates, plan-grounding, bootstrap-pending-completion, no-unrelated-changes). Closes review blocker #1.
- Add `tests/lib/test_llm_provider.sh` (claude branch coverage; codex tests stubbed/skipped).
- Acceptance criteria gated to PR-1: AC-2, AC-3, AC-7 (claude), AC-8, AC-9, AC-11, AC-13.
- Net behavior change: zero. `provider=codex` would still error out with "Unknown LLM provider: codex" — PR-2 is required for any Codex routing.

**PR-2 — Codex provider + `--provider` flag + provider-aware runner + deterministic Codex eval**
- Extend `llm_provider.sh` codex branch (Q1 closed: `codex exec`).
- Add `--provider` flag + `AGENT_LLM_PROVIDER` env to `scripts/agent-evals.sh`. Provider-aware bin lookup, missing-CLI message, skip wording.
- Make `tests/evals/plugin-command-load.sh` SKIP on `provider != claude`.
- Add `tests/evals/codex-harness-fixture.sh` (deterministic, no real Codex CLI — closes Q5).
- Add `tests/evals/mocks/{claude-quota,claude-misaligned,codex-quota,codex-auth}.sh` (closes Q3).
- Extend `tests/lib/test_llm_provider.sh` with codex coverage (mock-CLI based; conservative regex per Q2).
- Acceptance criteria gated to PR-2: AC-1, AC-4, AC-5, AC-6, AC-7 (codex), AC-14, AC-15, AC-16, AC-17.
- Q2 status: ship conservative regex covering generic OpenAI-style errors. Document gap in `tests/evals/README.md` and PR description; expand regex when real samples surface.

**PR-3 — Docs + version bump + migration**
- Update `tests/evals/README.md` (provider matrix), `README.md`, `USAGE.md` (review #6).
- `core/migrations/0.5.0/migration.json` (no-op, `from_versions: ["0.4.0"]`). `core/project-profile.template.md` deliberately unchanged (review #2).
- `tests/migrations/0.5.0/run.sh`.
- Bump `bootstrap-request.sh` `template_version`, `plugin.json`, `marketplace.json`.
- `CHANGELOG.md` entry.
- Tag `v0.5.0`.
- Acceptance criteria gated to PR-3: AC-10, AC-12, plus all earlier ACs continue to hold.

---

## Open Questions Status

### Q1. Codex CLI invocation syntax — **CLOSED**

Verified `codex-cli 0.124.0` uses `codex exec [OPTIONS] [PROMPT]`. `codex -p` is the `--profile` flag, not prompt. Final invocation:

```bash
codex exec --skip-git-repo-check --color never --sandbox workspace-write $CODEX_EXTRA_ARGS "$prompt"
```

`CODEX_EXTRA_ARGS` is positioned **before** the prompt (review #3). `--color never` strips ANSI escapes that would otherwise confuse `assert_contains` regexes. `--skip-git-repo-check` allows evals to run in temp dirs. `--sandbox workspace-write` is required for integration evals that mutate temp repos (review #7); users can tighten via `CODEX_EXTRA_ARGS="--sandbox read-only"`.

### Q2. Codex quota / auth error strings — **PARTIALLY OPEN**

Sandbox runs only produced infra errors (`Operation not permitted`, `stream disconnected`, `Could not resolve host`) — not real 401/403/429/quota responses. Decision: ship a **conservative regex** in PR-2 covering documented OpenAI API error contract terms (`rate limit`, `quota exceeded`, `insufficient credits`, `invalid api key`, `http 401|403|429`, `too many requests`) and add a `Q2-followup.md` task to expand the regex when first real samples surface in production CI.

**Risk if regex misses:** a Codex quota error would FAIL evals as a behavior regression (same failure mode Claude evals had before the SKIP classifier). Mitigation: PR-2 adds `tests/evals/mocks/codex-quota.sh` and `codex-auth.sh` with the assumed strings, so the test suite exercises the regex against known forms; any new variant found in production gets added to both the regex and a new mock.

### Q3. Mock-CLI policy — **CLOSED**

Check in mocks under `tests/evals/mocks/`. Deterministic, reviewable, no setup step.

### Q4. Default provider — **CLOSED**

Default stays `claude`. Existing CI continues green by default. `--provider` is opt-in.

### Q5. Codex deterministic eval — **CLOSED**

Add `tests/evals/codex-harness-fixture.sh` (PR-2): runs `bootstrap-request.sh --harness codex --features full --target <tmp>` and asserts the expected Codex skill files (`.agents/skills/agent-bootstrap/<skill>/SKILL.md`) are generated. Filesystem-only assertions, no Codex CLI invocation. This gives Codex-only contributors a non-empty `--fast` set when paired with `AGENT_LLM_PROVIDER=codex` (plugin-command-load SKIPs, codex-harness-fixture PASSes).

---

## Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Codex CLI invocation differs from assumption → behavior evals all FAIL on `--provider codex`. | PR-2 is gated on Q1 answer. Mock CLIs verify routing without real Codex calls. |
| Quota-detection regex for Codex misses some error variants → false FAIL after credits exhausted. | Same mitigation as Claude: ship initial regex, watch first month of CI runs, broaden as needed. Add a `tests/evals/mocks/codex-*.sh` for each known error class so the regex has a regression test. |
| `run_claude` shim diverges from new `run_llm` over time. | All 6 in-tree evals are migrated to `run_llm` in PR-1 (review blocker #1). The shim is marked deprecated in a `test-helpers.sh` comment but kept for any out-of-tree consumers. The shim can be removed in 0.6.0 once we're confident no external script depends on it. |
| Downstream repos that hard-code `CLAUDE_BIN` in CI continue to work? | Yes — `CLAUDE_BIN` is still read by the claude provider entry. Verified by AC-3 and PR-1's "no behavior change" gate. |
| Bash 3 compat (macOS default shell). | Provider registry uses case statements only, no associative arrays. Verified by `bash -n` and explicit shellcheck on `scripts/lib/llm_provider.sh`. |

---

## Non-Goals

- Adding more providers beyond Claude and Codex in this release.
- Changing harness adapters (Surface A) — already done.
- Migrating existing eval prompts to be "provider-neutral" beyond what's
  needed to run on both. Prompts continue to reference `AGENTS.md` /
  `.agent/rulebase.md` which both providers respect natively.
- Auto-detecting the provider from environment. Explicit selection only.
- Supporting parallel multi-provider runs in one invocation (e.g.
  `--provider claude,codex`). Out of scope; user can run twice.

---

## Out of Plan: 0.3.2 Tag Hygiene

Noted but not addressed here: `v0.3.2` tag currently points to commit
`499eb16 "WIP: 0.3.2 + 0.4.0 grounded planning"` which contains both 0.3.2
and 0.4.0 changes. This is a release-history defect, not a behavior bug.
If you want a clean tag, that's a separate plan (would require a forced
re-tag and a coordination notice for downstream consumers).

---

## Review Checklist (for human reviewer — v3 re-review)

Resolved in v3 (this revision — addressing v2 review findings):
- [x] **v2 #1** also migrate `skip_if_claude_unavailable` → `skip_if_llm_unavailable`; AC-13 covers both helpers.
- [x] **v2 #2** stale `project-profile.md` config paragraph removed; doc surfaces are README/USAGE/tests/evals/README only.
- [x] **v2 #3** Existing Behavior #1 reframed: provider-aware fast set is `ADDITIVE`; behavior #1b preserves the default-claude contract.
- [x] **v2 #4** Codex section refreshed: invocation now lists final `codex exec ...` form, sandbox decision documented.
- [x] **v2 #5** Verification commands switched from `/tmp/fake*` to `tests/evals/mocks/*`.
- [x] **v2 #6** AC-13 grep excludes `test-helpers.sh` and `plugin-command-load.sh`; covers both `run_claude` and `skip_if_claude_unavailable`.
- [x] **v2 #7** Codex sandbox decision: `--sandbox workspace-write` set by default in `_llm_invoke_codex`; users override via `CODEX_EXTRA_ARGS`.
- [x] **v2 #8** Registry snippet labeled "final state at end of PR-2"; PR-1 description explicitly states codex branch returns unknown.

Resolved earlier (v2):
- [x] Surface A vs Surface B distinction.
- [x] Q1 closed (`codex exec`, EXTRA_ARGS before prompt).
- [x] Q3 closed (mocks checked in under `tests/evals/mocks/`).
- [x] Q4 closed (default `claude`).
- [x] Q5 closed (`codex-harness-fixture.sh`, no real Codex CLI).
- [x] Blocker #1 closed (6-eval migration moved to PR-1).
- [x] `project-profile.template.md` not modified; migration stays no-op.
- [x] Codex invocation is an explicit function, EXTRA_ARGS before prompt.
- [x] AC-14 covers provider-aware missing-CLI; no Claude wording leak.
- [x] `README.md` + `USAGE.md` added to PR-3 scope.
- [x] Discussion proposal label; `.agent/runs/` formal plan promised before PR-1 code.

Still need your sign-off:
- [ ] Q2 strategy acceptable (ship conservative regex + mocks, document gap, expand later).
- [ ] AC-1..AC-17 coverage acceptable.
- [ ] Existing Behaviors 1–12 (with #1 ADDITIVE + #1b PRESERVED) list complete.
- [ ] PR sequencing PR-1 → PR-2 → PR-3 with PR-1 doing 6-eval migration + `skip_if_llm_unavailable` is acceptable.
- [ ] Codex sandbox default `workspace-write` is acceptable (vs read-only with opt-in).
- [ ] Target version `0.5.0` is correct.

After approval, I will draft a formal grounded plan under
`.agent/runs/llm-provider/pr-1/plan.md` (with real evidence-block hashes
that pass `agent-validate-plan.sh`) before writing any code. The formal
plan will reference this document for context but stand alone for
implementation review.

---

**Note on evidence-block placeholder hashes.** The two `<!-- current-code -->`
blocks above use `region_sha256=PLACEHOLDER`. They are illustrative for plan
discussion only; this proposal is not run through `agent-validate-plan.sh`.
Real plan files inside `.agent/runs/` would have full SHA-256 hashes
computed by the planner role per the 0.4.0 grounded-planning protocol.
