#!/usr/bin/env bash
set -euo pipefail

if [ -n "${AGENT_ROOT:-}" ]; then
  ROOT="$AGENT_ROOT"
  root_source="env"
elif [ -d ".agent" ]; then
  ROOT="$(pwd)"
  root_source="pwd"
else
  ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
  root_source="git"
fi

printf 'Resolving root: %s (source: %s)\n' "$ROOT" "$root_source" >&2
cd "$ROOT"

failures=0

fail() {
  printf 'FAIL: %s\n' "$*" >&2
  failures=$((failures + 1))
}

pass() {
  printf 'PASS: %s\n' "$*"
}

check_path() {
  if [ -e "$1" ]; then
    pass "$1 exists"
  else
    fail "$1 is missing"
  fi
}

check_contains() {
  file="$1"
  pattern="$2"
  description="$3"

  if [ ! -f "$file" ]; then
    fail "$description cannot be checked because $file is missing"
    return
  fi

  if grep -q "$pattern" "$file"; then
    pass "$description"
  else
    fail "$description"
  fi
}

if [ -d ".agent" ]; then
  matches="$(grep -RIn '{{[^}]*}}' .agent AGENTS.md CLAUDE.md GEMINI.md .cursor .github scripts 2>/dev/null || true)"
  if [ -n "$matches" ]; then
    fail "placeholders remain in generated agent files"
    printf '%s\n' "$matches" >&2
  else
    pass "no template placeholders found"
  fi
else
  fail ".agent directory is missing"
fi

check_path ".agent/README.md"
check_path ".agent/manifest.json"
check_path ".agent/project-profile.md"
check_path ".agent/rulebase.md"
check_path ".agent/ownership.md"
check_path ".agent/gates.md"
check_path ".agent/decisions.md"
check_path ".agent/lessons.md"
check_path ".agent/roles/planner.md"
check_path ".agent/roles/implementer.md"
check_path ".agent/roles/reviewer.md"
check_path ".agent/roles/gate-runner.md"
check_path ".agent/roles/prompts/planner-subagent.md"
check_path ".agent/roles/prompts/implementer-subagent.md"
check_path ".agent/roles/prompts/reviewer-subagent.md"
check_path ".agent/roles/prompts/gate-runner-subagent.md"
check_path ".agent/workflows/bootstrap-workflow.md"
check_path ".agent/workflows/feature-workflow.md"
check_path ".agent/workflows/bugfix-workflow.md"
check_path ".agent/workflows/refactor-workflow.md"
check_path ".agent/workflows/review-workflow.md"
check_path ".agent/workflows/security-review-workflow.md"
check_path ".agent/workflows/improvement-cycle-workflow.md"
check_path ".agent/workflows/rule-evolution-workflow.md"
check_path "scripts/agent-eval.sh"

check_contains ".agent/rulebase.md" "NO COMPLETION CLAIMS WITHOUT FRESH VERIFICATION EVIDENCE" ".agent/rulebase.md includes completion verification discipline"
check_contains ".agent/rulebase.md" "Rationalization Checks" ".agent/rulebase.md includes rationalization checks"
check_contains ".agent/gates.md" "NO INVENTED GATES OR COMMANDS" ".agent/gates.md includes no-invented-gates discipline"

if command -v jq >/dev/null 2>&1; then
  if jq . .agent/manifest.json >/dev/null; then
    pass ".agent/manifest.json is valid JSON"
  else
    fail ".agent/manifest.json is invalid JSON"
  fi
elif command -v python3 >/dev/null 2>&1; then
  if python3 -m json.tool .agent/manifest.json >/dev/null; then
    pass ".agent/manifest.json is valid JSON"
  else
    fail ".agent/manifest.json is invalid JSON"
  fi
else
  fail "cannot validate .agent/manifest.json because neither jq nor python3 is available"
fi

if [ -f "scripts/agent-eval.sh" ]; then
  if bash -n scripts/agent-eval.sh; then
    pass "scripts/agent-eval.sh shell syntax is valid"
  else
    fail "scripts/agent-eval.sh shell syntax is invalid"
  fi
fi

for adapter in \
  AGENTS.md \
  CLAUDE.md \
  GEMINI.md \
  .cursor/rules/agent-system.mdc \
  .github/copilot-instructions.md
do
  if [ -e "$adapter" ]; then
    if grep -q ".agent/" "$adapter"; then
      pass "$adapter points to .agent/"
    else
      fail "$adapter exists but does not point to .agent/"
    fi
  else
    printf 'SKIP: %s not generated\n' "$adapter"
  fi
done

if [ "$failures" -gt 0 ]; then
  printf '\n%d validation check(s) failed.\n' "$failures" >&2
  exit 1
fi

printf '\nAll validation checks passed.\n'
