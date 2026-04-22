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

  if grep -q -- "$pattern" "$file"; then
    pass "$description"
  else
    fail "$description"
  fi
}

check_json() {
  file="$1"
  description="$2"

  if [ ! -f "$file" ]; then
    fail "$description cannot be checked because $file is missing"
    return
  fi

  if command -v jq >/dev/null 2>&1; then
    if jq . "$file" >/dev/null; then
      pass "$description"
    else
      fail "$description"
    fi
  elif command -v python3 >/dev/null 2>&1; then
    if python3 -m json.tool "$file" >/dev/null; then
      pass "$description"
    else
      fail "$description"
    fi
  else
    fail "$description cannot be checked because neither jq nor python3 is available"
  fi
}

validate_template_skills() {
  expected_skills="verify-before-completion root-cause-debugging scoped-implementation plan-before-code worktree-isolation no-invented-artifacts bootstrap-agent-system"

  check_path "core/bootstrap-steps.md"
  check_contains "core/bootstrap-steps.md" "Deterministic Skeleton" "core/bootstrap-steps.md includes deterministic skeleton phase"
  check_contains "core/bootstrap-steps.md" "Agent Completion" "core/bootstrap-steps.md includes agent completion phase"

  check_path "scripts/bootstrap-request.sh"
  check_contains "scripts/bootstrap-request.sh" "--features" "scripts/bootstrap-request.sh supports feature selection"
  check_contains "scripts/bootstrap-request.sh" "--harness" "scripts/bootstrap-request.sh supports harness selection"
  if bash -n scripts/bootstrap-request.sh; then
    pass "scripts/bootstrap-request.sh shell syntax is valid"
  else
    fail "scripts/bootstrap-request.sh shell syntax is invalid"
  fi

  check_path ".claude-plugin/plugin.json"
  check_json ".claude-plugin/plugin.json" ".claude-plugin/plugin.json is valid JSON"
  check_contains ".claude-plugin/plugin.json" "\"name\": \"agent-bootstrap\"" ".claude-plugin/plugin.json defines agent-bootstrap plugin"
  check_contains ".claude-plugin/plugin.json" "\"skills\": \"./core/skills/\"" ".claude-plugin/plugin.json points to canonical skills"
  check_contains ".claude-plugin/plugin.json" "\"commands\": \"./commands/\"" ".claude-plugin/plugin.json points to plugin commands"

  check_path ".claude-plugin/marketplace.json"
  check_json ".claude-plugin/marketplace.json" ".claude-plugin/marketplace.json is valid JSON"
  check_contains ".claude-plugin/marketplace.json" "\"source\": \"./\"" ".claude-plugin/marketplace.json installs plugin from repo root"

  check_path "commands/bootstrap.md"
  check_contains "commands/bootstrap.md" "agent-bootstrap --features standard --target ." "commands/bootstrap.md invokes plugin wrapper"

  check_path "bin/agent-bootstrap"
  check_contains "bin/agent-bootstrap" "--harness claude" "bin/agent-bootstrap defaults to Claude harness"
  if bash -n bin/agent-bootstrap; then
    pass "bin/agent-bootstrap shell syntax is valid"
  else
    fail "bin/agent-bootstrap shell syntax is invalid"
  fi

  check_path "core/github/PULL_REQUEST_TEMPLATE.md"
  check_contains "core/github/PULL_REQUEST_TEMPLATE.md" "Problem observed" "core/github/PULL_REQUEST_TEMPLATE.md includes problem observed section"
  check_contains "core/github/PULL_REQUEST_TEMPLATE.md" "Gates run" "core/github/PULL_REQUEST_TEMPLATE.md includes gates run section"
  check_contains "core/github/PULL_REQUEST_TEMPLATE.md" "fabricated problem statements, speculative fixes, or bundled unrelated changes" "core/github/PULL_REQUEST_TEMPLATE.md includes anti-slop warning"

  check_path "core/workflows/worktree-workflow.md"
  check_contains "core/workflows/worktree-workflow.md" "optional acceleration" "core/workflows/worktree-workflow.md states opt-in behavior"
  check_contains "core/workflows/worktree-workflow.md" "Directory Priority" "core/workflows/worktree-workflow.md includes directory priority"
  check_contains "core/workflows/worktree-workflow.md" "Baseline Gate" "core/workflows/worktree-workflow.md includes baseline gate"
  check_contains "core/workflows/worktree-workflow.md" "When NOT To Use" "core/workflows/worktree-workflow.md includes when-not-to-use section"

  check_path "core/skills/README.md"
  check_contains "core/skills/README.md" "Skill Mapping" "core/skills/README.md includes skill mapping"

  skill_count="$(find core/skills -mindepth 2 -maxdepth 2 -name SKILL.md | wc -l | tr -d '[:space:]')"
  if [ "$skill_count" = "7" ]; then
    pass "core/skills contains 7 skill files"
  else
    fail "core/skills contains $skill_count skill files, expected 7"
  fi

  for skill in $expected_skills; do
    skill_file="core/skills/$skill/SKILL.md"
    check_path "$skill_file"
    check_contains "$skill_file" "^name: $skill$" "$skill_file has matching skill name"
    check_contains "$skill_file" "^description: Use when" "$skill_file has trigger-style description"
    check_contains "$skill_file" "Canonical Sources" "$skill_file lists canonical sources"
    check_contains "core/skills/README.md" "\`$skill\`" "core/skills/README.md maps $skill"
  done
}

if [ ! -d ".agent" ] && [ -d "core/skills" ]; then
  validate_template_skills

  if [ "$failures" -gt 0 ]; then
    printf '\n%d template skill validation check(s) failed.\n' "$failures" >&2
    exit 1
  fi

  printf '\nAll template skill validation checks passed.\n'
  exit 0
fi

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

if [ -f ".github/PULL_REQUEST_TEMPLATE.md" ]; then
  check_contains ".github/PULL_REQUEST_TEMPLATE.md" "Problem observed" ".github/PULL_REQUEST_TEMPLATE.md includes problem observed section"
  check_contains ".github/PULL_REQUEST_TEMPLATE.md" "Gates run" ".github/PULL_REQUEST_TEMPLATE.md includes gates run section"
  check_contains ".github/PULL_REQUEST_TEMPLATE.md" "fabricated problem statements, speculative fixes, or bundled unrelated changes" ".github/PULL_REQUEST_TEMPLATE.md includes anti-slop warning"
else
  printf 'SKIP: .github/PULL_REQUEST_TEMPLATE.md not generated\n'
fi

if [ -f ".agent/workflows/worktree-workflow.md" ]; then
  check_contains ".agent/workflows/worktree-workflow.md" "optional acceleration" ".agent/workflows/worktree-workflow.md states opt-in behavior"
  check_contains ".agent/workflows/worktree-workflow.md" "Directory Priority" ".agent/workflows/worktree-workflow.md includes directory priority"
  check_contains ".agent/workflows/worktree-workflow.md" "Baseline Gate" ".agent/workflows/worktree-workflow.md includes baseline gate"
  check_contains ".agent/workflows/worktree-workflow.md" "When NOT To Use" ".agent/workflows/worktree-workflow.md includes when-not-to-use section"
else
  printf 'SKIP: .agent/workflows/worktree-workflow.md not generated\n'
fi

if [ "$failures" -gt 0 ]; then
  printf '\n%d validation check(s) failed.\n' "$failures" >&2
  exit 1
fi

printf '\nAll validation checks passed.\n'
