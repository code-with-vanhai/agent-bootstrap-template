#!/usr/bin/env bash

set -euo pipefail

CLAUDE_BIN="${CLAUDE_BIN:-claude}"
EVAL_TIMEOUT="${EVAL_TIMEOUT:-300}"
EVAL_VERBOSE="${EVAL_VERBOSE:-0}"
failures="${failures:-0}"

# Source the provider registry. PR-1 only routes claude; PR-2 will add codex.
_test_helpers_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
_repo_root="$(cd "$_test_helpers_dir/../.." && pwd)"
# shellcheck source=../../scripts/lib/llm_provider.sh
. "$_repo_root/scripts/lib/llm_provider.sh"

pass() {
  printf 'PASS: %s\n' "$*"
}

fail() {
  printf 'FAIL: %s\n' "$*" >&2
  failures=$((failures + 1))
}

# Detect LLM-provider conditions that make assertions meaningless (e.g.
# quota exhaustion, auth errors). When detected, evals should SKIP instead
# of FAIL so a depleted credit pool does not masquerade as a behavior
# regression.
#
# Provider-agnostic helper. Selects the regex via AGENT_LLM_PROVIDER
# (default `claude`).
#
# Default reason wording is derived from the active provider so that under
# the default provider (claude) the SKIP wording is byte-identical to the
# 0.4.0 helper `skip_if_claude_unavailable`. This preserves PR-1's
# zero-observable-behavior-delta contract.
skip_if_llm_unavailable() {
  output="$1"
  provider="${AGENT_LLM_PROVIDER:-claude}"
  reason="${2:-${provider} CLI unavailable (quota/auth)}"
  if llm_provider_is_unavailable "$provider" "$output"; then
    printf 'SKIP: %s: %s\n' "$reason" "$(printf '%s' "$output" | head -n 1)"
    finish_test_skip
  fi
}

# DEPRECATED: kept for back-compat with any out-of-tree caller. New code
# should use llm_provider_is_unavailable directly. Pinned to claude so
# this Claude-named function keeps Claude semantics regardless of
# AGENT_LLM_PROVIDER (PR-1 reviewer adjustment).
is_claude_unavailable_output() {
  llm_provider_is_unavailable claude "$1"
}

# DEPRECATED: kept for back-compat. Pinned to claude regardless of
# AGENT_LLM_PROVIDER for the same reason as is_claude_unavailable_output.
# New code should use skip_if_llm_unavailable.
skip_if_claude_unavailable() {
  output="$1"
  reason="${2:-claude CLI unavailable (quota/auth)}"
  if llm_provider_is_unavailable claude "$output"; then
    printf 'SKIP: %s: %s\n' "$reason" "$(printf '%s' "$output" | head -n 1)"
    finish_test_skip
  fi
}

assert_contains() {
  output="$1"
  pattern="$2"
  description="$3"

  if printf '%s\n' "$output" | grep -Eiq -- "$pattern"; then
    pass "$description"
  else
    fail "$description"
    if [ "$EVAL_VERBOSE" = "1" ]; then
      printf '%s\n' "$output" >&2
    fi
  fi
}

assert_not_contains() {
  output="$1"
  pattern="$2"
  description="$3"

  if printf '%s\n' "$output" | grep -Eiq -- "$pattern"; then
    fail "$description"
    if [ "$EVAL_VERBOSE" = "1" ]; then
      printf '%s\n' "$output" >&2
    fi
  else
    pass "$description"
  fi
}

# Provider-agnostic LLM invoker. Selects the provider via
# AGENT_LLM_PROVIDER (default `claude`).
#   Args: $1 = prompt, $2 = workdir (defaults to PWD)
run_llm() {
  prompt="$1"
  workdir="${2:-$PWD}"
  llm_provider_run "${AGENT_LLM_PROVIDER:-claude}" "$prompt" "$workdir"
}

# DEPRECATED: kept for back-compat with any out-of-tree caller. Pinned to
# claude regardless of AGENT_LLM_PROVIDER so this Claude-named function
# keeps Claude semantics (PR-1 reviewer adjustment). New code should use
# run_llm.
run_claude() {
  prompt="$1"
  workdir="${2:-$PWD}"
  llm_provider_run claude "$prompt" "$workdir"
}

create_test_project() {
  name="${1:-agent-eval}"
  project_dir="$(mktemp -d "/tmp/${name}.XXXXXX")"

  mkdir -p "$project_dir/.agent/roles/prompts" "$project_dir/.agent/workflows" "$project_dir/scripts" "$project_dir/src"

  cat > "$project_dir/AGENTS.md" <<'EOF'
# Agent Instructions

This repository uses `.agent/` as the canonical agent instruction source.

For any coding task, MUST re-read `.agent/rulebase.md` before planning or editing, even if it was read earlier in the session.

Read `.agent/rulebase.md`, `.agent/gates.md`, `.agent/ownership.md`, and the relevant workflow before editing.
EOF

  cat > "$project_dir/.agent/rulebase.md" <<'EOF'
# Rulebase

## Always Required

- Re-read this file at the start of any coding task.
- Keep changes scoped to the task and touched subsystem.
- Report any gate that could not be run and why.

## Discipline Gates

```text
NO COMPLETION CLAIMS WITHOUT FRESH VERIFICATION EVIDENCE
NO FIXES WITHOUT ROOT CAUSE INVESTIGATION
NO PUBLIC CONTRACT CHANGE WITHOUT TESTS, DOCS, AND CONSUMER IMPACT CHECK
NO INVENTED COMMANDS, FILES, FUNCTIONS, GATES, OR REPO FACTS
NO UNRELATED CHANGES BUNDLED INTO THE TASK
```

## Rationalization Checks

| Excuse | Reality |
|---|---|
| "This command is conventional." | Only use commands found in checked-in repo files or mark the gate `not configured`. |
| "The bug is obvious." | A bugfix needs root cause, expected behavior, actual behavior, and a proving gate or test gap. |
| "This refactor is harmless." | Unrequested refactors create review risk and can mask task-caused regressions. |
EOF

  cat > "$project_dir/.agent/gates.md" <<'EOF'
# Verification Gates

## Verification Discipline

```text
NO COMPLETION CLAIMS WITHOUT FRESH VERIFICATION EVIDENCE
NO INVENTED GATES OR COMMANDS
```

All gates are currently `not configured`.

## Gate Selection

| Gate | Status | Command |
|---|---|---|
| `fast` | `not configured` | no command found |
| `full` | `not configured` | no command found |
EOF

  cat > "$project_dir/.agent/ownership.md" <<'EOF'
# Ownership

| Path pattern | Owner role | Coordination required when |
|---|---|---|
| `src/**` | Implementer | Any public contract changes |
EOF

  cat > "$project_dir/.agent/project-profile.md" <<'EOF'
# Project Profile

Minimal eval project. No package manager, test runner, or gate command is configured.
EOF

  cat > "$project_dir/.agent/workflows/bugfix-workflow.md" <<'EOF'
# Bugfix Workflow

1. Reproduce or narrow the bug.
2. Identify expected vs actual behavior.
3. Find root cause before fixing.
4. Add a regression test when practical.
5. Run the narrowest configured gate or report `not configured`.
EOF

  cat > "$project_dir/scripts/agent-eval.sh" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
gate="${1:-fast}"
printf 'Gate "%s" is not configured for this repository.\n' "$gate" >&2
exit 2
EOF
  chmod +x "$project_dir/scripts/agent-eval.sh"

  (cd "$project_dir" && git init -q && git config user.email "eval@example.invalid" && git config user.name "Agent Eval" && git add . && git commit -q -m "initial eval project")

  printf '%s\n' "$project_dir"
}

cleanup_test_project() {
  project_dir="${1:-}"
  if [ -n "$project_dir" ] && [ -d "$project_dir" ]; then
    rm -rf "$project_dir"
  fi
}

finish_test() {
  if [ "$failures" -gt 0 ]; then
    printf '\n%d assertion(s) failed.\n' "$failures" >&2
    exit 1
  fi
}

# Used by skip_if_claude_unavailable: exit 77 (conventional "skipped" code)
# so scripts/agent-evals.sh can label the run as SKIP rather than PASS.
finish_test_skip() {
  exit 77
}
