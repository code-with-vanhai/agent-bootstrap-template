#!/usr/bin/env bash
# Plan discipline command: validates `.agent/runs/<slug>/plan.md` and `spec.md`.
#
# This is NOT a gate mode (see core/gates.template.md). It enforces plan-level
# grounding, banned self-claims, lint pack patterns, required sections,
# decision-lock checks, and AC verification taxonomy.
#
# Usage:
#   scripts/agent-validate-plan.sh <plan.md | .agent/runs/<slug>/>
#   scripts/agent-validate-plan.sh --strict <target>
#   scripts/agent-validate-plan.sh --format github <target>
#
# Exit codes:
#   0  no High failures (Medium failures only emit warnings unless --strict)
#   1  at least one High failure, OR any Medium failure under --strict
#   2  usage error or missing target

set -euo pipefail

if ! command -v python3 >/dev/null 2>&1; then
  printf 'ERROR: python3 is required for agent-validate-plan.sh\n' >&2
  exit 2
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LIB_DIR="$SCRIPT_DIR/lib"

if [ ! -f "$LIB_DIR/validate_plan.py" ]; then
  printf 'ERROR: missing %s\n' "$LIB_DIR/validate_plan.py" >&2
  exit 2
fi

exec python3 "$LIB_DIR/validate_plan.py" "$@"
