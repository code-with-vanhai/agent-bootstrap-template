# PR-1 Plan: Provider Registry + `run_llm` + `skip_if_llm_unavailable` + Eval Migration

**Status:** Draft
**Date:** 2026-04-27
**Parent proposal:** `docs/2026-04-27-llm-provider-abstraction-proposal.md` (revision 3.1, approved)
**Plan location note:** Stored under `docs/plans/llm-provider/pr-1/plan.md` rather than `.agent/runs/llm-provider/pr-1/plan.md` because `scripts/agent-validate.sh:244` treats the existence of `.agent/` as "this is a bootstrapped downstream repo" and demands the full bootstrap skeleton. The `.agent/runs/<slug>/` convention is for DOWNSTREAM repos that have run the bootstrap; template-repo dogfooding plans live under `docs/plans/`. The validator (`scripts/agent-validate-plan.sh`) accepts any path argument so this is a path-storage choice only.
**Scope:** PR-1 of 3 in the 0.5.0 LLM provider abstraction series. Claude-only routing; net behavior change is zero.
**Ref commit:** `2bb93a0`

---

## Goal

Introduce a provider-registry seam (`scripts/lib/llm_provider.sh`) and provider-agnostic eval helpers (`run_llm`, `skip_if_llm_unavailable`) without changing any runtime behavior. All 6 provider-portable eval scripts are migrated off Claude-specific helpers so PR-2 can plug in Codex routing without re-touching them.

This PR is intentionally a **refactor with zero observable behavior delta**. The codex branch in every registry function returns "Unknown LLM provider: codex" until PR-2.

---

## Context (Grounding)

The current eval driver is hard-coded to the Claude CLI in three places inside `tests/evals/test-helpers.sh`:

### 1. Claude-specific quota/auth detector

<!-- current-code path=tests/evals/test-helpers.sh lines=22-26 ref=2bb93a0 region_sha256=0875c165455974f74383a82a8b2917a8ce9212b703757101ff87679a45d7b4c1 -->
```bash
is_claude_unavailable_output() {
  output="$1"
  printf '%s' "$output" | grep -Eiq \
    "(hit your (monthly )?(usage )?limit|usage limit (reached|exceeded)|rate limit (reached|exceeded)|limit.*resets|invalid api key|authentication.*failed|please (log ?in|authenticate)|credit balance is too low|quota exceeded|api error.*(401|403|429))"
}
```
<!-- /current-code -->

### 2. Claude-specific skip helper used by every behavior eval

<!-- current-code path=tests/evals/test-helpers.sh lines=28-35 ref=2bb93a0 region_sha256=8037a52ecb47300e7dcd6ec67e2f70d9f72f8384f518eb3d2c11e443b57eb7e8 -->
```bash
skip_if_claude_unavailable() {
  output="$1"
  reason="${2:-claude CLI unavailable (quota/auth)}"
  if is_claude_unavailable_output "$output"; then
    printf 'SKIP: %s: %s\n' "$reason" "$(printf '%s' "$output" | head -n 1)"
    finish_test_skip
  fi
}
```
<!-- /current-code -->

### 3. Claude-specific invocation function

<!-- current-code path=tests/evals/test-helpers.sh lines=67-86 ref=2bb93a0 region_sha256=e635ade14f2d0fb96b1306afdc4aee50fd670a50c2d222a6533dfdd9c6169739 -->
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

### Representative call site (one of 6)

<!-- current-code path=tests/evals/verify-before-claim.sh lines=21-22 ref=2bb93a0 region_sha256=d84370b25b5e130ee0b23610f437634ddcb7046b5c1be474209a3bbb1aa51df0 -->
```bash
output="$(run_claude "$prompt" "$project_dir" 2>&1 || true)"
skip_if_claude_unavailable "$output"
```
<!-- /current-code -->

The same two-line pattern (`run_claude` + `skip_if_claude_unavailable`) is present in 5 other evals: `root-cause-first.sh`, `no-invented-gates.sh`, `plan-grounding.sh`, `bootstrap-pending-completion.sh`, `no-unrelated-changes.sh`.

---

## Plan

### New file: `scripts/lib/llm_provider.sh`

Pure-bash registry. Exposes:

- `llm_provider_is_known <name>` — exit 0 if registered, 1 otherwise.
- `llm_provider_default_bin <name>` — print canonical bin name.
- `llm_provider_bin <name>` — print bin honoring `<PROVIDER>_BIN` env override.
- `llm_provider_run <name> <prompt> <workdir>` — dispatch to per-provider invoke function.
- `llm_provider_is_unavailable <name> <output>` — exit 0 if output looks like a quota/auth error.

PR-1 implements only the `claude` branch. Every function's `codex` case prints `Unknown LLM provider: codex` to stderr and returns 2 / 1 as appropriate. PR-2 fills in Codex.

The existing Claude regex (block 1 above) is moved verbatim into `llm_provider_is_unavailable`'s claude branch — no character changes — so all current matches continue to match (see Existing Behaviors Preserved #5).

The existing Claude invocation (block 3 above) is moved verbatim into `_llm_invoke_claude` with `$CLAUDE_BIN` resolved through `llm_provider_bin claude` instead of being read directly. Resolution priority is unchanged: env override > default name. No flag set or argument order changes.

### Modify: `tests/evals/test-helpers.sh`

- Source `scripts/lib/llm_provider.sh` near the top of the file (after the `set -euo pipefail` and env-var defaults block).
- Add `run_llm` that calls `llm_provider_run "${AGENT_LLM_PROVIDER:-claude}" "$@"`.
- Add `skip_if_llm_unavailable` that uses `llm_provider_is_unavailable "${AGENT_LLM_PROVIDER:-claude}" "$output"` and prints the same `SKIP: ... : <first line of output>` format then calls `finish_test_skip`.
- Reduce `run_claude` to a shim that calls `llm_provider_run claude "$@"` directly. **The shim must pin provider=claude, not delegate through `AGENT_LLM_PROVIDER`** so an out-of-tree caller with `AGENT_LLM_PROVIDER=codex` (after PR-2) still gets Claude semantics from this Claude-named function. Reviewer adjustment.
- Reduce `skip_if_claude_unavailable` to a shim that pins claude: it calls `llm_provider_is_unavailable claude "$output"` (NOT `skip_if_llm_unavailable "$@"`) and emits the same SKIP format. Pinning required for the same reason.
- Reduce `is_claude_unavailable_output` to a shim around `llm_provider_is_unavailable claude`.
- Add a deprecation comment above each shim noting the canonical replacement.

### Modify: 6 evals

In each of `verify-before-claim.sh`, `root-cause-first.sh`, `no-invented-gates.sh`, `plan-grounding.sh`, `bootstrap-pending-completion.sh`, `no-unrelated-changes.sh`:

- Replace `run_claude` call site with `run_llm`.
- Replace `skip_if_claude_unavailable` call site with `skip_if_llm_unavailable`.

No prompt content changes. No assertion changes. No control-flow changes.

`tests/evals/plugin-command-load.sh` is intentionally NOT migrated — it is Claude-Code-specific by design (uses `--plugin-dir`/`--debug-file`/`--print` flags) and stays Claude-pinned.

### New file: `tests/evals/mocks/claude-quota.sh`

Minimal Claude CLI mock that prints a known quota-exhausted error string to stdout and exits 0. Used by AC-6 in PR-1, and by AC-3 / AC-17 in PR-2. Tracking in git from PR-1 removes AC-6's dependency on an ad-hoc `/tmp/fakequota.sh`. Reviewer adjustment.

The other three mocks (`claude-misaligned.sh`, `codex-quota.sh`, `codex-auth.sh`) remain in PR-2 — they exercise FAIL paths and Codex routing that PR-1 cannot reach.

### New file: `tests/lib/test_llm_provider.sh`

Bash unit tests using a tiny inline assert harness (no bats dependency to keep CI surface unchanged). Covers, for the claude branch:

- `llm_provider_is_known claude` returns 0; `llm_provider_is_known codex` returns 1 (PR-1 state); `llm_provider_is_known foobar` returns 1.
- `llm_provider_default_bin claude` prints `claude`.
- `llm_provider_bin claude` honors `CLAUDE_BIN=/tmp/x` override.
- `llm_provider_is_unavailable claude` matches each of the 6 known Claude error variants in the existing regex.
- `llm_provider_is_unavailable claude` does NOT match a benign assistant response (`"tests pass and ready to merge"`).
- `llm_provider_run unknown` exits 2.

Codex-branch tests are stubbed with a `skip` placeholder line so PR-2 can fill them in.

---

## Acceptance Criteria

| ID | Criterion | Verification Method |
|---|---|---|
| AC-1 | `scripts/lib/llm_provider.sh` exists, is sourced cleanly, and `bash -n` passes. | TYPECHECK |
| AC-2 | `tests/evals/test-helpers.sh` defines `run_llm` and `skip_if_llm_unavailable`; `run_claude`, `skip_if_claude_unavailable`, and `is_claude_unavailable_output` still exist as shims (back-compat for any out-of-tree caller). | AUTOMATED-UNIT (`tests/lib/test_llm_provider.sh` + grep assertions in the same harness) |
| AC-3 | All 6 provider-portable evals are migrated off the Claude-specific helpers. Verified by `! rg -l -e 'run_claude' -e 'skip_if_claude_unavailable' tests/evals -g '*.sh' -g '!test-helpers.sh' -g '!plugin-command-load.sh'` producing no output. The `-g '*.sh'` filter is required so the scan does not pick up `tests/evals/README.md`, which mentions `run_claude` as documentation, not as a call site. (`-e` form avoids alternation pipe so the command is markdown-table safe.) | TYPECHECK |
| AC-4 | `tests/lib/test_llm_provider.sh` passes (claude branch coverage). | AUTOMATED-UNIT |
| AC-5 | `scripts/agent-evals.sh --fast` exits 0 (existing Claude-deterministic eval still passes; no regression). | AUTOMATED-INTEGRATION |
| AC-6 | `CLAUDE_BIN="$(pwd)/tests/evals/mocks/claude-quota.sh" scripts/agent-evals.sh --behavior` produces 4 SKIP exit 0. Absolute path is required because eval helpers `cd` into temp project dirs before exec, so a relative `CLAUDE_BIN` would not resolve. The Claude quota mock is checked in as part of PR-1 so AC-6 is self-contained and does not depend on any `/tmp` ad-hoc file. The other three mocks remain in PR-2. | AUTOMATED-INTEGRATION |
| AC-7 | `scripts/agent-validate.sh` passes (template self-validation; no skill count change). | AUTOMATED-INTEGRATION |
| AC-8 | `python3 scripts/lib/test_validate_plan.py` passes 27/27 (unrelated subsystem unchanged). | AUTOMATED-UNIT |
| AC-9 | `scripts/agent-validate-plan.sh docs/plans/llm-provider/pr-1/plan.md` exits 0 at plan creation time, before code work begins. After PR-1 implementation lands, the same command produces EV-003/EV-004 "working tree drifted from cited region" warnings — this is expected and EXPLICITLY part of the validator's design (plan cites pre-change state at `ref=2bb93a0`). The criterion is satisfied iff: (a) the plan validated cleanly at creation, AND (b) re-running it on the post-implementation tree produces only EV-003/EV-004 drift warnings, no other findings. | AUTOMATED-UNIT |
| AC-10 | `bash -n` passes on every modified shell file (`scripts/lib/llm_provider.sh`, `tests/evals/test-helpers.sh`, `tests/lib/test_llm_provider.sh`, the 6 migrated evals). | TYPECHECK |

---

## Existing Behaviors Preserved

Evidence blocks above ground each claim. No behavior in this PR is classified `INTENTIONALLY REMOVED` or `BUG FIX`. Each entry below cites the file and line range that establishes the current behavior.

- **PRESERVED** — `scripts/agent-evals.sh --fast` runs `tests/evals/plugin-command-load.sh` only and exits 0 in deterministic-only mode. PR-1 does not touch `scripts/agent-evals.sh:99-103` or `tests/evals/plugin-command-load.sh:1-67`.
- **PRESERVED** — `scripts/agent-evals.sh --behavior` runs 4 LLM evals and treats failures as advisory. Helpers become shims; runner is unchanged. Evidence: `scripts/agent-evals.sh:104-107`.
- **PRESERVED** — `scripts/agent-evals.sh --integration` runs deterministic + behavior + integration sets. Runner mode dispatch is not touched in PR-1. Evidence: `scripts/agent-evals.sh:108-111`.
- **PRESERVED** — Exit code contract: `0`=PASS, `77`=SKIP, other=FAIL; runner aggregates failures into exit `1`. PR-1 changes no exit codes. Evidence: `scripts/agent-evals.sh:142-154`.
- **PRESERVED** — `is_claude_unavailable_output` regex recognizes every Claude error string it matched at `2bb93a0`. The regex is moved verbatim into `llm_provider_is_unavailable`'s claude branch; the shim calls into the same regex. AC-4 exercises every known variant. Evidence: `tests/evals/test-helpers.sh:22-26`.
- **PRESERVED** — `CLAUDE_BIN`, `CLAUDE_EXTRA_ARGS`, `EVAL_TIMEOUT` env vars work as before. Resolution moves through `llm_provider_bin claude` but reads the same env var with the same default. Evidence: `tests/evals/test-helpers.sh:5-7`.
- **PRESERVED via shim** — `run_claude` is callable with the same `(prompt, workdir)` signature. Internal callers migrate to `run_llm`; the function continues to exist for any out-of-tree consumer. Evidence: `tests/evals/test-helpers.sh:67-86`.
- **PRESERVED via shim** — `skip_if_claude_unavailable` is callable with the same `(output, [reason])` signature and emits the same `SKIP: <reason>: <first line>` format then exits 77. The shim pins provider=claude so behavior is identical even when external scripts have set `AGENT_LLM_PROVIDER` to a different value. Evidence: `tests/evals/test-helpers.sh:28-35`.
- **PRESERVED** — All 6 evals produce identical PASS/FAIL/SKIP output on identical Claude CLI input. Migration is a name swap; the shim and the new helper share the exact same regex and invocation flags. AC-6 verifies. Representative call site evidence: `tests/evals/verify-before-claim.sh:21-22`.
- **PRESERVED** — `scripts/agent-validate.sh` template self-check still passes. New library file does not change the skill-count assertion. AC-7 verifies. Evidence: `scripts/agent-validate.sh:198-213`.
- **PRESERVED** — All 27 `test_validate_plan.py` unit tests still pass. PR-1 does not touch `scripts/lib/validate_plan.py`. AC-8 verifies. Evidence: `scripts/lib/test_validate_plan.py:1-10` (suite entry).

## Verification

Pre-merge gates, in order. All must pass:

```bash
# Static checks
bash -n scripts/lib/llm_provider.sh
bash -n tests/evals/test-helpers.sh
bash -n tests/lib/test_llm_provider.sh
for f in tests/evals/verify-before-claim.sh tests/evals/root-cause-first.sh \
         tests/evals/no-invented-gates.sh tests/evals/plan-grounding.sh \
         tests/evals/bootstrap-pending-completion.sh tests/evals/no-unrelated-changes.sh; do
  bash -n "$f"
done

# Migration grep (AC-3). `-g '*.sh'` is required so we do not pick up
# tests/evals/README.md, which legitimately mentions `run_claude` in prose.
! rg -l -e 'run_claude' -e 'skip_if_claude_unavailable' tests/evals \
       -g '*.sh' -g '!test-helpers.sh' -g '!plugin-command-load.sh'

# Unit + plan validator
bash tests/lib/test_llm_provider.sh                     # AC-4
python3 scripts/lib/test_validate_plan.py               # AC-8
scripts/agent-validate-plan.sh docs/plans/llm-provider/pr-1/plan.md     # AC-9
scripts/agent-validate.sh                               # AC-7

# Integration: existing eval suite still works under default (claude)
scripts/agent-evals.sh --fast                           # AC-5

# Integration: behavior evals still SKIP cleanly under the Claude quota mock.
# Absolute path required: eval helpers cd into temp project dirs before exec,
# so a relative CLAUDE_BIN would fail with ENOENT instead of triggering SKIP.
chmod +x tests/evals/mocks/claude-quota.sh                                                  # one-time, in case git --umask stripped +x
CLAUDE_BIN="$(pwd)/tests/evals/mocks/claude-quota.sh" scripts/agent-evals.sh --behavior     # AC-6 (4 SKIP, exit 0)

# Migration regression (Claude-only path unchanged)
tests/migrations/0.3.0/run.sh
tests/migrations/0.4.0/run.sh
```

Per reviewer adjustment, `tests/evals/mocks/claude-quota.sh` is shipped in PR-1 so AC-6 is self-contained. PR-2 adds the remaining three mocks (`claude-misaligned.sh`, `codex-quota.sh`, `codex-auth.sh`) per AC-17 in the parent proposal.

---

## Out of Scope (PR-2 / PR-3)

- `--provider` CLI flag and `AGENT_LLM_PROVIDER` env handling in `scripts/agent-evals.sh` (PR-2).
- Codex branch implementation in the registry (PR-2).
- Provider-aware missing-CLI message (PR-2).
- `tests/evals/codex-harness-fixture.sh` (PR-2).
- `tests/evals/mocks/claude-misaligned.sh`, `tests/evals/mocks/codex-quota.sh`, `tests/evals/mocks/codex-auth.sh` (PR-2). PR-1 ships only `claude-quota.sh` because AC-6 needs it.
- README/USAGE/tests/evals/README documentation (PR-3).
- Version bump, plugin metadata, migration manifest (PR-3).
- CHANGELOG entry (PR-3, with cumulative summary across all 3 PRs).

---

## Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Shim semantics drift from new helpers, breaking out-of-tree callers. | Both the shim and the new helper call into the same `llm_provider_*` registry function. There is one regex string and one invocation function — duplication is impossible by construction. |
| `source` of `scripts/lib/llm_provider.sh` from `test-helpers.sh` fails in some environments. | Use repo-root-relative resolution: `lib_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)/scripts/lib"`. Verified by AC-5 (existing eval suite must still run). |
| Migration grep (AC-3) misses a call site because of unusual quoting. | The grep uses word-boundary `\b...\b` and excludes only the two known intentional-Claude files. False negatives would manifest as PR-1 leaving a real Claude pin behind, which would later be caught when PR-2 turns on `--provider codex`. Acceptable risk for a refactor PR. |
| Bash 3 compat (macOS default shell). | Registry uses only case statements + `printf`/`return`. No `[[`-only features, no associative arrays. AC-10 catches syntax errors. |
