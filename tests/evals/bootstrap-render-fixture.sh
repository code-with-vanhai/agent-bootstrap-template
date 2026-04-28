#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
TEMPLATE_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

project_dir="$(mktemp -d "/tmp/agent render &.XXXXXX")"
cleanup() {
  rm -rf "$project_dir"
}
trap cleanup EXIT

(
  cd "$project_dir"
  git init -q
  git config user.email "eval@example.invalid"
  git config user.name "Agent Eval"
)

"$TEMPLATE_ROOT/scripts/bootstrap-request.sh" \
  --template "$TEMPLATE_ROOT" \
  --target "$project_dir" \
  --features standard \
  --harness generic >/tmp/bootstrap-render-fixture.out

python3 -m json.tool "$project_dir/.agent/manifest.json" >/dev/null

if grep -RIn '{{[A-Z][A-Z0-9_]*}}' "$project_dir/.agent" "$project_dir/scripts" >/tmp/bootstrap-render-placeholders.out 2>&1; then
  printf 'FAIL: placeholders remain after bootstrap rendering\n' >&2
  cat /tmp/bootstrap-render-placeholders.out >&2
  exit 1
fi

if ! grep -q 'agent render &' "$project_dir/.agent/manifest.json"; then
  printf 'FAIL: generated repo name with ampersand was not rendered literally\n' >&2
  exit 1
fi

if [ ! -x "$project_dir/scripts/agent-gate-discover.sh" ] || [ ! -f "$project_dir/scripts/lib/gate_discovery.py" ]; then
  printf 'FAIL: gate discovery wrapper or library was not copied into generated repo\n' >&2
  exit 1
fi

if [ ! -f "$project_dir/scripts/lib/plan_validation/cli.py" ] || [ ! -f "$project_dir/scripts/lib/plan_validation/validator.py" ]; then
  printf 'FAIL: modular plan validator package was not copied into generated repo\n' >&2
  exit 1
fi

if [ ! -f "$project_dir/scripts/lib/validate_agent_system.py" ]; then
  printf 'FAIL: structured agent-system validator was not copied into generated repo\n' >&2
  exit 1
fi

printf 'PASS: bootstrap rendering handles special-character target path and leaves valid manifest.\n'
