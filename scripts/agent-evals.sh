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
Usage: scripts/agent-evals.sh [--fast|--integration] [--timeout <sec>] [--verbose] [--skip-on-missing-cli]

Runs headless behavior evals for the agent-system template.

Options:
  --fast                 Run fast evals only (default).
  --integration          Run fast evals plus integration evals.
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

if ! command -v "$claude_bin" >/dev/null 2>&1; then
  if [ "$skip_on_missing_cli" = "1" ]; then
    printf 'SKIP: %s CLI not found; behavior evals were not run.\n' "$claude_bin"
    exit 0
  fi
  printf 'FAIL: %s CLI not found.\n' "$claude_bin" >&2
  exit 1
fi

fast_evals=(
  "tests/evals/plugin-command-load.sh"
  "tests/evals/verify-before-claim.sh"
  "tests/evals/root-cause-first.sh"
  "tests/evals/no-invented-gates.sh"
)

integration_evals=(
  "tests/evals/no-unrelated-changes.sh"
  "tests/evals/bootstrap-pending-completion.sh"
)

evals=("${fast_evals[@]}")
if [ "$mode" = "integration" ]; then
  evals+=("${integration_evals[@]}")
fi

failures=0

for eval_script in "${evals[@]}"; do
  if [ ! -x "$eval_script" ]; then
    printf 'SKIP: %s is not present or not executable.\n' "$eval_script"
    continue
  fi

  printf '\n>>> %s\n' "$eval_script"
  if CLAUDE_BIN="$claude_bin" EVAL_TIMEOUT="$timeout_seconds" EVAL_VERBOSE="$verbose" "$eval_script"; then
    printf 'PASS: %s\n' "$eval_script"
  else
    printf 'FAIL: %s\n' "$eval_script" >&2
    failures=$((failures + 1))
  fi
done

if [ "$failures" -gt 0 ]; then
  printf '\n%d behavior eval(s) failed.\n' "$failures" >&2
  exit 1
fi

printf '\nAll selected behavior evals passed or were skipped.\n'
