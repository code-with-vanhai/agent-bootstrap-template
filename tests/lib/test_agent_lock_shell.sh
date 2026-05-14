#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$ROOT"

work_root="$(mktemp -d /tmp/agent-lock-shell.XXXXXX)"
cleanup() {
  rm -rf "$work_root"
}
trap cleanup EXIT

assert_empty_locks() {
  if find "$work_root/.agent/locks" -type f -name '*.lock.json' 2>/dev/null | grep . >/dev/null; then
    find "$work_root/.agent/locks" -type f -name '*.lock.json' >&2
    printf 'FAIL: lock files remained\n' >&2
    exit 1
  fi
}

normal_out="$(bash scripts/agent-lock.sh run --root "$work_root" --paths 'src/test/**' --task normal -- echo done)"
if [ "$normal_out" != "done" ]; then
  printf 'FAIL: normal run output mismatch: %s\n' "$normal_out" >&2
  exit 1
fi
assert_empty_locks

set +e
bash scripts/agent-lock.sh run --root "$work_root" --paths 'src/test/**' --task signal -- bash -c 'kill -INT $$; exit 130' >/tmp/agent-lock-signal.out 2>&1
signal_rc=$?
set -e
if [ "$signal_rc" -eq 0 ]; then
  cat /tmp/agent-lock-signal.out >&2
  printf 'FAIL: signalled command should exit non-zero\n' >&2
  exit 1
fi
assert_empty_locks

session="$(bash scripts/agent-lock.sh acquire --root "$work_root" --paths 'src/test/**' --task held)"
set +e
bash scripts/agent-lock.sh run --root "$work_root" --paths 'src/test/file.ts' --task conflict -- echo no >/tmp/agent-lock-conflict.out 2>&1
conflict_rc=$?
set -e
if [ "$conflict_rc" -ne 1 ]; then
  cat /tmp/agent-lock-conflict.out >&2
  printf 'FAIL: overlap run should exit 1, got %s\n' "$conflict_rc" >&2
  exit 1
fi
bash scripts/agent-lock.sh release --root "$work_root" --session-id "$session"
assert_empty_locks

printf 'PASS: agent-lock shell wrapper normal, signal, and overlap paths passed.\n'
