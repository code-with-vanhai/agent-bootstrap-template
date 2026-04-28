#!/usr/bin/env bash
# Migration regression test for 0.7.0 -> 0.8.0.

set -euo pipefail

root="$(git rev-parse --show-toplevel)"
work_root="$(mktemp -d /tmp/migration-0.8.0.XXXXXX)"

ephemeral_v080_created="0"

cleanup() {
  if [ "$ephemeral_v080_created" = "1" ]; then
    git -C "$root" tag -d v0.8.0 >/dev/null 2>&1 || true
  fi
  rm -rf "$work_root"
}
trap cleanup EXIT

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

ensure_current_release_tag() {
  if git -C "$root" rev-parse --verify --quiet "v0.8.0^{commit}" >/dev/null; then
    return 0
  fi
  if ! git -C "$root" diff --quiet -- \
    core/migrations/0.8.0 \
    scripts/agent-validate.sh \
    scripts/agent-gate-discover.sh \
    scripts/agent-eval.template.sh \
    scripts/lib/validate_agent_system.py \
    scripts/lib/gate_discovery.py \
    scripts/lib/validate_plan.py \
    scripts/lib/plan_validation; then
    printf 'SKIP: v0.8.0 tag is missing and 0.8.0 migration sources are not committed yet.\n'
    exit 0
  fi
  git -C "$root" tag v0.8.0
  ephemeral_v080_created="1"
}

setup_070_fixture() {
  fixture_dir="$work_root/clean-from-0.7.0"
  cp -a "$root/tests/migrations/0.3.0/after/." "$fixture_dir/" >&2
  (
    cd "$fixture_dir"
    git init -q
    git -c user.email=t@t -c user.name=Test add .
    git -c user.email=t@t -c user.name=Test commit -q -m "fixture@0.3.0"
  ) >&2

  for version in 0.4.0 0.5.0 0.6.0 0.7.0; do
    AGENT_SYNC_NOW="2026-04-28T03:00:00Z" \
      "$root/scripts/agent-sync.sh" --target "$fixture_dir" --to "$version" --apply >&2
    (
      cd "$fixture_dir"
      git -c user.email=t@t -c user.name=Test add .
      git -c user.email=t@t -c user.name=Test commit -q -m "fixture@$version"
    ) >&2
  done

  assert_file_contains "$fixture_dir/.agent/manifest.json" '"template_version": "0.7.0"' \
    "[setup] manifest template_version=0.7.0" >&2
  printf '%s\n' "$fixture_dir"
}

ensure_current_release_tag
fixture="$(setup_070_fixture)"

AGENT_SYNC_NOW=2026-04-28T04:00:00Z \
  "$root/scripts/agent-sync.sh" --target "$fixture" --to 0.8.0 --apply

assert_file_contains "$fixture/.agent/manifest.json" '"template_version": "0.8.0"' \
  "[clean-from-0.7.0] manifest template_version=0.8.0"
assert_file_contains "$fixture/.agent/manifest.json" '"synced_to_template_version": "0.8.0"' \
  "[clean-from-0.7.0] manifest synced_to=0.8.0"
assert_file_contains "$fixture/.agent/sync-log.md" "Sync to 0.8.0" \
  "[clean-from-0.7.0] sync log appended"

assert_file_contains "$fixture/scripts/agent-validate.sh" "validate_agent_system.py" \
  "[clean-from-0.7.0] structured validator wrapper installed"
assert_file_contains "$fixture/scripts/lib/validate_agent_system.py" "class AgentSystemValidator" \
  "[clean-from-0.7.0] structured validator helper installed"
assert_file_contains "$fixture/scripts/agent-gate-discover.sh" "gate_discovery.py" \
  "[clean-from-0.7.0] gate discovery wrapper installed"
assert_file_contains "$fixture/scripts/lib/gate_discovery.py" "status=\"candidate\"" \
  "[clean-from-0.7.0] gate discovery helper installed"
assert_file_contains "$fixture/scripts/lib/validate_plan.py" "Compatibility wrapper" \
  "[clean-from-0.7.0] validate_plan compatibility wrapper installed"
assert_file_contains "$fixture/scripts/lib/plan_validation/validator.py" "def validate_plan" \
  "[clean-from-0.7.0] modular plan validator package installed"
assert_file_contains "$fixture/scripts/agent-eval.sh" "gitleaks dir" \
  "[clean-from-0.7.0] security gate scanner path installed"
assert_file_contains "$fixture/.agent/gates.md" "gate-suggestions.json" \
  "[clean-from-0.7.0] gates document candidate suggestions"
assert_file_contains "$fixture/.agent/rulebase.md" "Treat secret scanning as required evidence" \
  "[clean-from-0.7.0] rulebase documents secret scanning evidence"

AGENT_ROOT="$fixture" bash "$fixture/scripts/agent-validate.sh" >/tmp/migration-0.8.0-validate.out
assert_file_contains "/tmp/migration-0.8.0-validate.out" "All validation checks passed." \
  "[clean-from-0.7.0] generated validator passes"

(
  cd "$fixture"
  git -c user.email=t@t -c user.name=Test add .
  git -c user.email=t@t -c user.name=Test commit -q -m "first 0.8.0 apply"
)

AGENT_SYNC_NOW=2026-04-28T04:00:00Z \
  "$root/scripts/agent-sync.sh" --target "$fixture" --to 0.8.0 --apply

if [ -n "$(git -C "$fixture" status --short)" ]; then
  git -C "$fixture" status --short
  printf 'FAIL: [clean-from-0.7.0] re-apply produced changes\n' >&2
  exit 1
fi
printf 'PASS: [clean-from-0.7.0] idempotent re-apply\n'

printf '\nAll 0.8.0 migration assertions passed.\n'
