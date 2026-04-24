#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
TEMPLATE_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

if ! command -v python3 >/dev/null 2>&1; then
  printf 'ERROR: python3 is required for agent sync.\n' >&2
  exit 2
fi

exec python3 "$SCRIPT_DIR/agent-sync.py" --template-root "$TEMPLATE_ROOT" "$@"
