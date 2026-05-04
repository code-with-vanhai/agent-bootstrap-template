#!/usr/bin/env bash
# Deterministic Codex-harness eval. Asserts that
#   scripts/bootstrap-request.sh --harness codex --features full
# produces the expected SKILL.md tree under .agents/skills/agent-bootstrap/
# in the bootstrapped target.
#
# This eval invokes NO LLM CLI. It is a pure filesystem check intended to
# run in --fast mode. The expected list of skills/commands is computed at
# runtime from core/skills/ and core/commands/, so adding a future entry
# does not break this eval as long as bootstrap-request.sh keeps copying
# them.
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$ROOT"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=tests/evals/test-helpers.sh
source "$SCRIPT_DIR/test-helpers.sh"

target_dir="$(mktemp -d "/tmp/codex-harness-fixture.XXXXXX")"
trap 'rm -rf "$target_dir"' EXIT

# Run bootstrap-request in dry-quiet mode. We need real writes for the
# assertions, so no --dry-run.
"$ROOT/scripts/bootstrap-request.sh" \
  --harness codex \
  --features full \
  --target "$target_dir" \
  >/dev/null 2>&1 || {
    printf 'FAIL: bootstrap-request.sh --harness codex --features full failed.\n' >&2
    exit 1
  }

skills_root="$target_dir/.agents/skills/agent-bootstrap"

if [ ! -d "$skills_root" ]; then
  printf 'FAIL: %s missing after bootstrap (codex skill destination).\n' "$skills_root" >&2
  exit 1
fi

# --- Skills (one per directory under core/skills/, excluding README) ---
expected_skills=0
missing_skills=0
for skill_dir in "$ROOT"/core/skills/*/; do
  skill_name="$(basename "$skill_dir")"
  expected="$skills_root/$skill_name/SKILL.md"
  expected_skills=$((expected_skills + 1))
  if [ ! -f "$expected" ]; then
    fail "skill SKILL.md missing: .agents/skills/agent-bootstrap/$skill_name/SKILL.md"
    missing_skills=$((missing_skills + 1))
  fi
done

if [ "$missing_skills" -eq 0 ]; then
  pass "all $expected_skills core/skills/<name>/SKILL.md copied to .agents/skills/agent-bootstrap/<name>/SKILL.md"
fi

# --- Codex command skills (one agent-<command> per core/commands/<cmd>.md) ---
# Skip commands whose generation is gated behind an opt-in bootstrap flag
# (see scripts/lib/bootstrap/copy_mcp.sh). The default bootstrap path in
# this eval does NOT enable those flags, so we filter them out here and
# rely on tests/evals/mcp-discovery-fixture.sh to exercise the opt-in path.
expected_commands=0
missing_commands=0
for command_file in "$ROOT"/core/commands/*.md; do
  command_name="$(basename "$command_file" .md)"
  case "$command_name" in
    mcp-discover)
      continue
      ;;
  esac
  expected="$skills_root/agent-$command_name/SKILL.md"
  expected_commands=$((expected_commands + 1))
  if [ ! -f "$expected" ]; then
    fail "codex command-skill missing: .agents/skills/agent-bootstrap/agent-$command_name/SKILL.md"
    missing_commands=$((missing_commands + 1))
  fi
done

if [ "$missing_commands" -eq 0 ]; then
  pass "all $expected_commands core/commands/<cmd>.md generated agent-<cmd>/SKILL.md under codex harness"
fi

finish_test
