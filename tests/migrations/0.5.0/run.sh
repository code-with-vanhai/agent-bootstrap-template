#!/usr/bin/env bash
# Migration regression test for 0.4.0 -> 0.5.0.
#
# Strategy:
#   1. Build a genuine 0.4.0 fixture by copying the canonical 0.3.0
#      post-migration fixture and syncing it through the production 0.4.0
#      migration first.
#   2. Commit that 0.4.0 fixture before applying 0.5.0. agent-sync.py
#      rejects dirty worktrees unless --allow-dirty is passed, and this test
#      should exercise the normal clean-target path.
#   3. Apply 0.5.0 and assert the no-op contract: only the manifest and the
#      unconditional sync log entry change.

set -euo pipefail

root="$(git rev-parse --show-toplevel)"
work_root="$(mktemp -d /tmp/migration-0.5.0.XXXXXX)"

ephemeral_v032_created="0"
ephemeral_v040_created="0"
ephemeral_v050_created="0"
cleanup() {
  if [ "$ephemeral_v050_created" = "1" ]; then
    git -C "$root" tag -d v0.5.0 >/dev/null 2>&1 || true
  fi
  if [ "$ephemeral_v040_created" = "1" ]; then
    git -C "$root" tag -d v0.4.0 >/dev/null 2>&1 || true
  fi
  if [ "$ephemeral_v032_created" = "1" ]; then
    git -C "$root" tag -d v0.3.2 >/dev/null 2>&1 || true
  fi
  rm -rf "$work_root"
}
trap cleanup EXIT

ensure_tag() {
  version="$1"
  commit="$2"
  created_var="$3"

  if git -C "$root" rev-parse --verify --quiet "v$version^{commit}" >/dev/null; then
    return 0
  fi
  if ! git -C "$root" rev-parse --verify --quiet "$commit^{commit}" >/dev/null; then
    printf 'FAIL: v%s tag missing AND commit %s is not reachable locally.\n' "$version" "$commit" >&2
    printf '      Run `git fetch --tags` and retry.\n' >&2
    exit 1
  fi
  git -C "$root" tag "v$version" "$commit"
  eval "$created_var=1"
}

# Required by the 0.4.0 setup migration preflight.
ensure_tag "0.3.2" "499eb163bdc4cf5de39f7572a538af418828be4c" "ephemeral_v032_created"
ensure_tag "0.4.0" "2bb93a0602fb4f2af4b325ceff20c6b88ff49972" "ephemeral_v040_created"

# Required by the 0.5.0 migration preflight while the release commit is still
# in progress. The real maintainer-created tag replaces this after merge.
if ! git -C "$root" rev-parse --verify --quiet "v0.5.0^{commit}" >/dev/null; then
  git -C "$root" tag v0.5.0
  ephemeral_v050_created="1"
fi

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

setup_040_fixture() {
  # All progress / sync output inside this function is redirected to
  # stderr so the function's stdout contains exactly one line: the
  # fixture path. Callers capture the path via command substitution.
  fixture_dir="$work_root/clean-from-0.4.0"
  cp -a "$root/tests/migrations/0.3.0/after/." "$fixture_dir/" >&2
  (
    cd "$fixture_dir"
    git init -q
    git -c user.email=t@t -c user.name=Test add .
    git -c user.email=t@t -c user.name=Test commit -q -m "fixture@0.3.0"
  ) >&2

  AGENT_SYNC_NOW=2026-04-27T00:00:00Z \
    "$root/scripts/agent-sync.sh" --target "$fixture_dir" --to 0.4.0 --apply >&2

  assert_file_contains "$fixture_dir/.agent/manifest.json" '"template_version": "0.4.0"' \
    "[setup] manifest template_version=0.4.0" >&2
  assert_file_contains "$fixture_dir/.agent/manifest.json" '"synced_to_template_version": "0.4.0"' \
    "[setup] manifest synced_to=0.4.0" >&2

  (
    cd "$fixture_dir"
    git -c user.email=t@t -c user.name=Test add .
    git -c user.email=t@t -c user.name=Test commit -q -m "fixture@0.4.0"
  ) >&2
  printf '%s\n' "$fixture_dir"
}

fixture="$(setup_040_fixture)"

AGENT_SYNC_NOW=2026-04-28T00:00:00Z \
  "$root/scripts/agent-sync.sh" --target "$fixture" --to 0.5.0 --apply

assert_file_contains "$fixture/.agent/manifest.json" '"template_version": "0.5.0"' \
  "[clean-from-0.4.0] manifest template_version=0.5.0"
assert_file_contains "$fixture/.agent/manifest.json" '"synced_to_template_version": "0.5.0"' \
  "[clean-from-0.4.0] manifest synced_to=0.5.0"
assert_file_contains "$fixture/.agent/manifest.json" "AGENT_LLM_PROVIDER" \
  "[clean-from-0.4.0] manifest release note mentions provider env"
assert_file_contains "$fixture/.agent/sync-log.md" "Sync to 0.5.0" \
  "[clean-from-0.4.0] sync log appended"

actual_status="$(git -C "$fixture" status --short | LC_ALL=C sort)"
expected_status="$(printf ' M .agent/manifest.json\n M .agent/sync-log.md')"
if [ "$actual_status" != "$expected_status" ]; then
  printf 'FAIL: [clean-from-0.4.0] no-op contract changed unexpected paths\n' >&2
  printf 'Expected:\n%s\n' "$expected_status" >&2
  printf 'Actual:\n%s\n' "$actual_status" >&2
  exit 1
fi
printf 'PASS: [clean-from-0.4.0] only manifest and sync-log changed\n'

(
  cd "$fixture"
  git -c user.email=t@t -c user.name=Test add .
  git -c user.email=t@t -c user.name=Test commit -q -m "first 0.5.0 apply"
)

AGENT_SYNC_NOW=2026-04-28T00:00:00Z \
  "$root/scripts/agent-sync.sh" --target "$fixture" --to 0.5.0 --apply

if [ -n "$(git -C "$fixture" status --short)" ]; then
  git -C "$fixture" status --short
  printf 'FAIL: [clean-from-0.4.0] re-apply produced changes\n' >&2
  exit 1
fi
printf 'PASS: [clean-from-0.4.0] idempotent re-apply\n'

printf '\nAll 0.5.0 migration assertions passed.\n'
