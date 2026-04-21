#!/usr/bin/env bash

set -euo pipefail

CLAUDE_BIN="${CLAUDE_BIN:-claude}"
EVAL_TIMEOUT="${EVAL_TIMEOUT:-300}"
EVAL_VERBOSE="${EVAL_VERBOSE:-0}"
failures="${failures:-0}"

pass() {
  printf 'PASS: %s\n' "$*"
}

fail() {
  printf 'FAIL: %s\n' "$*" >&2
  failures=$((failures + 1))
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
