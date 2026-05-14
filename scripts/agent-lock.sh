#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
LOCK_CLI="$SCRIPT_DIR/lib/agent_lock.py"

if ! command -v python3 >/dev/null 2>&1; then
  printf 'ERROR: python3 is required for agent-lock.sh\n' >&2
  exit 2
fi

if [ ! -f "$LOCK_CLI" ]; then
  printf 'ERROR: missing %s\n' "$LOCK_CLI" >&2
  exit 2
fi

usage() {
  printf 'Usage: %s <acquire|release|list|prune|check-overlap|run> [options]\n' "$0" >&2
}

release_via_python() {
  python3 "$LOCK_CLI" release --root "$lock_root" --session-id "$session_id" >/dev/null 2>&1
}

cmd="${1:-}"
if [ -z "$cmd" ]; then
  usage
  exit 2
fi
shift

case "$cmd" in
  acquire|release|list|prune|check-overlap)
    exec python3 "$LOCK_CLI" "$cmd" "$@"
    ;;
  run)
    paths=""
    task="agent task"
    ttl_minutes="60"
    lock_root="$ROOT"
    while [ "$#" -gt 0 ]; do
      case "$1" in
        --paths)
          paths="${2:-}"
          shift 2
          ;;
        --task)
          task="${2:-}"
          shift 2
          ;;
        --ttl-minutes)
          ttl_minutes="${2:-}"
          shift 2
          ;;
        --root)
          lock_root="${2:-}"
          shift 2
          ;;
        --)
          shift
          break
          ;;
        *)
          printf 'ERROR: unsupported run option: %s\n' "$1" >&2
          exit 2
          ;;
      esac
    done
    if [ -z "$paths" ]; then
      printf 'ERROR: run requires --paths\n' >&2
      exit 2
    fi
    if [ "$#" -eq 0 ]; then
      printf 'ERROR: run requires a command after --\n' >&2
      exit 2
    fi

    session_id="$(python3 "$LOCK_CLI" acquire \
      --root "$lock_root" \
      --paths "$paths" \
      --task "$task" \
      --ttl-minutes "$ttl_minutes")"

    rc=0
    cleanup() {
      trap - EXIT INT TERM HUP
      release_via_python || true
      exit "$rc"
    }
    trap cleanup EXIT INT TERM HUP

    set +e
    "$@"
    rc=$?
    set -e
    cleanup
    ;;
  *)
    usage
    exit 2
    ;;
esac
