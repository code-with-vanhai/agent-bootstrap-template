#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$ROOT"

claude_bin="${CLAUDE_BIN:-claude}"
timeout_seconds="${EVAL_TIMEOUT:-30}"

# Phase 1 eval only: verify Claude Code loads plugin commands from the
# canonical custom path. This intentionally invokes a fake plugin-prefixed
# command so no model behavior or command prompt execution is required.
# The debug-log wording below is known to match Claude Code 2.1.117.

if ! command -v timeout >/dev/null 2>&1; then
  printf 'SKIP: timeout command not found; plugin command load eval was not run.\n'
  exit 0
fi

debug_file="$(mktemp)"
output_file="$(mktemp)"

cleanup() {
  rm -f "$debug_file" "$output_file"
}
trap cleanup EXIT

set +e
timeout "$timeout_seconds" "$claude_bin" \
  --plugin-dir "$ROOT" \
  --debug-file "$debug_file" \
  --print "/agent-bootstrap:__command_load_probe" \
  >"$output_file" 2>&1
status="$?"
set -e

if [ "$status" = "124" ]; then
  printf 'FAIL: Claude command load probe timed out after %s seconds.\n' "$timeout_seconds" >&2
  exit 1
fi

if grep -Eq 'Loaded [0-9]+ commands from plugin agent-bootstrap custom path: .*/core/commands' "$debug_file"; then
  printf 'PASS: Claude plugin loads commands from core/commands.\n'
  exit 0
fi

printf 'FAIL: Claude plugin did not report loading commands from core/commands.\n' >&2
printf '\n--- Claude output ---\n' >&2
sed -n '1,120p' "$output_file" >&2
printf '\n--- Debug excerpt ---\n' >&2
grep -E 'agent-bootstrap|commands|plugin' "$debug_file" >&2 || true
exit 1
