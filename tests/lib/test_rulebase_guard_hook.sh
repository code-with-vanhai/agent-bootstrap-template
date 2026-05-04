#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

HOOK="$ROOT/core/hooks/pre-tool-use-rulebase-guard.py.template"

if [ ! -f "$HOOK" ]; then
  printf 'FAIL: hook template missing at %s\n' "$HOOK" >&2
  exit 1
fi

work="$(mktemp -d /tmp/agent-rulebase-guard-test.XXXXXX)"
cleanup() {
  rm -rf "$work"
}
trap cleanup EXIT

run_hook() {
  payload="$1"
  out_file="$work/out.json"
  err_file="$work/err.txt"
  printf '%s' "$payload" | python3 "$HOOK" >"$out_file" 2>"$err_file"
  exit_code="$?"
  printf '%s\n' "$exit_code" >"$work/exit"
}

assert_exit_zero() {
  case_label="$1"
  if [ "$(cat "$work/exit")" != "0" ]; then
    printf 'FAIL: %s expected exit 0, got %s\n' "$case_label" "$(cat "$work/exit")" >&2
    cat "$work/err.txt" >&2
    exit 1
  fi
}

assert_no_stdout() {
  case_label="$1"
  if [ -s "$work/out.json" ]; then
    printf 'FAIL: %s expected no stdout, got:\n' "$case_label" >&2
    cat "$work/out.json" >&2
    exit 1
  fi
}

assert_stdout_contains() {
  case_label="$1"
  needle="$2"
  if ! grep -q -- "$needle" "$work/out.json"; then
    printf 'FAIL: %s stdout missing %s\n' "$case_label" "$needle" >&2
    cat "$work/out.json" >&2
    exit 1
  fi
}

assert_stdout_not_contains() {
  case_label="$1"
  needle="$2"
  if grep -q -- "$needle" "$work/out.json"; then
    printf 'FAIL: %s stdout unexpectedly contains %s\n' "$case_label" "$needle" >&2
    cat "$work/out.json" >&2
    exit 1
  fi
}

# Case 1: Edit on .agent/constitution.md -> deny JSON, exit 0.
run_hook '{"tool_name":"Edit","tool_input":{"file_path":".agent/constitution.md"}}'
assert_exit_zero "deny constitution"
assert_stdout_contains "deny constitution" '"permissionDecision": "deny"'
assert_stdout_contains "deny constitution" '"hookEventName": "PreToolUse"'
assert_stdout_contains "deny constitution" '.agent/constitution.md is protected'
assert_stdout_contains "deny constitution" 'non-negotiable'

# Case 2: Write on .agent/rulebase.md -> ask JSON, exit 0.
run_hook '{"tool_name":"Write","tool_input":{"file_path":".agent/rulebase.md"}}'
assert_exit_zero "ask rulebase"
assert_stdout_contains "ask rulebase" '"permissionDecision": "ask"'
assert_stdout_contains "ask rulebase" 'rule-evolution-workflow.md'

# Case 3: MultiEdit on .agent/constitution.md via absolute path -> still denies.
run_hook '{"tool_name":"MultiEdit","tool_input":{"file_path":"/workspace/repo/.agent/constitution.md"}}'
assert_exit_zero "deny constitution absolute"
assert_stdout_contains "deny constitution absolute" '"permissionDecision": "deny"'

# Case 4: Write on docs/spec.md -> allow (no stdout).
run_hook '{"tool_name":"Write","tool_input":{"file_path":"docs/spec.md"}}'
assert_exit_zero "allow docs/spec.md"
assert_no_stdout "allow docs/spec.md"

# Case 5: Read on .agent/constitution.md -> non-write tool passes through.
run_hook '{"tool_name":"Read","tool_input":{"file_path":".agent/constitution.md"}}'
assert_exit_zero "Read constitution passthrough"
assert_no_stdout "Read constitution passthrough"

# Case 6: Bash tool with command targeting constitution -> non-write, allow.
run_hook '{"tool_name":"Bash","tool_input":{"command":"sed -i s/foo/bar/ .agent/constitution.md"}}'
assert_exit_zero "Bash passthrough"
assert_no_stdout "Bash passthrough"

# Case 7: Malformed JSON -> fail-open.
run_hook 'not json at all'
assert_exit_zero "malformed JSON"
assert_no_stdout "malformed JSON"

# Case 8: Empty stdin -> fail-open.
run_hook ''
assert_exit_zero "empty stdin"
assert_no_stdout "empty stdin"

# Case 9: Unknown schema (missing tool_input) -> fail-open.
run_hook '{"tool_name":"Edit"}'
assert_exit_zero "missing tool_input fail-open"
assert_no_stdout "missing tool_input fail-open"

# Case 10: Edit on .agent/constitution.md with tool_input.content secret ->
# deny without leaking content.
SECRET="DO_NOT_LEAK_CONSTITUTION_DRAFT"
run_hook "{\"tool_name\":\"Edit\",\"tool_input\":{\"file_path\":\".agent/constitution.md\",\"content\":\"$SECRET\"}}"
assert_exit_zero "no content leak"
assert_stdout_contains "no content leak" '"permissionDecision": "deny"'
assert_stdout_not_contains "no content leak" "$SECRET"

# Case 11: Edit using tool_input.path (alternate field) on rulebase -> ask.
run_hook '{"tool_name":"Edit","tool_input":{"path":".agent/rulebase.md"}}'
assert_exit_zero "ask via path field"
assert_stdout_contains "ask via path field" '"permissionDecision": "ask"'

# Case 12: tool_input.file_path is non-string -> fail-open.
run_hook '{"tool_name":"Edit","tool_input":{"file_path":123}}'
assert_exit_zero "non-string path fail-open"
assert_no_stdout "non-string path fail-open"

# Case 13: payload not a dict (top-level array) -> fail-open.
run_hook '[]'
assert_exit_zero "array payload fail-open"
assert_no_stdout "array payload fail-open"

# Case 14: Edit on file ending in different `constitution.md` (not under
# `.agent/`) -> allow.  Suffix matching must require the leading `.agent/`.
run_hook '{"tool_name":"Edit","tool_input":{"file_path":"docs/constitution.md"}}'
assert_exit_zero "unrelated constitution allowed"
assert_no_stdout "unrelated constitution allowed"

printf 'PASS: rulebase-guard hook contract verified across %s cases.\n' 14
