#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$ROOT"

mode="fast"
timeout_seconds="300"
verbose="0"
skip_on_missing_cli="1"
claude_bin="${CLAUDE_BIN:-claude}"

usage() {
  cat <<'EOF'
Usage: scripts/agent-evals.sh [--fast|--behavior|--integration] [--timeout <sec>] [--verbose] [--skip-on-missing-cli]

Runs headless evals for the agent-system template.

Mode semantics:
  --fast         Deterministic, free, reliable evals only (default).
                 No LLM calls. Safe to run on every commit / in CI.
  --behavior     LLM-driven advisory evals (call Claude CLI). Inherently
                 flaky; treat as advisory, NOT a release gate. Each run
                 consumes Claude quota.
  --integration  All known evals: deterministic + behavior + integration.
                 Heaviest mode; only run intentionally.

Other options:
  --timeout <sec>        Per-eval timeout in seconds (default: 300).
  --verbose              Show full Claude output from each eval.
  --skip-on-missing-cli  Exit 0 with SKIP if claude CLI is missing (default).
  -h, --help             Show this help.
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --fast)
      mode="fast"
      shift
      ;;
    --behavior)
      mode="behavior"
      shift
      ;;
    --integration)
      mode="integration"
      shift
      ;;
    --timeout)
      if [ "$#" -lt 2 ]; then
        printf 'Missing value for --timeout\n' >&2
        exit 2
      fi
      timeout_seconds="$2"
      shift 2
      ;;
    --verbose)
      verbose="1"
      shift
      ;;
    --skip-on-missing-cli)
      skip_on_missing_cli="1"
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      printf 'Unknown option: %s\n' "$1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

# Deterministic evals: no LLM calls, free, reliable. Safe in --fast / CI.
deterministic_evals=(
  "tests/evals/plugin-command-load.sh"
)

# Behavior evals: LLM-driven, advisory only. Each run costs Claude quota and
# is non-deterministic. Demoted out of --fast so a flaky LLM run does not
# masquerade as a release-gate failure.
behavior_evals=(
  "tests/evals/verify-before-claim.sh"
  "tests/evals/root-cause-first.sh"
  "tests/evals/no-invented-gates.sh"
  "tests/evals/plan-grounding.sh"
)

# Integration evals: also LLM-driven, advisory.
integration_evals=(
  "tests/evals/no-unrelated-changes.sh"
  "tests/evals/bootstrap-pending-completion.sh"
)

case "$mode" in
  fast)
    evals=("${deterministic_evals[@]}")
    needs_claude=0
    ;;
  behavior)
    evals=("${behavior_evals[@]}")
    needs_claude=1
    ;;
  integration)
    evals=("${deterministic_evals[@]}" "${behavior_evals[@]}" "${integration_evals[@]}")
    needs_claude=1
    ;;
  *)
    printf 'Internal error: unknown mode %q\n' "$mode" >&2
    exit 2
    ;;
esac

if [ "$needs_claude" = "1" ] && ! command -v "$claude_bin" >/dev/null 2>&1; then
  if [ "$skip_on_missing_cli" = "1" ]; then
    printf 'SKIP: %s CLI not found; LLM-driven evals were not run.\n' "$claude_bin"
    exit 0
  fi
  printf 'FAIL: %s CLI not found.\n' "$claude_bin" >&2
  exit 1
fi

failures=0
skipped=0

for eval_script in "${evals[@]}"; do
  if [ ! -x "$eval_script" ]; then
    printf 'SKIP: %s is not present or not executable.\n' "$eval_script"
    skipped=$((skipped + 1))
    continue
  fi

  printf '\n>>> %s\n' "$eval_script"
  set +e
  CLAUDE_BIN="$claude_bin" EVAL_TIMEOUT="$timeout_seconds" EVAL_VERBOSE="$verbose" "$eval_script"
  rc=$?
  set -e
  case "$rc" in
    0)
      printf 'PASS: %s\n' "$eval_script"
      ;;
    77)
      printf 'SKIP: %s (claude CLI unavailable)\n' "$eval_script"
      skipped=$((skipped + 1))
      ;;
    *)
      printf 'FAIL: %s\n' "$eval_script" >&2
      failures=$((failures + 1))
      ;;
  esac
done

if [ "$failures" -gt 0 ]; then
  if [ "$mode" = "behavior" ] || [ "$mode" = "integration" ]; then
    printf '\n%d eval(s) failed in mode=%s. LLM-driven evals are advisory; do NOT block release on this alone.\n' "$failures" "$mode" >&2
  else
    printf '\n%d eval(s) failed in mode=%s.\n' "$failures" "$mode" >&2
  fi
  exit 1
fi

if [ "$skipped" -gt 0 ]; then
  printf '\nEvals (mode=%s): %d skipped (claude CLI unavailable or quota exhausted); remaining passed.\n' "$mode" "$skipped"
else
  printf '\nAll selected evals passed (mode=%s).\n' "$mode"
fi
