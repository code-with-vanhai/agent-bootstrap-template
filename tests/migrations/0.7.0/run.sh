#!/usr/bin/env bash
# Migration regression test for 0.6.0 -> 0.7.0.
#
# Strategy:
#   1. Build a genuine 0.6.0 fixture by syncing the canonical 0.3.0
#      post-migration fixture through 0.4.0, 0.5.0, and 0.6.0 first.
#   2. Commit the 0.6.0 fixture before applying 0.7.0 so the normal clean
#      target preflight is exercised.
#   3. Apply 0.7.0 and assert the downstream planning discipline files,
#      validator, manifest, sync log, and idempotent re-apply behavior.

set -euo pipefail

root="$(git rev-parse --show-toplevel)"
work_root="$(mktemp -d /tmp/migration-0.7.0.XXXXXX)"

ephemeral_v032_created="0"
ephemeral_v040_created="0"
ephemeral_v050_created="0"
ephemeral_v060_created="0"
ephemeral_v070_created="0"

cleanup() {
  if [ "$ephemeral_v070_created" = "1" ]; then
    git -C "$root" tag -d v0.7.0 >/dev/null 2>&1 || true
  fi
  if [ "$ephemeral_v060_created" = "1" ]; then
    git -C "$root" tag -d v0.6.0 >/dev/null 2>&1 || true
  fi
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

# Required by setup migrations and 0.7.0 preflight.
ensure_tag "0.3.2" "499eb163bdc4cf5de39f7572a538af418828be4c" "ephemeral_v032_created"
ensure_tag "0.4.0" "2bb93a0ea9870eccdba1c195f7e65ed367a58ed7" "ephemeral_v040_created"
ensure_tag "0.5.0" "3900230d548852696fd39b6745fe05f08179c7fb" "ephemeral_v050_created"
ensure_tag "0.6.0" "264b0661a80c235dfd2a3b63078d2e45cbc3b8ce" "ephemeral_v060_created"

# Required while the 0.7.0 release commit is in progress. The maintainer-created
# annotated tag replaces this after review.
if ! git -C "$root" rev-parse --verify --quiet "v0.7.0^{commit}" >/dev/null; then
  git -C "$root" tag v0.7.0
  ephemeral_v070_created="1"
fi

setup_060_fixture() {
  fixture_dir="$work_root/clean-from-0.6.0"
  cp -a "$root/tests/migrations/0.3.0/after/." "$fixture_dir/" >&2
  (
    cd "$fixture_dir"
    git init -q
    git -c user.email=t@t -c user.name=Test add .
    git -c user.email=t@t -c user.name=Test commit -q -m "fixture@0.3.0"
  ) >&2

  AGENT_SYNC_NOW=2026-04-27T00:00:00Z \
    "$root/scripts/agent-sync.sh" --target "$fixture_dir" --to 0.4.0 --apply >&2
  (
    cd "$fixture_dir"
    git -c user.email=t@t -c user.name=Test add .
    git -c user.email=t@t -c user.name=Test commit -q -m "fixture@0.4.0"
  ) >&2

  AGENT_SYNC_NOW=2026-04-28T00:00:00Z \
    "$root/scripts/agent-sync.sh" --target "$fixture_dir" --to 0.5.0 --apply >&2
  (
    cd "$fixture_dir"
    git -c user.email=t@t -c user.name=Test add .
    git -c user.email=t@t -c user.name=Test commit -q -m "fixture@0.5.0"
  ) >&2

  AGENT_SYNC_NOW=2026-04-28T01:00:00Z \
    "$root/scripts/agent-sync.sh" --target "$fixture_dir" --to 0.6.0 --apply >&2

  assert_file_contains "$fixture_dir/.agent/manifest.json" '"template_version": "0.6.0"' \
    "[setup] manifest template_version=0.6.0" >&2
  assert_file_contains "$fixture_dir/.agent/manifest.json" '"synced_to_template_version": "0.6.0"' \
    "[setup] manifest synced_to=0.6.0" >&2

  (
    cd "$fixture_dir"
    git -c user.email=t@t -c user.name=Test add .
    git -c user.email=t@t -c user.name=Test commit -q -m "fixture@0.6.0"
  ) >&2
  printf '%s\n' "$fixture_dir"
}

fixture="$(setup_060_fixture)"

AGENT_SYNC_NOW=2026-04-28T02:00:00Z \
  "$root/scripts/agent-sync.sh" --target "$fixture" --to 0.7.0 --apply

assert_file_contains "$fixture/.agent/manifest.json" '"template_version": "0.7.0"' \
  "[clean-from-0.6.0] manifest template_version=0.7.0"
assert_file_contains "$fixture/.agent/manifest.json" '"synced_to_template_version": "0.7.0"' \
  "[clean-from-0.6.0] manifest synced_to=0.7.0"
assert_file_contains "$fixture/.agent/manifest.json" "semantic Decision Ledger enforcement" \
  "[clean-from-0.6.0] manifest release note mentions Decision Ledger"
assert_file_contains "$fixture/.agent/sync-log.md" "Sync to 0.7.0" \
  "[clean-from-0.6.0] sync log appended"

assert_file_contains "$fixture/.agent/commands/plan.md" "Decision Ledger" \
  "[clean-from-0.6.0] plan command requires Decision Ledger when triggered"
assert_file_contains "$fixture/.agent/workflows/feature-workflow.md" "0.7.0 addendum" \
  "[clean-from-0.6.0] feature workflow documents 0.7.0 addendum"
assert_file_contains "$fixture/.agent/roles/planner.md" "Use a \`Decision Ledger\` section" \
  "[clean-from-0.6.0] planner Decision Ledger section"
assert_file_contains "$fixture/.agent/roles/prompts/planner-subagent.md" "Do not put unchanged literals or threshold constants" \
  "[clean-from-0.6.0] planner subagent narrows Contract Value Table"
assert_file_contains "$fixture/.agent/workflows/review-workflow.md" "During the correctness pass, check the \`Decision Ledger\`" \
  "[clean-from-0.6.0] review workflow checks Decision Ledger"
assert_file_contains "$fixture/scripts/lib/validate_plan.py" "DEC-001" \
  "[clean-from-0.6.0] validator includes DEC-001"
assert_file_contains "$fixture/scripts/lib/validate_plan.py" "CVT-003" \
  "[clean-from-0.6.0] validator includes CVT-003"

actual_status="$(git -C "$fixture" status --short | LC_ALL=C sort)"
expected_status="$(cat <<'EOF'
 M .agent/commands/plan.md
 M .agent/manifest.json
 M .agent/roles/planner.md
 M .agent/roles/prompts/planner-subagent.md
 M .agent/sync-log.md
 M .agent/workflows/feature-workflow.md
 M .agent/workflows/review-workflow.md
 M scripts/lib/validate_plan.py
EOF
)"
if [ "$actual_status" != "$expected_status" ]; then
  printf 'FAIL: [clean-from-0.6.0] unexpected migration paths\n' >&2
  printf 'Expected:\n%s\n' "$expected_status" >&2
  printf 'Actual:\n%s\n' "$actual_status" >&2
  exit 1
fi
printf 'PASS: [clean-from-0.6.0] expected files changed\n'

(
  cd "$fixture"
  git -c user.email=t@t -c user.name=Test add .
  git -c user.email=t@t -c user.name=Test commit -q -m "first 0.7.0 apply"
)

AGENT_SYNC_NOW=2026-04-28T02:00:00Z \
  "$root/scripts/agent-sync.sh" --target "$fixture" --to 0.7.0 --apply

if [ -n "$(git -C "$fixture" status --short)" ]; then
  git -C "$fixture" status --short
  printf 'FAIL: [clean-from-0.6.0] re-apply produced changes\n' >&2
  exit 1
fi
printf 'PASS: [clean-from-0.6.0] idempotent re-apply\n'

printf '\nAll 0.7.0 migration assertions passed.\n'
