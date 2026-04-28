#!/usr/bin/env bash
# Unit tests for scripts/lib/llm_provider.sh (PR-1: claude branch only).
#
# Tiny inline assert harness — no bats dependency. Returns 0 on success,
# 1 on first failure with a descriptive message.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# shellcheck source=../scripts/lib/llm_provider.sh
. "$REPO_ROOT/scripts/lib/llm_provider.sh"

# Required by _llm_invoke_claude when timeout is available.
EVAL_TIMEOUT="${EVAL_TIMEOUT:-5}"

failures=0
tests_run=0

assert_true() {
  description="$1"
  shift
  tests_run=$((tests_run + 1))
  if "$@"; then
    printf '  PASS: %s\n' "$description"
  else
    printf '  FAIL: %s\n' "$description" >&2
    failures=$((failures + 1))
  fi
}

assert_false() {
  description="$1"
  shift
  tests_run=$((tests_run + 1))
  if "$@"; then
    printf '  FAIL: %s (expected non-zero)\n' "$description" >&2
    failures=$((failures + 1))
  else
    printf '  PASS: %s\n' "$description"
  fi
}

assert_equals() {
  description="$1"
  expected="$2"
  actual="$3"
  tests_run=$((tests_run + 1))
  if [ "$expected" = "$actual" ]; then
    printf '  PASS: %s\n' "$description"
  else
    printf '  FAIL: %s\n    expected: %q\n    actual:   %q\n' \
      "$description" "$expected" "$actual" >&2
    failures=$((failures + 1))
  fi
}

# ---------------------------------------------------------------------------
# llm_provider_is_known
# ---------------------------------------------------------------------------
printf '\n[group] llm_provider_is_known\n'
assert_true  'claude is known'           llm_provider_is_known claude
assert_false 'codex is NOT known in PR-1' llm_provider_is_known codex
assert_false 'foobar is unknown'         llm_provider_is_known foobar
assert_false 'empty arg is unknown'      llm_provider_is_known ''

# ---------------------------------------------------------------------------
# llm_provider_default_bin
# ---------------------------------------------------------------------------
printf '\n[group] llm_provider_default_bin\n'
assert_equals 'claude default bin is "claude"' \
  'claude' "$(llm_provider_default_bin claude)"
assert_false 'codex default bin returns 1 (PR-1)' \
  llm_provider_default_bin codex

# ---------------------------------------------------------------------------
# llm_provider_bin (env override)
# ---------------------------------------------------------------------------
printf '\n[group] llm_provider_bin\n'
(
  unset CLAUDE_BIN
  bin="$(llm_provider_bin claude)"
  [ "$bin" = "claude" ]
) && printf '  PASS: claude bin defaults to "claude" when CLAUDE_BIN unset\n' \
  || { printf '  FAIL: claude default bin without env\n' >&2; failures=$((failures + 1)); }
tests_run=$((tests_run + 1))

(
  CLAUDE_BIN="/tmp/custom-claude"
  bin="$(llm_provider_bin claude)"
  [ "$bin" = "/tmp/custom-claude" ]
) && printf '  PASS: CLAUDE_BIN env overrides default bin\n' \
  || { printf '  FAIL: CLAUDE_BIN env override\n' >&2; failures=$((failures + 1)); }
tests_run=$((tests_run + 1))

# ---------------------------------------------------------------------------
# llm_provider_is_unavailable claude — every known variant matches
# ---------------------------------------------------------------------------
printf '\n[group] llm_provider_is_unavailable claude (positive)\n'

CLAUDE_QUOTA_SAMPLES=(
  "You've hit your limit · resets 8pm (Asia/Bangkok)"
  "You've hit your monthly usage limit"
  "Usage limit reached. Try again later."
  "Rate limit exceeded"
  "Invalid API key provided"
  "Authentication failed: please log in"
  "Please log in to continue"
  "Your credit balance is too low to access the service"
  "Quota exceeded for organization"
  "API error 401 Unauthorized"
  "API error 403 forbidden"
  "API error 429 Too Many Requests"
)

for sample in "${CLAUDE_QUOTA_SAMPLES[@]}"; do
  assert_true "matches: ${sample:0:48}..." \
    llm_provider_is_unavailable claude "$sample"
done

# ---------------------------------------------------------------------------
# llm_provider_is_unavailable claude — benign output does NOT match
# ---------------------------------------------------------------------------
printf '\n[group] llm_provider_is_unavailable claude (negative)\n'

CLAUDE_BENIGN_SAMPLES=(
  "tests pass and ready to merge"
  "Here is the requested code change."
  "I will read AGENTS.md and .agent/rulebase.md first."
  ""
)

for sample in "${CLAUDE_BENIGN_SAMPLES[@]}"; do
  assert_false "does NOT match: ${sample:0:48}..." \
    llm_provider_is_unavailable claude "$sample"
done

# ---------------------------------------------------------------------------
# llm_provider_run unknown -> exit 2 with stderr message
# ---------------------------------------------------------------------------
printf '\n[group] llm_provider_run unknown\n'
unknown_stderr="$(llm_provider_run foobar 'prompt' "$PWD" 2>&1 >/dev/null)" || rc=$?
rc="${rc:-0}"
assert_equals 'unknown provider exits 2' '2' "$rc"
case "$unknown_stderr" in
  *"Unknown LLM provider: foobar"*)
    printf '  PASS: stderr contains "Unknown LLM provider: foobar"\n'
    ;;
  *)
    printf '  FAIL: stderr did not include the unknown-provider message\n    actual: %q\n' \
      "$unknown_stderr" >&2
    failures=$((failures + 1))
    ;;
esac
tests_run=$((tests_run + 1))

# ---------------------------------------------------------------------------
# llm_provider_run claude with mock bin actually invokes the bin
# ---------------------------------------------------------------------------
printf '\n[group] llm_provider_run claude (mock bin invocation)\n'
mock_bin="$(mktemp)"
cat > "$mock_bin" <<'EOF'
#!/usr/bin/env bash
printf 'mock-claude-output\n'
exit 0
EOF
chmod +x "$mock_bin"

(
  CLAUDE_BIN="$mock_bin"
  out="$(llm_provider_run claude 'hello' "$PWD" 2>&1)"
  [ "$out" = "mock-claude-output" ]
) && printf '  PASS: llm_provider_run claude executes CLAUDE_BIN with -p prompt\n' \
  || { printf '  FAIL: mock CLAUDE_BIN invocation\n' >&2; failures=$((failures + 1)); }
tests_run=$((tests_run + 1))
rm -f "$mock_bin"

# ---------------------------------------------------------------------------
# Codex branch is intentionally absent in PR-1
# ---------------------------------------------------------------------------
printf '\n[group] codex branch (PR-1 stub)\n'
codex_stderr="$(llm_provider_run codex 'p' "$PWD" 2>&1 >/dev/null)" || codex_rc=$?
codex_rc="${codex_rc:-0}"
assert_equals 'codex run returns 2 in PR-1' '2' "$codex_rc"
case "$codex_stderr" in
  *"Unknown LLM provider: codex"*)
    printf '  PASS: codex stderr is "Unknown LLM provider: codex" (PR-2 will replace)\n'
    ;;
  *)
    printf '  FAIL: codex stderr unexpected\n    actual: %q\n' "$codex_stderr" >&2
    failures=$((failures + 1))
    ;;
esac
tests_run=$((tests_run + 1))

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
printf '\n----\n%d test(s) run, %d failure(s).\n' "$tests_run" "$failures"

if [ "$failures" -gt 0 ]; then
  exit 1
fi
exit 0
