#!/usr/bin/env bash
# Plan discipline command: validates `.agent/runs/<slug>/plan.md` and `spec.md`.
#
# This is NOT a gate mode (see core/gates.template.md). It enforces plan-level
# grounding, banned self-claims, lint pack patterns, required sections,
# decision-lock checks, conditional plan tables, risk mitigations, and AC
# verification taxonomy.
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

if ! command -v python3 >/dev/null 2>/dev/null; then
  printf 'ERROR: python3 is required for agent-validate-plan.sh\n' >&2
  exit 2
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LIB_DIR="$SCRIPT_DIR/lib"

if [ ! -f "$LIB_DIR/validate_plan.py" ]; then
  printf 'ERROR: missing %s\n' "$LIB_DIR/validate_plan.py" >&2
  exit 2
fi

format="human"
strict="false"
target_arg=""
expect_value_for=""
for arg in "$@"; do
  if [ -n "$expect_value_for" ]; then
    if [ "$expect_value_for" = "format" ]; then
      format="$arg"
    fi
    expect_value_for=""
    continue
  fi

  case "$arg" in
    --format)
      expect_value_for="format"
      ;;
    --format=*)
      format="${arg#--format=}"
      ;;
    --strict)
      strict="true"
      ;;
    --repo-root)
      expect_value_for="repo-root"
      ;;
    --repo-root=*|--force)
      ;;
    --*)
      ;;
    *)
      target_arg="$arg"
      ;;
  esac
done

if ! out_file="$(mktemp 2>/dev/null)"; then
  exec python3 "$LIB_DIR/validate_plan.py" "$@"
fi
if ! err_file="$(mktemp 2>/dev/null)"; then
  rm -f "$out_file"
  exec python3 "$LIB_DIR/validate_plan.py" "$@"
fi

cleanup() {
  rm -f "$out_file" "$err_file"
}
trap cleanup EXIT INT TERM

set +e
python3 "$LIB_DIR/validate_plan.py" "$@" >"$out_file" 2>"$err_file"
exit_code=$?
set -e

cat "$out_file" || true
cat "$err_file" >&2 || true

audit_args=(
  --kind plan_validation
  --actor scripts/agent-validate-plan.sh
  --field "target=${target_arg:-not provided}"
  --field "exit_code=$exit_code"
  --field "strict=$strict"
)

if [ "$format" = "human" ]; then
  summary_line="$(grep -E '^Summary: [0-9]+ High, [0-9]+ Medium' "$out_file" | tail -n 1 || true)"
  if [ -n "$summary_line" ]; then
    high_count="$(printf '%s\n' "$summary_line" | sed -E 's/^Summary: ([0-9]+) High, ([0-9]+) Medium.*/\1/')"
    medium_count="$(printf '%s\n' "$summary_line" | sed -E 's/^Summary: ([0-9]+) High, ([0-9]+) Medium.*/\2/')"
    audit_args+=(--field "high=$high_count" --field "medium=$medium_count")
  fi
fi

if [ -x "$SCRIPT_DIR/agent-audit-log.sh" ]; then
  "$SCRIPT_DIR/agent-audit-log.sh" "${audit_args[@]}" || true
fi

exit "$exit_code"
