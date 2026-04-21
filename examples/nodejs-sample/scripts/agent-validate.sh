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

for path in \
  .agent/README.md \
  .agent/manifest.json \
  .agent/project-profile.md \
  .agent/rulebase.md \
  .agent/ownership.md \
  .agent/gates.md \
  .agent/decisions.md \
  .agent/lessons.md \
  .agent/roles/planner.md \
  .agent/roles/implementer.md \
  .agent/roles/reviewer.md \
  .agent/roles/gate-runner.md \
  .agent/workflows/bootstrap-workflow.md \
  .agent/workflows/feature-workflow.md \
  .agent/workflows/bugfix-workflow.md \
  .agent/workflows/refactor-workflow.md \
  .agent/workflows/review-workflow.md \
  .agent/workflows/security-review-workflow.md \
  .agent/workflows/improvement-cycle-workflow.md \
  .agent/workflows/rule-evolution-workflow.md \
  scripts/agent-eval.sh
do
  if [ -e "$path" ]; then
    pass "$path exists"
  else
    fail "$path is missing"
  fi
done

matches="$(grep -RIn '{{[^}]*}}' .agent AGENTS.md CLAUDE.md .cursor scripts 2>/dev/null || true)"
if [ -n "$matches" ]; then
  fail "placeholders remain"
  printf '%s\n' "$matches" >&2
else
  pass "no placeholders remain"
fi

if command -v jq >/dev/null 2>&1; then
  if jq . .agent/manifest.json >/dev/null; then
    pass ".agent/manifest.json is valid JSON"
  else
    fail ".agent/manifest.json is invalid JSON"
  fi
elif command -v python3 >/dev/null 2>&1 && python3 -m json.tool .agent/manifest.json >/dev/null; then
  pass ".agent/manifest.json is valid JSON"
else
  fail ".agent/manifest.json is invalid JSON or no JSON validator is available"
fi

if bash -n scripts/agent-eval.sh; then
  pass "scripts/agent-eval.sh shell syntax is valid"
else
  fail "scripts/agent-eval.sh shell syntax is invalid"
fi

if grep -q ".agent/" AGENTS.md; then
  pass "AGENTS.md points to .agent/"
else
  fail "AGENTS.md does not point to .agent/"
fi

if grep -q ".agent/" CLAUDE.md; then
  pass "CLAUDE.md points to .agent/"
else
  fail "CLAUDE.md does not point to .agent/"
fi

if grep -q ".agent/" .cursor/rules/agent-system.mdc; then
  pass ".cursor/rules/agent-system.mdc points to .agent/"
else
  fail ".cursor/rules/agent-system.mdc does not point to .agent/"
fi

if [ "$failures" -gt 0 ]; then
  printf '\n%d validation check(s) failed.\n' "$failures" >&2
  exit 1
fi

printf '\nAll validation checks passed.\n'
