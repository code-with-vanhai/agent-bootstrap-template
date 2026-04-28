#!/usr/bin/env bash
# Migration regression test for 0.3.0 -> 0.4.0.
#
# Strategy:
#   1. Reuse tests/migrations/0.3.0/after/ as the canonical 0.3.0 baseline.
#   2. Create an ephemeral local v0.4.0 tag at HEAD if it does not already
#      exist (deleted on EXIT). Tests run against the production --to 0.4.0
#      path; no test-only sync flag.
#   3. Run sync and assert content rather than diff against a baked fixture
#      tree. This avoids a fragile full-tree fixture for an in-progress release.
#
# Note on dropped clean-from-0.3.2 case:
#   v0.3.2 was NOT a metadata-only release (`git diff v0.3.0 v0.3.2 -- core/`
#   shows ~940 lines of grounded-planning content across 17 files including
#   core/commands/plan.md). The earlier clean-from-0.3.2 scenario copied the
#   0.3.0 fixture and merely patched the manifest's synced_to_template_version
#   to 0.3.2, which produced a fixture whose content reflected 0.3.0 but
#   claimed to be 0.3.2. agent-sync.py correctly flagged the inevitable
#   ours-vs-base divergence as a conflict. Dropping the case rather than
#   building a real 0.3.2 fixture (would require its own baseline tree) keeps
#   the test honest. Migration semantics for repos genuinely synced to 0.3.2
#   are still exercised in production when those users sync to 0.4.0.
#
# Coverage:
#   - clean-from-0.3.0: source = 0.3.0 manifest, no customizations.
#   - customized:       user edited rulebase.md before sync; safe_overwrite
#                       preserves user edits (ours == theirs check) and the
#                       patch is still applied because anchor still matches.
#   - idempotent:       applying twice produces no changes the second time.

set -euo pipefail

root="$(git rev-parse --show-toplevel)"
work_root="$(mktemp -d /tmp/migration-0.4.0.XXXXXX)"

ephemeral_v032_created="0"
ephemeral_v040_created="0"
cleanup() {
  if [ "$ephemeral_v040_created" = "1" ]; then
    git -C "$root" tag -d v0.4.0 >/dev/null 2>&1 || true
  fi
  if [ "$ephemeral_v032_created" = "1" ]; then
    git -C "$root" tag -d v0.3.2 >/dev/null 2>&1 || true
  fi
  rm -rf "$work_root"
}
trap cleanup EXIT

# 1) Ensure v0.3.2 and v0.4.0 tags exist for the test. agent-sync.py's
#    preflight requires a tag for every from_version in the migration
#    chain, even when this test only exercises clean-from-0.3.0 -> 0.4.0:
#    a 0.3.0 -> 0.4.0 sync still walks the chain through 0.3.2.
#
#    For v0.3.2: pin to the REAL v0.3.2 commit (499eb163) if reachable in
#    local history. Do NOT fall back to v0.3.0's commit (the prior code
#    did this on the false premise that v0.3.2 was metadata-only; see
#    the header note above).
#
#    Ephemeral tags are deleted on exit.
if ! git -C "$root" rev-parse --verify --quiet "v0.3.2^{commit}" >/dev/null; then
  v032_real_commit="499eb163bdc4cf5de39f7572a538af418828be4c"
  if ! git -C "$root" rev-parse --verify --quiet "${v032_real_commit}^{commit}" >/dev/null; then
    printf 'FAIL: v0.3.2 tag missing AND commit %s is not reachable locally.\n' "$v032_real_commit" >&2
    printf '      Run `git fetch --tags` (or `git fetch origin %s`) and retry.\n' "$v032_real_commit" >&2
    exit 1
  fi
  git -C "$root" tag v0.3.2 "$v032_real_commit"
  ephemeral_v032_created="1"
fi
if ! git -C "$root" rev-parse --verify --quiet "v0.4.0^{commit}" >/dev/null; then
  git -C "$root" tag v0.4.0
  ephemeral_v040_created="1"
fi

setup_fixture() {
  local name="$1"
  local source_version="$2"
  local fixture_dir="$work_root/$name"
  cp -a "$root/tests/migrations/0.3.0/after/." "$fixture_dir/"
  # Adjust manifest source version.
  python3 - "$fixture_dir/.agent/manifest.json" "$source_version" <<'PY'
import json, sys
from collections import OrderedDict
path, version = sys.argv[1], sys.argv[2]
with open(path, "r", encoding="utf-8") as fh:
    data = json.load(fh, object_pairs_hook=OrderedDict)
data["template_version"] = version
data["synced_to_template_version"] = version
with open(path, "w", encoding="utf-8") as fh:
    json.dump(data, fh, indent=2)
    fh.write("\n")
PY
  ( cd "$fixture_dir" && git init -q && \
    git -c user.email=t@t -c user.name=Test add . && \
    git -c user.email=t@t -c user.name=Test commit -q -m "fixture@$source_version" )
  printf '%s\n' "$fixture_dir"
}

assert_file_contains() {
  local path="$1" needle="$2" desc="$3"
  if grep -qF -- "$needle" "$path"; then
    printf 'PASS: %s\n' "$desc"
  else
    printf 'FAIL: %s\n  file=%s\n  needle=%s\n' "$desc" "$path" "$needle" >&2
    exit 1
  fi
}

assert_file_exists() {
  local path="$1" desc="$2"
  if [ -f "$path" ]; then
    printf 'PASS: %s\n' "$desc"
  else
    printf 'FAIL: %s (missing %s)\n' "$desc" "$path" >&2
    exit 1
  fi
}

run_sync_clean() {
  local source_version="$1"
  local label="clean-from-$source_version"
  local fixture
  fixture="$(setup_fixture "$label" "$source_version")"

  AGENT_SYNC_NOW=2026-04-26T00:00:00Z \
    "$root/scripts/agent-sync.sh" --target "$fixture" --to 0.4.0 --apply

  # New validator scripts shipped.
  assert_file_exists "$fixture/scripts/agent-validate-plan.sh" \
    "[$label] agent-validate-plan.sh shipped"
  assert_file_exists "$fixture/scripts/lib/validate_plan.py" \
    "[$label] lib/validate_plan.py shipped"

  # Anchor patches landed.
  assert_file_contains "$fixture/.agent/rulebase.md" "## Status Field Whitelist" \
    "[$label] rulebase Status Field Whitelist"
  assert_file_contains "$fixture/.agent/workflows/feature-workflow.md" "## Grounding Requirements" \
    "[$label] feature-workflow Grounding Requirements"
  assert_file_contains "$fixture/.agent/workflows/review-workflow.md" "## Plan/Spec Review" \
    "[$label] review-workflow Plan/Spec Review"
  assert_file_contains "$fixture/.agent/roles/planner.md" "## Evidence Blocks" \
    "[$label] planner Evidence Blocks"
  assert_file_contains "$fixture/.agent/roles/reviewer.md" "## Plan/Spec Grounding Pass" \
    "[$label] reviewer Plan/Spec Grounding Pass"
  assert_file_contains "$fixture/.agent/gates.md" "## AC Verification Taxonomy" \
    "[$label] gates AC Verification Taxonomy"

  # Manifest updated.
  assert_file_contains "$fixture/.agent/manifest.json" '"template_version": "0.4.0"' \
    "[$label] manifest template_version=0.4.0"
  assert_file_contains "$fixture/.agent/manifest.json" '"synced_to_template_version": "0.4.0"' \
    "[$label] manifest synced_to=0.4.0"

  # Idempotency: re-apply must be a no-op.
  ( cd "$fixture" && git -c user.email=t@t -c user.name=Test add . && \
    git -c user.email=t@t -c user.name=Test commit -q -m "first apply" )

  AGENT_SYNC_NOW=2026-04-26T00:00:00Z \
    "$root/scripts/agent-sync.sh" --target "$fixture" --to 0.4.0 --apply

  if [ -n "$(git -C "$fixture" status --short)" ]; then
    git -C "$fixture" status --short
    printf 'FAIL: [%s] re-apply produced changes\n' "$label" >&2
    exit 1
  fi
  printf 'PASS: [%s] idempotent re-apply\n' "$label"
}

run_sync_customized_rulebase() {
  local label="customized-rulebase"
  local fixture
  fixture="$(setup_fixture "$label" "0.3.0")"

  cat >> "$fixture/.agent/rulebase.md" <<'EOF'

## Local Project Notes

- Custom rule: never deploy on Friday.
EOF
  ( cd "$fixture" && git -c user.email=t@t -c user.name=Test add . && \
    git -c user.email=t@t -c user.name=Test commit -q -m "rulebase customization" )

  AGENT_SYNC_NOW=2026-04-26T00:00:00Z \
    "$root/scripts/agent-sync.sh" --target "$fixture" --to 0.4.0 --apply

  assert_file_contains "$fixture/.agent/rulebase.md" "Custom rule: never deploy on Friday." \
    "[$label] customization preserved"
  assert_file_contains "$fixture/.agent/rulebase.md" "## Status Field Whitelist" \
    "[$label] Status Field Whitelist patch applied alongside customization"
}

run_sync_customized_gates() {
  local label="customized-gates"
  local fixture
  fixture="$(setup_fixture "$label" "0.3.0")"

  cat >> "$fixture/.agent/gates.md" <<'EOF'

## Local Project Gate Mapping

- `frontend` -> `pnpm test:web`
- `backend`  -> `pnpm test:api`
EOF
  ( cd "$fixture" && git -c user.email=t@t -c user.name=Test add . && \
    git -c user.email=t@t -c user.name=Test commit -q -m "gate customization" )

  AGENT_SYNC_NOW=2026-04-26T00:00:00Z \
    "$root/scripts/agent-sync.sh" --target "$fixture" --to 0.4.0 --apply

  assert_file_contains "$fixture/.agent/gates.md" "pnpm test:web" \
    "[$label] custom frontend gate mapping preserved"
  assert_file_contains "$fixture/.agent/gates.md" "pnpm test:api" \
    "[$label] custom backend gate mapping preserved"
  assert_file_contains "$fixture/.agent/gates.md" "## AC Verification Taxonomy" \
    "[$label] AC Verification Taxonomy patch applied alongside customization"
  assert_file_contains "$fixture/.agent/gates.md" "## Plan Discipline Command" \
    "[$label] Plan Discipline Command patch applied alongside customization"
}

run_sync_customized_roles() {
  local label="customized-roles"
  local fixture
  fixture="$(setup_fixture "$label" "0.3.0")"

  # Append role-specific local guidance to planner + reviewer.
  cat >> "$fixture/.agent/roles/planner.md" <<'EOF'

## Local Planning Notes

- Always confirm cron ownership with the on-call rotation before scheduling jobs.
EOF
  cat >> "$fixture/.agent/roles/reviewer.md" <<'EOF'

## Local Review Notes

- Block any change that touches `infra/terraform/` without infra-team sign-off.
EOF
  cat >> "$fixture/.agent/workflows/feature-workflow.md" <<'EOF'

## Local Workflow Notes

- Run `pnpm i18n:check` before merging UI strings.
EOF
  cat >> "$fixture/.agent/workflows/review-workflow.md" <<'EOF'

## Local Review Workflow Notes

- Reviewers must spot-check generated migrations against the staging dataset.
EOF
  ( cd "$fixture" && git -c user.email=t@t -c user.name=Test add . && \
    git -c user.email=t@t -c user.name=Test commit -q -m "role/workflow customization" )

  AGENT_SYNC_NOW=2026-04-26T00:00:00Z \
    "$root/scripts/agent-sync.sh" --target "$fixture" --to 0.4.0 --apply

  # Customizations preserved.
  assert_file_contains "$fixture/.agent/roles/planner.md" "on-call rotation" \
    "[$label] planner customization preserved"
  assert_file_contains "$fixture/.agent/roles/reviewer.md" "infra-team sign-off" \
    "[$label] reviewer customization preserved"
  assert_file_contains "$fixture/.agent/workflows/feature-workflow.md" "pnpm i18n:check" \
    "[$label] feature-workflow customization preserved"
  assert_file_contains "$fixture/.agent/workflows/review-workflow.md" "staging dataset" \
    "[$label] review-workflow customization preserved"

  # Patches still applied.
  assert_file_contains "$fixture/.agent/roles/planner.md" "## Evidence Blocks" \
    "[$label] planner Evidence Blocks patch applied"
  assert_file_contains "$fixture/.agent/roles/reviewer.md" "## Plan/Spec Grounding Pass" \
    "[$label] reviewer Plan/Spec Grounding Pass patch applied"
  assert_file_contains "$fixture/.agent/workflows/feature-workflow.md" "## Grounding Requirements" \
    "[$label] feature-workflow Grounding Requirements patch applied"
  assert_file_contains "$fixture/.agent/workflows/review-workflow.md" "## Plan/Spec Review" \
    "[$label] review-workflow Plan/Spec Review patch applied"
}

run_sync_clean 0.3.0
run_sync_customized_rulebase
run_sync_customized_gates
run_sync_customized_roles

printf '\nAll 0.4.0 migration assertions passed.\n'
