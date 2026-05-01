#!/usr/bin/env bash
# Migration regression test for the multi-hop walker (P1-2).
#
# Strategy:
#   1. Build a canonical 0.4.0 fixture by syncing the 0.3.0 baseline through
#      single-hop 0.4.0 first (mirrors tests/migrations/0.5.0/run.sh).
#   2. Drive `scripts/agent-sync.sh --multi-hop --target ... --to 0.8.1`
#      end-to-end.
#   3. Cover the four invariant cases promised in the plan:
#      A) dry-run leaves the target byte-identical;
#      B) apply reaches 0.8.1 with exactly one aggregated sync-log entry;
#      C) mid-chain conflict raises EXIT_CONFLICT and target tree is unchanged;
#      D) dirty target without --allow-dirty raises EXIT_DIRTY *before* any
#         tempfile.mkdtemp / shutil.copytree call (preflight invariant).

set -euo pipefail

root="$(git rev-parse --show-toplevel)"
work_root="$(mktemp -d /tmp/migration-multi-hop.XXXXXX)"
sync_tmpdir="$work_root/sync-tmp"
mkdir -p "$sync_tmpdir"
export TMPDIR="$sync_tmpdir"

ephemeral_tags=()
cleanup() {
  for tag in "${ephemeral_tags[@]:-}"; do
    git -C "$root" tag -d "$tag" >/dev/null 2>&1 || true
  done
  rm -rf "$work_root"
}
trap cleanup EXIT

ensure_tag() {
  local version="$1" commit="$2"
  if git -C "$root" rev-parse --verify --quiet "v$version^{commit}" >/dev/null; then
    return 0
  fi
  if [ -n "$commit" ]; then
    if ! git -C "$root" rev-parse --verify --quiet "${commit}^{commit}" >/dev/null; then
      printf 'FAIL: v%s tag missing AND commit %s is not reachable locally.\n' "$version" "$commit" >&2
      exit 1
    fi
    git -C "$root" tag "v$version" "$commit"
  else
    git -C "$root" tag "v$version"
  fi
  ephemeral_tags+=("v$version")
}

ensure_tag "0.3.2" "499eb163bdc4cf5de39f7572a538af418828be4c"
ensure_tag "0.4.0" "2bb93a0ea9870eccdba1c195f7e65ed367a58ed7"
ensure_tag "0.5.0" "3900230d548852696fd39b6745fe05f08179c7fb"
ensure_tag "0.6.0" "264b0661a80c235dfd2a3b63078d2e45cbc3b8ce"
ensure_tag "0.7.0" ""
ensure_tag "0.8.0" ""
ensure_tag "0.8.1" ""

assert_eq() {
  local got="$1" want="$2" desc="$3"
  if [ "$got" = "$want" ]; then
    printf 'PASS: %s\n' "$desc"
  else
    printf 'FAIL: %s\n  got:  %q\n  want: %q\n' "$desc" "$got" "$want" >&2
    exit 1
  fi
}

build_040_fixture() {
  local dest="$1"
  cp -a "$root/tests/migrations/0.3.0/after/." "$dest/" >&2
  (
    cd "$dest"
    git init -q
    git -c user.email=t@t -c user.name=Test add .
    git -c user.email=t@t -c user.name=Test commit -q -m "fixture@0.3.0"
  ) >&2

  AGENT_SYNC_NOW=2026-04-30T00:00:00Z \
    "$root/scripts/agent-sync.sh" --target "$dest" --to 0.4.0 --apply >&2

  (
    cd "$dest"
    git -c user.email=t@t -c user.name=Test add .
    git -c user.email=t@t -c user.name=Test commit -q -m "fixture@0.4.0"
  ) >&2
}

# Hash the visible portion of the target (everything outside .git). Used to
# assert "target tree unchanged" in the conflict and dry-run cases.
target_tree_sha() {
  local dir="$1"
  ( cd "$dir" && find . -type f -not -path './.git/*' -print0 \
      | LC_ALL=C sort -z \
      | xargs -0 sha256sum \
      | sha256sum \
      | awk '{print $1}' )
}

# ---------- Case A: dry-run leaves the real target unchanged ----------
case_a="$work_root/case-a"
mkdir -p "$case_a"
build_040_fixture "$case_a"
sha_a_before="$(target_tree_sha "$case_a")"

# Inherit the same --accept-theirs scripts/agent-eval.sh as the canonical
# 0.8.0 single-hop test (tests/migrations/0.8.0/run.sh:83): the rendered
# scripts/agent-eval.sh vs. the raw v0.8.0 scripts/agent-eval.template.sh
# always 3-way conflicts on hop 0.7.0 -> 0.8.0, regardless of multi-hop.
AGENT_SYNC_NOW=2026-04-30T00:10:00Z \
  "$root/scripts/agent-sync.sh" --multi-hop --target "$case_a" --to 0.8.1 \
    --accept-theirs scripts/agent-eval.sh >/dev/null

sha_a_after="$(target_tree_sha "$case_a")"
assert_eq "$sha_a_after" "$sha_a_before" "case-a: dry-run leaves target tree byte-identical"

# Temp tree must be cleaned up even after dry-run.
remaining="$(find "$sync_tmpdir" -maxdepth 1 -mindepth 1 -name 'agent-sync-chain-*' 2>/dev/null | wc -l | tr -d ' ')"
assert_eq "$remaining" "0" "case-a: rehearsal temp dir cleaned up"

# ---------- Case B: apply reaches 0.8.1 with one aggregated sync-log entry ----------
case_b="$work_root/case-b"
mkdir -p "$case_b"
build_040_fixture "$case_b"
sections_before="$(grep -c '^## ' "$case_b/.agent/sync-log.md" 2>/dev/null || echo 0)"

AGENT_SYNC_NOW=2026-04-30T01:00:00Z \
  "$root/scripts/agent-sync.sh" --multi-hop --target "$case_b" --to 0.8.1 --apply \
    --accept-theirs scripts/agent-eval.sh >/dev/null

got_synced_to="$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['synced_to_template_version'])" "$case_b/.agent/manifest.json")"
got_template_version="$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['template_version'])" "$case_b/.agent/manifest.json")"
assert_eq "$got_synced_to" "0.8.1" "case-b: manifest synced_to_template_version == 0.8.1"
assert_eq "$got_template_version" "0.8.1" "case-b: manifest template_version == 0.8.1"

sections_after="$(grep -c '^## ' "$case_b/.agent/sync-log.md")"
assert_eq "$((sections_after - sections_before))" "1" "case-b: exactly one new sync-log entry appended"

if grep -q "multi-hop from 0.4.0" "$case_b/.agent/sync-log.md"; then
  printf 'PASS: case-b: aggregated heading mentions multi-hop\n'
else
  printf 'FAIL: case-b: aggregated heading missing multi-hop marker\n' >&2
  exit 1
fi

if grep -q "Chain: 0.4.0 -> 0.5.0 -> 0.6.0 -> 0.7.0 -> 0.8.0 -> 0.8.1" "$case_b/.agent/sync-log.md"; then
  printf 'PASS: case-b: aggregated entry lists full chain\n'
else
  printf 'FAIL: case-b: aggregated entry missing full chain line\n' >&2
  grep -A2 "multi-hop from 0.4.0" "$case_b/.agent/sync-log.md" >&2 || true
  exit 1
fi

# Sanity check that 0.7.0-era validator content landed and that 0.8.0's
# modular split moved it to plan_validation/validator.py.
if grep -q "DEC-001" "$case_b/scripts/lib/plan_validation/validator.py"; then
  printf 'PASS: case-b: 0.7.0 DEC-001 logic landed via 0.8.0 modular split\n'
else
  printf 'FAIL: case-b: 0.7.0 DEC-001 logic missing from plan_validation/validator.py\n' >&2
  exit 1
fi
if grep -q "Compatibility wrapper" "$case_b/scripts/lib/validate_plan.py"; then
  printf 'PASS: case-b: 0.8.0 compatibility wrapper installed in scripts/lib/validate_plan.py\n'
else
  printf 'FAIL: case-b: 0.8.0 compatibility wrapper missing from scripts/lib/validate_plan.py\n' >&2
  exit 1
fi

# Multi-hop sync sets template_commit to the final tag (Template commit is the
# 6th line after the heading: blank/From/To/Chain/Template commit/Updated).
if grep -A6 "multi-hop from 0.4.0" "$case_b/.agent/sync-log.md" | grep -q "Template commit:"; then
  printf 'PASS: case-b: aggregated entry records final template commit\n'
else
  printf 'FAIL: case-b: aggregated entry missing Template commit line\n' >&2
  exit 1
fi

# ---------- Case C: mid-chain conflict leaves the target unchanged ----------
case_c="$work_root/case-c"
mkdir -p "$case_c"
build_040_fixture "$case_c"

# Drift a file that 0.6.0's safe_overwrite touches so the rehearsal hits a
# CONFLICT at hop 0.5.0 -> 0.6.0 (ours diverges from both base v0.5.0 and
# theirs v0.6.0).
printf '\n# DRIFT TO FORCE CONFLICT (multi-hop test)\n' >> "$case_c/scripts/lib/validate_plan.py"
(
  cd "$case_c"
  git -c user.email=t@t -c user.name=Test add scripts/lib/validate_plan.py
  git -c user.email=t@t -c user.name=Test commit -q -m "drift validate_plan.py"
)

sha_c_before="$(target_tree_sha "$case_c")"

# Pass --accept-theirs scripts/agent-eval.sh so the *only* remaining conflict
# is the deliberate validate_plan.py drift at hop 0.5.0 -> 0.6.0.
set +e
AGENT_SYNC_NOW=2026-04-30T02:00:00Z \
  "$root/scripts/agent-sync.sh" --multi-hop --target "$case_c" --to 0.8.1 --apply \
    --accept-theirs scripts/agent-eval.sh >/dev/null 2>&1
case_c_rc=$?
set -e
assert_eq "$case_c_rc" "20" "case-c: mid-chain conflict raises EXIT_CONFLICT (20)"

sha_c_after="$(target_tree_sha "$case_c")"
assert_eq "$sha_c_after" "$sha_c_before" "case-c: target tree unchanged after mid-chain conflict"

if [ -e "$case_c/.agent/.sync.lock" ]; then
  printf 'FAIL: case-c: stale .sync.lock left in target after rehearsal conflict\n' >&2
  exit 1
fi
printf 'PASS: case-c: no .sync.lock leaked into target after rehearsal conflict\n'

remaining="$(find "$sync_tmpdir" -maxdepth 1 -mindepth 1 -name 'agent-sync-chain-*' 2>/dev/null | wc -l | tr -d ' ')"
assert_eq "$remaining" "0" "case-c: rehearsal temp dir cleaned up after conflict"

# ---------- Case D: dirty target rejected before any temp materialization ----------
case_d="$work_root/case-d"
mkdir -p "$case_d"
build_040_fixture "$case_d"
printf '\n# uncommitted noise\n' >> "$case_d/.agent/manifest.json"

# Snapshot the temp directory listing before the dirty rejection. Sign-off
# invariant 1: preflight must run before mkdtemp/copytree.
ls -A "$sync_tmpdir" | LC_ALL=C sort > "$work_root/tmp-before.txt"

set +e
AGENT_SYNC_NOW=2026-04-30T03:00:00Z \
  "$root/scripts/agent-sync.sh" --multi-hop --target "$case_d" --to 0.8.1 --apply >/dev/null 2>&1
case_d_rc=$?
set -e
assert_eq "$case_d_rc" "10" "case-d: dirty target raises EXIT_DIRTY (10)"

ls -A "$sync_tmpdir" | LC_ALL=C sort > "$work_root/tmp-after.txt"
if diff -q "$work_root/tmp-before.txt" "$work_root/tmp-after.txt" >/dev/null; then
  printf 'PASS: case-d: no temp dir materialized when preflight rejects dirty target\n'
else
  printf 'FAIL: case-d: temp dir(s) materialized despite dirty rejection\n' >&2
  diff "$work_root/tmp-before.txt" "$work_root/tmp-after.txt" >&2 || true
  exit 1
fi

# Same case, dry-run path: dirty target must also be rejected before mkdtemp.
ls -A "$sync_tmpdir" | LC_ALL=C sort > "$work_root/tmp-before-dry.txt"

set +e
AGENT_SYNC_NOW=2026-04-30T03:10:00Z \
  "$root/scripts/agent-sync.sh" --multi-hop --target "$case_d" --to 0.8.1 >/dev/null 2>&1
case_d_dry_rc=$?
set -e
assert_eq "$case_d_dry_rc" "10" "case-d (dry-run): dirty target raises EXIT_DIRTY"

ls -A "$sync_tmpdir" | LC_ALL=C sort > "$work_root/tmp-after-dry.txt"
if diff -q "$work_root/tmp-before-dry.txt" "$work_root/tmp-after-dry.txt" >/dev/null; then
  printf 'PASS: case-d (dry-run): no temp dir materialized\n'
else
  printf 'FAIL: case-d (dry-run): temp dir(s) materialized despite dirty rejection\n' >&2
  diff "$work_root/tmp-before-dry.txt" "$work_root/tmp-after-dry.txt" >&2 || true
  exit 1
fi

printf 'All multi-hop migration tests passed.\n'
