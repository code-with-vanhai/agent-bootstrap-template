#!/usr/bin/env bash
# Migration regression test for 0.3.0/0.3.2 -> 0.4.0.
#
# Strategy:
#   1. Reuse tests/migrations/0.3.0/after/ as the canonical 0.3.0 baseline.
#   2. Create an ephemeral local v0.4.0 tag at HEAD if it does not already
#      exist (deleted on EXIT). Tests run against the production --to 0.4.0
#      path; no test-only sync flag.
#   3. Run sync and assert content rather than diff against a baked fixture
#      tree. This avoids a fragile full-tree fixture for an in-progress release.
#
# Coverage:
#   - clean-from-0.3.0: source = 0.3.0 manifest, no customizations.
#   - clean-from-0.3.2: source = 0.3.2 manifest, no customizations.
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

# 1) Ensure v0.3.2 and v0.4.0 tags exist at HEAD for the test (production
#    code reads the template via the requested tag in multiple places).
#    Delete the ephemeral tags on exit.
if ! git -C "$root" rev-parse --verify --quiet "v0.3.2^{commit}" >/dev/null; then
  # 0.3.2 was a metadata-only release; core/* is byte-identical to 0.3.0.
  # Pin the ephemeral tag to v0.3.0's commit to model that accurately.
  v030_commit="$(git -C "$root" rev-parse "v0.3.0^{commit}")"
  git -C "$root" tag v0.3.2 "$v030_commit"
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
if version == "0.3.2":
    # Repos newly bootstrapped at 0.3.2 also have instantiated_from_template_version=0.3.2.
    data["instantiated_from_template_version"] = "0.3.2"
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

run_sync_customized() {
  local label="customized"
  local fixture
  fixture="$(setup_fixture "$label" "0.3.0")"

  # Inject a small user customization that does NOT collide with anchors.
  cat >> "$fixture/.agent/rulebase.md" <<'EOF'

## Local Project Notes

This rulebase is customized for the fixture project. The lines below are
preserved across syncs.

- Custom rule: never deploy on Friday.
EOF
  ( cd "$fixture" && git -c user.email=t@t -c user.name=Test add . && \
    git -c user.email=t@t -c user.name=Test commit -q -m "user customization" )

  AGENT_SYNC_NOW=2026-04-26T00:00:00Z \
    "$root/scripts/agent-sync.sh" --target "$fixture" --to 0.4.0 --apply

  # User customization preserved.
  assert_file_contains "$fixture/.agent/rulebase.md" "Custom rule: never deploy on Friday." \
    "[$label] user customization preserved"
  # Patch still applied.
  assert_file_contains "$fixture/.agent/rulebase.md" "## Status Field Whitelist" \
    "[$label] Status Field Whitelist patch applied alongside customization"
}

run_sync_clean 0.3.0
run_sync_clean 0.3.2
run_sync_customized

printf '\nAll 0.4.0 migration assertions passed.\n'
