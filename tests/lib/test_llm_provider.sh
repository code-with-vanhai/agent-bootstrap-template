#!/usr/bin/env bash
# Unit tests for scripts/lib/llm_provider.sh (PR-2: claude + codex).
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
assert_true  'codex is known (PR-2)'     llm_provider_is_known codex
assert_false 'foobar is unknown'         llm_provider_is_known foobar
assert_false 'empty arg is unknown'      llm_provider_is_known ''

# ---------------------------------------------------------------------------
# llm_provider_default_bin
# ---------------------------------------------------------------------------
printf '\n[group] llm_provider_default_bin\n'
assert_equals 'claude default bin is "claude"' \
  'claude' "$(llm_provider_default_bin claude)"
assert_equals 'codex default bin is "codex" (PR-2)' \
  'codex' "$(llm_provider_default_bin codex)"
assert_false 'unknown provider default_bin returns 1' \
  llm_provider_default_bin foobar

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

(
  unset CODEX_BIN
  bin="$(llm_provider_bin codex)"
  [ "$bin" = "codex" ]
) && printf '  PASS: codex bin defaults to "codex" when CODEX_BIN unset\n' \
  || { printf '  FAIL: codex default bin without env\n' >&2; failures=$((failures + 1)); }
tests_run=$((tests_run + 1))

(
  CODEX_BIN="/tmp/custom-codex"
  bin="$(llm_provider_bin codex)"
  [ "$bin" = "/tmp/custom-codex" ]
) && printf '  PASS: CODEX_BIN env overrides default bin\n' \
  || { printf '  FAIL: CODEX_BIN env override\n' >&2; failures=$((failures + 1)); }
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
# llm_provider_is_unavailable codex — every known variant matches
# ---------------------------------------------------------------------------
printf '\n[group] llm_provider_is_unavailable codex (positive)\n'

CODEX_QUOTA_SAMPLES=(
  "Error: rate limit exceeded for organization"
  "usage limit reached for this account"
  "quota exceeded; please upgrade"
  "insufficient credits to complete request"
  "insufficient quota: contact billing"
  "Invalid API key provided"
  "authentication error: token expired"
  "authentication failed: please log in"
  "please sign in to continue"
  "please log in to continue"
  "HTTP 401 Unauthorized"
  "HTTP status 403 forbidden"
  "HTTP 429: too many requests"
  "too many requests, retry later"
)

for sample in "${CODEX_QUOTA_SAMPLES[@]}"; do
  assert_true "matches: ${sample:0:48}..." \
    llm_provider_is_unavailable codex "$sample"
done

# ---------------------------------------------------------------------------
# llm_provider_is_unavailable codex — benign output does NOT match
# ---------------------------------------------------------------------------
printf '\n[group] llm_provider_is_unavailable codex (negative)\n'

CODEX_BENIGN_SAMPLES=(
  "All assertions passed; ready to merge."
  "Reading AGENTS.md before planning."
  ""
)

for sample in "${CODEX_BENIGN_SAMPLES[@]}"; do
  assert_false "does NOT match: ${sample:0:48}..." \
    llm_provider_is_unavailable codex "$sample"
done

# ---------------------------------------------------------------------------
# llm_provider_run codex with mock bin actually invokes the bin AND uses
# the documented flag set: exec --skip-git-repo-check --color never
# --sandbox workspace-write [CODEX_EXTRA_ARGS] <prompt>
# ---------------------------------------------------------------------------
printf '\n[group] llm_provider_run codex (mock bin invocation)\n'
mock_codex="$(mktemp)"
cat > "$mock_codex" <<'EOF'
#!/usr/bin/env bash
# Echo back the full argv so the caller can assert on flag set + ordering.
printf 'argv:'
for a in "$@"; do printf ' [%s]' "$a"; done
printf '\n'
exit 0
EOF
chmod +x "$mock_codex"

(
  CODEX_BIN="$mock_codex"
  unset CODEX_EXTRA_ARGS
  out="$(llm_provider_run codex 'hello prompt' "$PWD" 2>&1)"
  case "$out" in
    *'[exec]'*'[--skip-git-repo-check]'*'[--color]'*'[never]'*'[--sandbox]'*'[workspace-write]'*'[hello prompt]'*) exit 0 ;;
    *) printf '%s\n' "$out" >&2; exit 1 ;;
  esac
) && printf '  PASS: codex invocation uses exec + skip-git-repo-check + color never + sandbox workspace-write\n' \
  || { printf '  FAIL: codex invocation argv check\n' >&2; failures=$((failures + 1)); }
tests_run=$((tests_run + 1))

# Verify CODEX_EXTRA_ARGS is positioned BEFORE the prompt (review #3).
(
  CODEX_BIN="$mock_codex"
  CODEX_EXTRA_ARGS="--config sandbox=read-only"
  out="$(llm_provider_run codex 'PROMPT_TOKEN' "$PWD" 2>&1)"
  # Expected ordering: ... [--sandbox] [workspace-write] [--config] [sandbox=read-only] [PROMPT_TOKEN]
  case "$out" in
    *'[--config]'*'[sandbox=read-only]'*'[PROMPT_TOKEN]'*) exit 0 ;;
    *) printf '%s\n' "$out" >&2; exit 1 ;;
  esac
) && printf '  PASS: CODEX_EXTRA_ARGS appears BEFORE the prompt (review #3)\n' \
  || { printf '  FAIL: CODEX_EXTRA_ARGS placement\n' >&2; failures=$((failures + 1)); }
tests_run=$((tests_run + 1))
rm -f "$mock_codex"

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
printf '\n----\n%d test(s) run, %d failure(s).\n' "$tests_run" "$failures"

if [ "$failures" -gt 0 ]; then
  exit 1
fi
exit 0
