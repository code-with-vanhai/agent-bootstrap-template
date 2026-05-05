#!/usr/bin/env bash
# Migration regression test for 0.10.0 -> 0.11.0 (D-11 Option A backfill).
#
# 0.11.0 is a no-op data migration: it only refreshes manifest sync
# metadata so synced_to_template_version / synced_to_template_commit do
# not stay stale (per scripts/lib/agent_sync/manifest_ops.py:55).
#
# Strategy mirrors tests/migrations/0.5.0/run.sh: build a 0.10.0 fixture
# from the canonical 0.3.0 baseline via multi-hop, commit, then assert
# the no-op contract (only manifest + sync-log change) and idempotency.

set -euo pipefail

root="$(git rev-parse --show-toplevel)"
work_root="$(mktemp -d /tmp/migration-0.11.0.XXXXXX)"
trap 'rm -rf "$work_root"' EXIT

assert_file_contains() {
  path="$1"
  needle="$2"
  desc="$3"
  if grep -qF -- "$needle" "$path"; then
    printf 'PASS: %s\n' "$desc"
  else
    printf 'FAIL: %s\n  file=%s\n  needle=%s\n' "$desc" "$path" "$needle" >&2
    exit 1
  fi
}

if ! git -C "$root" rev-parse --verify --quiet "v0.10.0^{commit}" >/dev/null; then
  printf 'SKIP: v0.10.0 tag is missing; cannot build the 0.10.0 baseline.\n'
  exit 0
fi
if ! git -C "$root" rev-parse --verify --quiet "v0.11.0^{commit}" >/dev/null; then
  printf 'SKIP: v0.11.0 tag is missing; cannot resolve theirs for 0.11.0 hop.\n'
  exit 0
fi

remove_pycache() { find "$1" -type d -name __pycache__ -prune -exec rm -rf {} +; }

setup_0100_fixture() {
  fixture_dir="$work_root/clean-from-0.10.0"
  cp -a "$root/tests/migrations/0.3.0/after/." "$fixture_dir/" >&2
  (
    cd "$fixture_dir"
    git init -q
    git -c user.email=t@t -c user.name=Test add .
    git -c user.email=t@t -c user.name=Test commit -q -m "fixture@0.3.0"
  ) >&2

  AGENT_SYNC_NOW=2026-05-04T00:00:00Z \
    "$root/scripts/agent-sync.sh" --multi-hop --target "$fixture_dir" --to 0.10.0 --apply \
      --accept-theirs scripts/agent-eval.sh >&2

  remove_pycache "$fixture_dir"
  (
    cd "$fixture_dir"
    git -c user.email=t@t -c user.name=Test add .
    git -c user.email=t@t -c user.name=Test commit -q -m "fixture@0.10.0"
  ) >&2

  assert_file_contains "$fixture_dir/.agent/manifest.json" '"template_version": "0.10.0"' \
    "[setup] manifest template_version=0.10.0" >&2
  assert_file_contains "$fixture_dir/.agent/manifest.json" '"synced_to_template_version": "0.10.0"' \
    "[setup] manifest synced_to=0.10.0" >&2

  printf '%s\n' "$fixture_dir"
}

fixture="$(setup_0100_fixture)"

AGENT_SYNC_NOW=2026-05-05T00:00:00Z \
  "$root/scripts/agent-sync.sh" --target "$fixture" --to 0.11.0 --apply
remove_pycache "$fixture"

# Manifest must bump cleanly (D-11 specifically guards against empty
# manifest_updates leaving these stale).
assert_file_contains "$fixture/.agent/manifest.json" '"template_version": "0.11.0"' \
  "[clean-from-0.10.0] manifest template_version=0.11.0"
assert_file_contains "$fixture/.agent/manifest.json" '"synced_to_template_version": "0.11.0"' \
  "[clean-from-0.10.0] manifest synced_to=0.11.0"
assert_file_contains "$fixture/.agent/manifest.json" '"synced_to_template_commit"' \
  "[clean-from-0.10.0] manifest carries synced_to_template_commit"
assert_file_contains "$fixture/.agent/sync-log.md" "Sync to 0.11.0" \
  "[clean-from-0.10.0] sync log appended"
assert_file_contains "$fixture/.agent/manifest.json" \
  "Synced to v0.11.0 (no downstream-facing changes)." \
  "[clean-from-0.10.0] manifest release note appended"

# No-op contract: only manifest and sync-log changed (mirrors
# tests/migrations/0.5.0/run.sh:119).
actual_status="$(git -C "$fixture" status --short | LC_ALL=C sort)"
expected_status="$(printf ' M .agent/manifest.json\n M .agent/sync-log.md')"
if [ "$actual_status" != "$expected_status" ]; then
  printf 'FAIL: [clean-from-0.10.0] no-op contract changed unexpected paths\n' >&2
  printf 'Expected:\n%s\n' "$expected_status" >&2
  printf 'Actual:\n%s\n' "$actual_status" >&2
  exit 1
fi
printf 'PASS: [clean-from-0.10.0] only manifest and sync-log changed\n'

(
  cd "$fixture"
  git -c user.email=t@t -c user.name=Test add .
  git -c user.email=t@t -c user.name=Test commit -q -m "first 0.11.0 apply"
)

# Idempotent re-apply must be a clean no-op (current-version shortcut).
AGENT_SYNC_NOW=2026-05-05T00:00:00Z \
  "$root/scripts/agent-sync.sh" --target "$fixture" --to 0.11.0 --apply
remove_pycache "$fixture"

if [ -n "$(git -C "$fixture" status --short)" ]; then
  git -C "$fixture" status --short
  printf 'FAIL: [clean-from-0.10.0] re-apply produced changes\n' >&2
  exit 1
fi
printf 'PASS: [clean-from-0.10.0] idempotent re-apply\n'

printf '\nAll 0.11.0 migration assertions passed.\n'
