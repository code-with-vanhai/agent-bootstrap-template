#!/usr/bin/env bash
# Migration regression test for 0.8.1 -> 0.9.0.

set -euo pipefail

root="$(git rev-parse --show-toplevel)"
work_root="$(mktemp -d /tmp/migration-0.9.0.XXXXXX)"

ephemeral_v090_created="0"

cleanup() {
  if [ "$ephemeral_v090_created" = "1" ]; then
    git -C "$root" tag -d v0.9.0 >/dev/null 2>&1 || true
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

assert_file_absent() {
  path="$1"
  desc="$2"
  if [ ! -e "$path" ]; then
    printf 'PASS: %s\n' "$desc"
  else
    printf 'FAIL: %s\n  unexpected path exists\n' "$desc" >&2
    exit 1
  fi
}

ensure_previous_release_tag() {
  if git -C "$root" rev-parse --verify --quiet "v0.8.1^{commit}" >/dev/null; then
    return 0
  fi
  printf 'SKIP: v0.8.1 tag is missing; cannot build the 0.8.1 regression fixture.\n'
  exit 0
}

ensure_current_release_tag() {
  if git -C "$root" rev-parse --verify --quiet "v0.9.0^{commit}" >/dev/null; then
    return 0
  fi
  if [ -n "$(git -C "$root" status --short -- \
    CHANGELOG.md \
    USAGE.md \
    core/migrations/README.md \
    core/migrations/0.9.0 \
    scripts/bootstrap-request.sh \
    scripts/agent-sync.py \
    scripts/agent-audit-log.sh \
    scripts/agent-eval.template.sh \
    scripts/agent-validate-plan.sh \
    scripts/lib/audit_log.py \
    scripts/lib/insert_gate_candidates.py \
    scripts/lib/validate_agent_system.py \
    scripts/lib/plan_validation/cli.py \
    scripts/lib/plan_validation/models.py \
    adapters \
    core/README.md \
    core/project-profile.template.md \
    core/roles/prompts \
    core/skills/data-safety)" ]; then
    printf 'SKIP: v0.9.0 tag is missing and 0.9.0 migration sources are not committed yet.\n'
    exit 0
  fi
  git -C "$root" tag v0.9.0
  ephemeral_v090_created="1"
}

remove_pycache() {
  dir="$1"
  find "$dir" -type d -name __pycache__ -prune -exec rm -rf {} +
}

setup_081_fixture() {
  fixture_dir="$work_root/clean-from-0.8.1"
  cp -a "$root/tests/migrations/0.3.0/after/." "$fixture_dir/" >&2
  (
    cd "$fixture_dir"
    git init -q
    git -c user.email=t@t -c user.name=Test add .
    git -c user.email=t@t -c user.name=Test commit -q -m "fixture@0.3.0"
  ) >&2

  AGENT_SYNC_NOW=2026-05-01T00:00:00Z \
    "$root/scripts/agent-sync.sh" --multi-hop --target "$fixture_dir" --to 0.8.1 --apply \
      --accept-theirs scripts/agent-eval.sh >&2

  remove_pycache "$fixture_dir"
  (
    cd "$fixture_dir"
    git -c user.email=t@t -c user.name=Test add .
    git -c user.email=t@t -c user.name=Test commit -q -m "fixture@0.8.1"
  ) >&2

  assert_file_contains "$fixture_dir/.agent/manifest.json" '"template_version": "0.8.1"' \
    "[setup] manifest template_version=0.8.1" >&2
  assert_file_absent "$fixture_dir/scripts/agent-audit-log.sh" \
    "[setup] audit-log script absent before 0.9.0" >&2
  assert_file_absent "$fixture_dir/.agents/skills/agent-bootstrap/data-safety/SKILL.md" \
    "[setup] data-safety skill absent before 0.9.0" >&2

  printf '%s\n' "$fixture_dir"
}

ensure_previous_release_tag
ensure_current_release_tag
fixture="$(setup_081_fixture)"

AGENT_SYNC_NOW=2026-05-01T01:00:00Z \
  "$root/scripts/agent-sync.sh" --target "$fixture" --to 0.9.0 --apply

assert_file_contains "$fixture/.agent/manifest.json" '"template_version": "0.9.0"' \
  "[clean-from-0.8.1] manifest template_version=0.9.0"
assert_file_contains "$fixture/.agent/manifest.json" '"synced_to_template_version": "0.9.0"' \
  "[clean-from-0.8.1] manifest synced_to=0.9.0"
assert_file_contains "$fixture/.agent/sync-log.md" "Sync to 0.9.0" \
  "[clean-from-0.8.1] sync log appended"

assert_file_contains "$fixture/.agent/project-profile.md" "## Data Surface" \
  "[clean-from-0.8.1] Data Surface inserted"
assert_file_contains "$fixture/scripts/agent-eval.sh" "trap '_audit_emit_gate_exit' EXIT" \
  "[clean-from-0.8.1] agent-eval audit trap installed"
assert_file_contains "$fixture/scripts/agent-eval.sh" "AGENT-CANDIDATES gate=fast" \
  "[clean-from-0.8.1] candidate gate markers installed"
assert_file_contains "$fixture/scripts/agent-validate-plan.sh" "agent-audit-log.sh" \
  "[clean-from-0.8.1] validate-plan audit wrapper installed"
assert_file_contains "$fixture/scripts/lib/plan_validation/cli.py" '"json"' \
  "[clean-from-0.8.1] plan validator JSON format installed"
assert_file_contains "$fixture/scripts/lib/insert_gate_candidates.py" "AGENT-CANDIDATES" \
  "[clean-from-0.8.1] gate candidate insertion helper installed"

assert_file_contains "$fixture/AGENTS.md" "## Always do" \
  "[clean-from-0.8.1] AGENTS.md three-tier adapter installed"
assert_file_contains "$fixture/AGENTS.md" "## Ask first" \
  "[clean-from-0.8.1] AGENTS.md ask-first tier installed"
assert_file_absent "$fixture/CLAUDE.md" \
  "[clean-from-0.8.1] missing optional CLAUDE.md was not created"

assert_file_contains "$fixture/.agents/skills/agent-bootstrap/data-safety/SKILL.md" "name: data-safety" \
  "[clean-from-0.8.1] data-safety Codex skill installed when native skill root exists"

AGENT_ROOT="$fixture" bash "$fixture/scripts/agent-validate.sh" >/tmp/migration-0.9.0-validate.out
assert_file_contains "/tmp/migration-0.9.0-validate.out" "All validation checks passed." \
  "[clean-from-0.8.1] generated validator passes"

remove_pycache "$fixture"
(
  cd "$fixture"
  git -c user.email=t@t -c user.name=Test add .
  git -c user.email=t@t -c user.name=Test commit -q -m "first 0.9.0 apply"
)

AGENT_SYNC_NOW=2026-05-01T01:00:00Z \
  "$root/scripts/agent-sync.sh" --target "$fixture" --to 0.9.0 --apply

if [ -n "$(git -C "$fixture" status --short)" ]; then
  git -C "$fixture" status --short
  printf 'FAIL: [clean-from-0.8.1] re-apply produced changes\n' >&2
  exit 1
fi
printf 'PASS: [clean-from-0.8.1] idempotent re-apply\n'

printf '\nAll 0.9.0 migration assertions passed.\n'
