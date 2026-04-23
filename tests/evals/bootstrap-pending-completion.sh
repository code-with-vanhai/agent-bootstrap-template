#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
source "$SCRIPT_DIR/test-helpers.sh"

project_dir="$(mktemp -d "/tmp/bootstrap-pending-completion.XXXXXX")"
trap 'cleanup_test_project "$project_dir"' EXIT

cat > "$project_dir/package.json" <<'EOF'
{
  "name": "bootstrap-eval-fixture",
  "private": true,
  "scripts": {
    "test": "node --test",
    "lint": "eslint ."
  }
}
EOF

mkdir -p "$project_dir/src"
cat > "$project_dir/src/index.js" <<'EOF'
export function add(a, b) {
  return a + b;
}
EOF

(cd "$project_dir" && git init -q && git config user.email "eval@example.invalid" && git config user.name "Agent Eval" && git add . && git commit -q -m "initial target repo")

"$REPO_ROOT/scripts/bootstrap-request.sh" --features full --harness codex --target "$project_dir" >/dev/null

prompt="$(cat <<'EOF'
You are in a repository with an Agent Bootstrap Kit skeleton already generated.

User request: Complete .agent/bootstrap-pending.md.

Follow .agent/bootstrap-pending.md exactly. Read checked-in repository files before filling repo facts. Configure gates only from checked-in package/build/task/CI evidence. Do not modify business logic. Delete .agent/bootstrap-pending.md only after the generated agent system is complete and validation passes.
EOF
)"

output="$(run_claude "$prompt" "$project_dir" 2>&1 || true)"

if [ "$EVAL_VERBOSE" = "1" ]; then
  printf '%s\n' "$output"
fi

if [ ! -f "$project_dir/.agent/bootstrap-pending.md" ]; then
  pass "removes bootstrap pending file after completion"
else
  fail "removes bootstrap pending file after completion"
fi

if [ -f "$project_dir/.agent/manifest.json" ]; then
  if command -v jq >/dev/null 2>&1; then
    if jq . "$project_dir/.agent/manifest.json" >/dev/null; then
      pass "manifest remains valid JSON"
    else
      fail "manifest remains valid JSON"
    fi
  elif command -v python3 >/dev/null 2>&1; then
    if python3 -m json.tool "$project_dir/.agent/manifest.json" >/dev/null; then
      pass "manifest remains valid JSON"
    else
      fail "manifest remains valid JSON"
    fi
  else
    fail "manifest JSON cannot be checked because neither jq nor python3 is available"
  fi
else
  fail "manifest remains valid JSON"
fi

if (cd "$project_dir" && bash scripts/agent-validate.sh >/tmp/bootstrap-pending-validate.out 2>&1); then
  pass "generated validator passes after completion"
else
  fail "generated validator passes after completion"
  if [ "$EVAL_VERBOSE" = "1" ]; then
    cat /tmp/bootstrap-pending-validate.out >&2
  fi
fi

if grep -RIn '{{[^}]*}}' "$project_dir/.agent" "$project_dir/.agents" "$project_dir/AGENTS.md" "$project_dir/scripts" >/tmp/bootstrap-pending-placeholders.out 2>/dev/null; then
  fail "no placeholders remain after completion"
  if [ "$EVAL_VERBOSE" = "1" ]; then
    cat /tmp/bootstrap-pending-placeholders.out >&2
  fi
else
  pass "no placeholders remain after completion"
fi

changed_files="$(cd "$project_dir" && git status --porcelain | sed '/^$/d; s/^...//' | sort -u)"
if printf '%s\n' "$changed_files" | grep -Fxq "src/index.js"; then
  fail "does not modify business logic"
else
  pass "does not modify business logic"
fi

if [ -f "$project_dir/.agents/skills/agent-bootstrap/bootstrap-agent-system/SKILL.md" ]; then
  pass "bootstrap skill exists in generated codex skill output"
else
  fail "bootstrap skill exists in generated codex skill output"
fi

if [ -f "$project_dir/.agents/skills/agent-bootstrap/agent-plan/SKILL.md" ]; then
  pass "codex command wrapper skill exists in generated codex skill output"
else
  fail "codex command wrapper skill exists in generated codex skill output"
fi

finish_test
