#!/usr/bin/env bash
# Behavior eval: reviewer must catch grounding defects in fixture plan files.
#
# Strategy:
#   1. Stage the canonical workflow + planner role + the validator scripts in
#      the test project so the agent can RUN scripts/agent-validate-plan.sh.
#   2. Manifest reports template_version >= 0.4.0 so the validator does not
#      silently skip.
#   3. For each fixture, ask the agent to (a) run the validator first and
#      (b) summarize findings as a list of `<check-id> [severity]` lines.
#      Assert against the structured output, not free-form prose.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/test-helpers.sh"

TEMPLATE_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
FIXTURES_DIR="$SCRIPT_DIR/fixtures"

project_dir="$(create_test_project plan-grounding)"
trap 'cleanup_test_project "$project_dir"' EXIT

# Bump the test project's manifest to 0.4.0 so the validator does not skip.
mkdir -p "$project_dir/.agent"
cat > "$project_dir/.agent/manifest.json" <<'EOF'
{
  "template_version": "0.4.0",
  "synced_to_template_version": "0.4.0",
  "instantiated_from_template_version": "0.4.0",
  "features_enabled": []
}
EOF

# Stage src/app.ts that good + bad-stale-snippet fixtures cite.
mkdir -p "$project_dir/src" "$project_dir/.agent/runs" "$project_dir/scripts/lib"
cat > "$project_dir/src/app.ts" <<'EOF'
export function helloWorld() {
  return "ok";
}
EOF

# Stage workflows + planner role so the agent has the Plan/Spec Review protocol.
mkdir -p "$project_dir/.agent/workflows" "$project_dir/.agent/roles"
cp "$TEMPLATE_ROOT/core/workflows/review-workflow.md" \
   "$project_dir/.agent/workflows/review-workflow.md"
cp "$TEMPLATE_ROOT/core/workflows/feature-workflow.md" \
   "$project_dir/.agent/workflows/feature-workflow.md"
cp "$TEMPLATE_ROOT/core/roles/planner.md" \
   "$project_dir/.agent/roles/planner.md"

# Stage the validator so the agent can actually run it.
cp "$TEMPLATE_ROOT/scripts/agent-validate-plan.sh" \
   "$project_dir/scripts/agent-validate-plan.sh"
cp "$TEMPLATE_ROOT/scripts/lib/__init__.py" \
   "$project_dir/scripts/lib/__init__.py"
cp "$TEMPLATE_ROOT/scripts/lib/validate_plan.py" \
   "$project_dir/scripts/lib/validate_plan.py"
cp -R "$TEMPLATE_ROOT/scripts/lib/plan_validation" \
   "$project_dir/scripts/lib/plan_validation"
chmod +x "$project_dir/scripts/agent-validate-plan.sh"

( cd "$project_dir" && git add . && git -c user.email=t@t -c user.name=t commit -q -m "fixture" )

run_review() {
  fixture="$1"
  description="$2"

  cp "$fixture" "$project_dir/.agent/runs/eval-plan.md"

  prompt_file="$project_dir/.agent/runs/eval-prompt.md"
  cat > "$prompt_file" <<'EOF'
You are reviewing the plan at .agent/runs/eval-plan.md in the current repo.

REQUIRED steps:
1. First, run: bash scripts/agent-validate-plan.sh .agent/runs/eval-plan.md
   Report the exact stdout/stderr you saw.
2. Then apply the Plan/Spec Review protocol from .agent/workflows/review-workflow.md
   (grounding pass first).
3. Output a final section titled `## Findings` with one bullet per finding in
   this exact format:
       - <CHECK-ID> [<SEVERITY>] <one-line message>
   Use the validator's check ids (EV-001..EV-005, SC-*, BEH-*, SECT-*, AC-*).
   Severity must be one of: High, Medium, Low. If there are no findings, output
   `- NONE [Info] plan is grounded`.

Do not edit any files. Do not invent check ids that the validator does not
emit.
EOF
  prompt="$(cat "$prompt_file")"

  output="$(run_llm "$prompt" "$project_dir" 2>&1 || true)"

  if [ "$EVAL_VERBOSE" = "1" ]; then
    printf '\n--- %s ---\n%s\n' "$description" "$output"
  fi

  printf '%s' "$output"
}

# --- bad-stale-snippet --------------------------------------------------
output="$(run_review "$FIXTURES_DIR/grounding-bad-stale-snippet/plan.md" "bad-stale-snippet")"
skip_if_llm_unavailable "$output"
assert_contains "$output" "EV-003|EV-005|snippet does not match|region_sha256" \
  "bad-stale-snippet plan flagged with EV-003/EV-005 (snippet/sha mismatch)"

# --- bad-fictional-line -------------------------------------------------
output="$(run_review "$FIXTURES_DIR/grounding-bad-fictional-line/plan.md" "bad-fictional-line")"
skip_if_llm_unavailable "$output"
assert_contains "$output" "EV-002|EV-003|out of range|does not exist" \
  "bad-fictional-line plan flagged with EV-002/EV-003 (path/range error)"

# --- good ---------------------------------------------------------------
output="$(run_review "$FIXTURES_DIR/grounding-good/plan.md" "good")"
skip_if_llm_unavailable "$output"
assert_not_contains "$output" "EV-002 \[High\]|EV-003 \[High\]|EV-005 \[High\]" \
  "good plan does not raise High EV-002/EV-003/EV-005"

finish_test
