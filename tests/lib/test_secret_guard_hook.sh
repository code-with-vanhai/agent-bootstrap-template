#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

HOOK="$ROOT/core/hooks/pre-tool-use-secret-guard.py.template"

if [ ! -f "$HOOK" ]; then
  printf 'FAIL: hook template missing at %s\n' "$HOOK" >&2
  exit 1
fi

work="$(mktemp -d /tmp/agent-secret-guard-test.XXXXXX)"
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

# Case 1: Edit on .env -> deny JSON, exit 0.
run_hook '{"tool_name":"Edit","tool_input":{"file_path":".env"}}'
assert_exit_zero "deny .env"
assert_stdout_contains "deny .env" '"permissionDecision": "deny"'
assert_stdout_contains "deny .env" '"hookEventName": "PreToolUse"'
assert_stdout_contains "deny .env" '.env is protected'

# Case 2: Edit on src/foo.ts -> allow (no stdout).
run_hook '{"tool_name":"Edit","tool_input":{"file_path":"src/foo.ts"}}'
assert_exit_zero "allow src/foo.ts"
assert_no_stdout "allow src/foo.ts"

# Case 3: Read on .env -> non-write tool passes through.
run_hook '{"tool_name":"Read","tool_input":{"file_path":".env"}}'
assert_exit_zero "Read .env passthrough"
assert_no_stdout "Read .env passthrough"

# Case 4: Malformed JSON -> fail-open.
run_hook 'not json at all'
assert_exit_zero "malformed JSON"
assert_no_stdout "malformed JSON"

# Case 5: Empty stdin -> fail-open.
run_hook ''
assert_exit_zero "empty stdin"
assert_no_stdout "empty stdin"

# Case 6: Edit on .env with tool_input.content secret -> deny without leaking content.
SECRET="SUPERSECRET_TOKEN_DO_NOT_LEAK"
run_hook "{\"tool_name\":\"Edit\",\"tool_input\":{\"file_path\":\".env\",\"content\":\"$SECRET\"}}"
assert_exit_zero "no content leak"
assert_stdout_contains "no content leak" '"permissionDecision": "deny"'
assert_stdout_not_contains "no content leak" "$SECRET"

# Case 7: MultiEdit on .agent/rulebase.md -> deny.
run_hook '{"tool_name":"MultiEdit","tool_input":{"file_path":".agent/rulebase.md"}}'
assert_exit_zero "deny rulebase"
assert_stdout_contains "deny rulebase" '"permissionDecision": "deny"'
assert_stdout_contains "deny rulebase" '.agent/rulebase.md is protected'

# Case 8: Write on path with secrets/ segment -> deny.
run_hook '{"tool_name":"Write","tool_input":{"file_path":"infra/secrets/api.key"}}'
assert_exit_zero "deny secrets segment"
assert_stdout_contains "deny secrets segment" '"permissionDecision": "deny"'

# Case 9: Edit on .env.production -> deny via prefix match.
run_hook '{"tool_name":"Edit","tool_input":{"file_path":".env.production"}}'
assert_exit_zero "deny .env.production"
assert_stdout_contains "deny .env.production" '"permissionDecision": "deny"'

# Case 10: Edit with tool_input.path (alternate field) -> deny.
run_hook '{"tool_name":"Edit","tool_input":{"path":"credentials.json"}}'
assert_exit_zero "deny via path field"
assert_stdout_contains "deny via path field" '"permissionDecision": "deny"'

# Case 11: Edit on README.md -> allow.
run_hook '{"tool_name":"Edit","tool_input":{"file_path":"README.md"}}'
assert_exit_zero "allow README.md"
assert_no_stdout "allow README.md"

# Case 12: Bash tool -> non-write passthrough even on protected path.
run_hook '{"tool_name":"Bash","tool_input":{"command":"cat .env"}}'
assert_exit_zero "Bash passthrough"
assert_no_stdout "Bash passthrough"

printf 'PASS: secret-guard hook contract verified across %s cases.\n' 12
