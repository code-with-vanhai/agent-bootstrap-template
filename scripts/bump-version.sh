#!/usr/bin/env bash
# Stage 2.1: bump all version sources + release-tags (see scripts/lib/bump_version.py).
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
exec python3 "$ROOT/scripts/lib/bump_version.py" --root "$ROOT" "$@"
