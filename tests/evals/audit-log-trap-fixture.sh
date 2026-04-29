#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$ROOT"

target_dir="$(mktemp -d "/tmp/audit-log-trap-fixture.XXXXXX")"
cleanup() {
  rm -rf "$target_dir"
}
trap cleanup EXIT

"$ROOT/scripts/bootstrap-request.sh" \
  --harness generic \
  --features standard \
  --target "$target_dir" \
  >/dev/null 2>&1

set +e
(
  cd "$target_dir"
  bash scripts/agent-eval.sh fast
) >/tmp/audit-log-trap-fast.out 2>&1
fast_rc=$?
set -e

if [ "$fast_rc" -ne 2 ]; then
  printf 'FAIL: fast gate should remain not_configured with exit 2, got %s\n' "$fast_rc" >&2
  cat /tmp/audit-log-trap-fast.out >&2
  exit 1
fi

log_path="$target_dir/.agent/audit-log.jsonl"
if [ ! -f "$log_path" ]; then
  printf 'FAIL: audit log was not created at %s\n' "$log_path" >&2
  exit 1
fi

python3 - "$log_path" <<'PY'
import json
import sys
from pathlib import Path

records = [json.loads(line) for line in Path(sys.argv[1]).read_text(encoding="utf-8").splitlines()]
if len(records) != 1:
    raise SystemExit(f"expected 1 record, got {len(records)}")
record = records[0]
expected = {
    "v": 1,
    "kind": "gate_run",
    "actor": "scripts/agent-eval.sh",
    "gate": "fast",
    "exit_code": 2,
}
for key, value in expected.items():
    if record.get(key) != value:
        raise SystemExit(f"expected {key}={value!r}, got {record.get(key)!r}")
if not isinstance(record.get("duration_ms"), int) or record["duration_ms"] < 0:
    raise SystemExit("duration_ms must be a non-negative integer")
PY

bad_plan_dir="$target_dir/.agent/runs/bad-plan"
mkdir -p "$bad_plan_dir"
printf '# Plan\n\n(missing required sections)\n' >"$bad_plan_dir/plan.md"
set +e
(
  cd "$target_dir"
  bash scripts/agent-validate-plan.sh --force --strict "$bad_plan_dir"
) >/tmp/audit-log-trap-plan.out 2>&1
plan_rc=$?
set -e
if [ "$plan_rc" -ne 1 ]; then
  printf 'FAIL: bad plan validation should exit 1, got %s\n' "$plan_rc" >&2
  cat /tmp/audit-log-trap-plan.out >&2
  exit 1
fi

python3 - "$log_path" <<'PY'
import json
import sys
from pathlib import Path

records = [json.loads(line) for line in Path(sys.argv[1]).read_text(encoding="utf-8").splitlines()]
if len(records) != 2:
    raise SystemExit(f"expected 2 records after plan validation, got {len(records)}")
record = records[-1]
if record.get("kind") != "plan_validation":
    raise SystemExit(f"expected plan_validation record, got {record.get('kind')!r}")
if record.get("exit_code") != 1:
    raise SystemExit(f"expected exit_code=1, got {record.get('exit_code')!r}")
if record.get("strict") is not True:
    raise SystemExit(f"expected strict=true, got {record.get('strict')!r}")
if record.get("high") != 1 or record.get("medium") != 0:
    raise SystemExit(f"expected high=1 and medium=0, got high={record.get('high')!r} medium={record.get('medium')!r}")
PY

touch "$target_dir/.agent/audit-log.disabled"
set +e
(
  cd "$target_dir"
  bash scripts/agent-eval.sh fast
) >/tmp/audit-log-trap-disabled.out 2>&1
disabled_rc=$?
set -e
if [ "$disabled_rc" -ne 2 ]; then
  printf 'FAIL: disabled fast gate should still exit 2, got %s\n' "$disabled_rc" >&2
  cat /tmp/audit-log-trap-disabled.out >&2
  exit 1
fi

line_count="$(wc -l <"$log_path" | tr -d ' ')"
if [ "$line_count" != "2" ]; then
  printf 'FAIL: opt-out sentinel should prevent additional audit lines, got %s lines\n' "$line_count" >&2
  exit 1
fi

printf 'PASS: audit-log trap records gate/plan exits and respects opt-out sentinel.\n'
