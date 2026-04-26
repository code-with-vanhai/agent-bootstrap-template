#!/usr/bin/env bash
# Behavior eval: reviewer must catch grounding defects in fixture plan files.
#
# Skip-friendly: requires the Claude CLI just like the other behavior evals.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/test-helpers.sh"

FIXTURES_DIR="$SCRIPT_DIR/fixtures"

project_dir="$(create_test_project plan-grounding)"
trap 'cleanup_test_project "$project_dir"' EXIT

# Stage a small repo file the bad-fixture references; the good fixture also
# uses it.
mkdir -p "$project_dir/src" "$project_dir/.agent/runs"
cat > "$project_dir/src/app.ts" <<'EOF'
export function helloWorld() {
  return "ok";
}
EOF

# Stage the canonical review workflow + planner role so the agent has the
# Plan/Spec Review protocol to apply. This is the same content the template
# would patch into a target repo at 0.4.0.
mkdir -p "$project_dir/.agent/workflows" "$project_dir/.agent/roles"
cp "$(cd "$SCRIPT_DIR/../.." && pwd)/core/workflows/review-workflow.md" \
   "$project_dir/.agent/workflows/review-workflow.md"
cp "$(cd "$SCRIPT_DIR/../.." && pwd)/core/roles/planner.md" \
   "$project_dir/.agent/roles/planner.md"

( cd "$project_dir" && git add . && git -c user.email=t@t -c user.name=t commit -q -m "src + workflows" )

run_review() {
  fixture="$1"
  description="$2"

  cp "$fixture" "$project_dir/.agent/runs/eval-plan.md"

  prompt="$(cat <<EOF
You are reviewing the plan at .agent/runs/eval-plan.md in the current
repository. Follow the Plan/Spec Review section in
.agent/workflows/review-workflow.md (grounding pass first).

Output format:
- Findings: list each issue with severity (P0/P1/P2/P3) and check id.
- Do not edit any files.
EOF
)"

  output="$(run_claude "$prompt" "$project_dir" 2>&1 || true)"

  if [ "$EVAL_VERBOSE" = "1" ]; then
    printf '\n--- %s ---\n%s\n' "$description" "$output"
  fi

  printf '%s' "$output"
}

# --- bad-stale-snippet: snippet does not match working tree --------------
output="$(run_review "$FIXTURES_DIR/grounding-bad-stale-snippet/plan.md" "bad-stale-snippet")"
assert_contains "$output" "P0|grounding|EV-003|mismatch|does not match" \
  "bad-stale-snippet plan flagged as grounding defect"

# --- bad-fictional-line: cited line range does not exist -----------------
output="$(run_review "$FIXTURES_DIR/grounding-bad-fictional-line/plan.md" "bad-fictional-line")"
assert_contains "$output" "P0|grounding|EV-002|EV-003|does not exist|out of range" \
  "bad-fictional-line plan flagged as grounding defect"

# --- good: grounded plan, no grounding defect ---------------------------
output="$(run_review "$FIXTURES_DIR/grounding-good/plan.md" "good")"
assert_not_contains "$output" "P0.*grounding|grounding.*P0|EV-002|EV-003" \
  "good plan does not raise grounding defects"

finish_test
