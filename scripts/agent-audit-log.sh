#!/usr/bin/env bash
# Best-effort audit-log wrapper. Runtime callers must keep their own exit code.

set -u

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
WRITER="$SCRIPT_DIR/lib/audit_log.py"

if ! command -v python3 >/dev/null 2>&1; then
  exit 0
fi

if [ ! -f "$WRITER" ]; then
  exit 0
fi

python3 "$WRITER" append --root "$ROOT" "$@" || true
exit 0
