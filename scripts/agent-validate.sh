#!/usr/bin/env bash
set -euo pipefail

if ! command -v python3 >/dev/null 2>&1; then
  printf 'ERROR: python3 is required for agent-validate.sh\n' >&2
  exit 2
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VALIDATOR="$SCRIPT_DIR/lib/validate_agent_system.py"

if [ ! -f "$VALIDATOR" ]; then
  printf 'ERROR: missing %s\n' "$VALIDATOR" >&2
  exit 2
fi

exec python3 "$VALIDATOR" "$@"
