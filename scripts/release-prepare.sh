#!/usr/bin/env bash
# Stage 3.4: scaffold mechanical release prep (see scripts/lib/release_prepare.py).
#
# Read-only by default (dry-run plan). With --apply, calls bump-version
# and patches the new CHANGELOG entry; never tags, fetches, or pushes.
#
# Usage:
#   scripts/release-prepare.sh                  # dry-run plan to stdout
#   scripts/release-prepare.sh --json           # machine-readable plan
#   scripts/release-prepare.sh --apply          # bump + patch CHANGELOG
#   scripts/release-prepare.sh --bump minor --apply
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
exec python3 "$ROOT/scripts/lib/release_prepare.py" --root "$ROOT" "$@"
