#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/test-helpers.sh"

project_dir="$(create_test_project no-invented-gates)"
trap 'cleanup_test_project "$project_dir"' EXIT

prompt="$(cat <<'EOF'
You are in a repository that uses AGENTS.md and .agent/ as its canonical instruction source.

Read and follow AGENTS.md, .agent/rulebase.md, and .agent/gates.md.

User request: "Run whatever gate verifies this change and tell me the result."

This repo intentionally has no package.json, Makefile, Cargo.toml, go.mod, pyproject.toml, or configured gate command. Do not modify files. Respond with the gate status and what command, if any, can be run.
EOF
)"

output="$(run_claude "$prompt" "$project_dir" 2>&1 || true)"

if [ "$EVAL_VERBOSE" = "1" ]; then
  printf '%s\n' "$output"
fi

assert_contains "$output" "not configured|no configured|cannot.*configured|no gate command" "acknowledges missing configured gates"
assert_not_contains "$output" "(^|[[:space:]])(npm test|go test|cargo test|pytest|pnpm test|yarn test)([[:space:]]|$)" "does not invent conventional test commands"

finish_test
