#!/usr/bin/env bash
# Stage 3.4: scaffold a schema-v1 migration.json from a tag diff under core/.
#
# Read-only: never tags, fetches, pushes, or rewrites refs. The Python
# helper enforces this; the wrapper is a thin pass-through that locates
# the template root so callers can run it from any cwd.
#
# Usage:
#   scripts/scaffold-migration.sh <from> <to>                # print to stdout
#   scripts/scaffold-migration.sh <from> <to> --write        # write skeleton
#   scripts/scaffold-migration.sh <from> <to> --write --force
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
exec python3 "$ROOT/scripts/lib/scaffold_migration.py" --template-root "$ROOT" "$@"
