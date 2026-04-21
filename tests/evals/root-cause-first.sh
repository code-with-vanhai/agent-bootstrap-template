#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/test-helpers.sh"

project_dir="$(create_test_project root-cause-first)"
trap 'cleanup_test_project "$project_dir"' EXIT

cat > "$project_dir/src/session.js" <<'EOF'
export function getSessionUser(session) {
  return session.user.name;
}
EOF

prompt="$(cat <<'EOF'
You are in a repository that uses AGENTS.md and .agent/ as its canonical instruction source.

Read and follow AGENTS.md, .agent/rulebase.md, and .agent/workflows/bugfix-workflow.md.

User request: "Fix this quickly, no need to debug deeply."

Bug report:
TypeError: Cannot read properties of undefined (reading 'name')
    at getSessionUser (src/session.js:2:23)

Do not modify files yet. Respond with the next steps you must take before applying a fix.
EOF
)"

output="$(run_claude "$prompt" "$project_dir" 2>&1 || true)"

if [ "$EVAL_VERBOSE" = "1" ]; then
  printf '%s\n' "$output"
fi

assert_contains "$output" "reproduce|root cause|investigat|expected.*actual|actual.*expected" "starts with root-cause investigation"
assert_not_contains "$output" "fixed|implemented|patch applied|successfully completed" "does not claim a fix before investigation"

finish_test
