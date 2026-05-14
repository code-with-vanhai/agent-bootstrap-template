#!/usr/bin/env bash
set -euo pipefail

if ! command -v python3 >/dev/null 2>&1; then
  printf 'ERROR: python3 is required for agent-validate.sh\n' >&2
  exit 2
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="${AGENT_ROOT:-$(cd "$SCRIPT_DIR/.." && pwd)}"
VALIDATOR="$SCRIPT_DIR/lib/validate_agent_system.py"
CHANGED_ONLY=0

if [ "${1:-}" = "--changed-only" ]; then
  CHANGED_ONLY=1
  shift
fi

if [ ! -f "$VALIDATOR" ]; then
  printf 'ERROR: missing %s\n' "$VALIDATOR" >&2
  exit 2
fi

if [ "$CHANGED_ONLY" = "1" ]; then
  requested_mode="auto"
  previous=""
  for arg in "$@"; do
    if [ "$previous" = "--mode" ]; then
      requested_mode="$arg"
      previous=""
      continue
    fi
    case "$arg" in
      --mode=*) requested_mode="${arg#--mode=}" ;;
      --mode) previous="--mode" ;;
      *) previous="" ;;
    esac
  done

  if [ "$requested_mode" != "template" ] && { [ "$requested_mode" = "generated" ] || [ ! -f "$ROOT/core/gate-modes.json" ]; }; then
    base_ref="${AGENT_VALIDATE_BASE_REF:-HEAD~1}"
    set +e
    (
      cd "$ROOT"
      python3 -m scripts.lib.agent_system_validation.monitored_paths diff-quiet \
        --root "$ROOT" \
        --base "$base_ref"
    )
    diff_rc=$?
    set -e
    if [ "$diff_rc" -eq 0 ]; then
      printf 'No monitored agent-system changes since %s; skipping validation.\n' "$base_ref"
      exit 0
    fi
    if [ "$diff_rc" -gt 1 ]; then
      printf 'WARNING: could not diff monitored agent-system paths against %s; running full validation.\n' "$base_ref" >&2
    fi
  fi
fi

exec python3 "$VALIDATOR" "$@"
