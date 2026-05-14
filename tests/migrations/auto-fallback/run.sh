#!/usr/bin/env bash
# Stage 1.1 fixture (revision 7 of the 2026-05-05 migration UX plan):
#   - Case 1: clean fixture, hash matches catalog, auto-fallback runs
#             0.4.0 -> latest migratable with no --multi-hop / --accept-theirs.
#   - Case 2: same fixture but the user customized scripts/agent-eval.sh; the
#             walker must FAIL at hop 0.7.0 -> 0.8.0 because the catalog hash
#             no longer matches. Re-running with --accept-theirs succeeds.
#   - Case 3: no --to flag -> the fallback path resolves a default-latest
#             target and propagates it to run_multi_hop instead of raising
#             UsageError at multi_hop.py:133.
#   - Case 4: catalog provenance — recompute the catalog baseline_sha256
#             from the canonical 0.4.0 -> 0.7.0 fixture pipeline and assert
#             the published catalog hash matches.

set -euo pipefail

root="$(git rev-parse --show-toplevel)"
work_root="$(mktemp -d /tmp/migration-auto-fallback.XXXXXX)"
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

tag_current_worktree() {
  local version="$1"
  if git -C "$root" rev-parse --verify --quiet "v$version^{commit}" >/dev/null; then
    return 0
  fi
  local index_file tree commit
  index_file="$work_root/index-$version"
  GIT_INDEX_FILE="$index_file" git -C "$root" read-tree HEAD
  GIT_INDEX_FILE="$index_file" git -C "$root" add -A
  tree="$(GIT_INDEX_FILE="$index_file" git -C "$root" write-tree)"
  commit="$(printf 'ephemeral v%s\n' "$version" | git -C "$root" commit-tree "$tree" -p HEAD)"
  git -C "$root" tag "v$version" "$commit"
  ephemeral_tags+=("v$version")
  rm -f "$index_file"
}

ensure_tag "0.3.2" "499eb163bdc4cf5de39f7572a538af418828be4c"
ensure_tag "0.4.0" "2bb93a0ea9870eccdba1c195f7e65ed367a58ed7"
ensure_tag "0.5.0" "3900230d548852696fd39b6745fe05f08179c7fb"
ensure_tag "0.6.0" "264b0661a80c235dfd2a3b63078d2e45cbc3b8ce"
ensure_tag "0.7.0" ""
ensure_tag "0.8.0" ""
ensure_tag "0.8.1" ""
ensure_tag "0.9.0" ""
ensure_tag "0.10.0" ""
# v1.0.0 is unreleased; pin its ephemeral tag to the commit immediately
# before the 1.1.0 stage commits (ci: gate agent sync versions test module).
# This keeps v1.0.0's bytes free of 1.1.0's changes (e.g. the comment added to
# scripts/agent-audit-log.sh), so the multi-hop chain through v1.0.0 -> v1.1.0
# behaves like a real downstream upgrade: base bytes (v1.0.0) differ from
# theirs (v1.1.0), and a previously-managed file that has not been customized
# matches base and fast-paths through. v1.1.0 contains the unreleased
# safe_overwrite payload, so it tags an ephemeral commit built from the
# current working tree.
ensure_tag "0.11.0" ""
ensure_tag "1.0.0" "ce988e0aed187846ba30d3517274355252fb58a6"
tag_current_worktree "1.1.0"

assert_eq() {
  local got="$1" want="$2" desc="$3"
  if [ "$got" = "$want" ]; then
    printf 'PASS: %s\n' "$desc"
  else
    printf 'FAIL: %s\n  got:  %q\n  want: %q\n' "$desc" "$got" "$want" >&2
    exit 1
  fi
}

# Build a 0.4.0 fixture (mirrors tests/migrations/multi-hop/run.sh:68).
build_040_fixture() {
  local dest="$1"
  cp -a "$root/tests/migrations/0.3.0/after/." "$dest/" >&2
  (
    cd "$dest"
    git init -q
    git -c user.email=t@t -c user.name=Test add .
    git -c user.email=t@t -c user.name=Test commit -q -m "fixture@0.3.0"
  ) >&2

  AGENT_SYNC_NOW=2026-05-05T00:00:00Z \
    "$root/scripts/agent-sync.sh" --target "$dest" --to 0.4.0 --apply >&2

  (
    cd "$dest"
    git -c user.email=t@t -c user.name=Test add .
    git -c user.email=t@t -c user.name=Test commit -q -m "fixture@0.4.0"
  ) >&2
}

# ---------- Case 1: auto-fallback through catalog match ----------
case_1="$work_root/case-1"
mkdir -p "$case_1"
build_040_fixture "$case_1"

# No --multi-hop, no --accept-theirs. Use --to 0.10.0 because that is the
# pre-D-11-backfill latest migratable destination (the plan's Stage 1.1
# closing paragraph documents this matrix).
sync_out="$work_root/case-1.out"
set +e
AGENT_SYNC_NOW=2026-05-05T00:01:00Z \
  "$root/scripts/agent-sync.sh" --target "$case_1" --to 0.10.0 --apply \
    >"$sync_out" 2>&1
case_1_rc=$?
set -e
if [ "$case_1_rc" -ne 0 ]; then
  cat "$sync_out"
  printf 'FAIL: case-1: auto-fallback did not succeed (rc=%s)\n' "$case_1_rc" >&2
  exit 1
fi

if grep -q "Auto-walking multi-hop chain" "$sync_out"; then
  printf 'PASS: case-1: stdout includes the auto-walking notice\n'
else
  cat "$sync_out"
  printf 'FAIL: case-1: missing auto-walking notice\n' >&2
  exit 1
fi

got_synced_to="$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['synced_to_template_version'])" "$case_1/.agent/manifest.json")"
assert_eq "$got_synced_to" "0.10.0" "case-1: manifest synced_to_template_version == 0.10.0"

if grep -F "[reason=catalog-baseline-match, source=0.7.0->0.8.0 catalog]" \
  "$case_1/.agent/sync-log.md" >/dev/null; then
  printf 'PASS: case-1: D-12 catalog token recorded for the 0.7.0 -> 0.8.0 hop\n'
else
  printf 'FAIL: case-1: D-12 catalog token missing from sync-log\n' >&2
  cat "$case_1/.agent/sync-log.md" >&2
  exit 1
fi

# ---------- Case 2: customized file blocks the catalog branch ----------
case_2="$work_root/case-2"
mkdir -p "$case_2"
build_040_fixture "$case_2"

printf '\n# user customization (catalog should NOT auto-accept)\n' \
  >> "$case_2/scripts/agent-eval.sh"
(
  cd "$case_2"
  git -c user.email=t@t -c user.name=Test add scripts/agent-eval.sh
  git -c user.email=t@t -c user.name=Test commit -q -m "user customization"
) >&2

set +e
AGENT_SYNC_NOW=2026-05-05T00:02:00Z \
  "$root/scripts/agent-sync.sh" --target "$case_2" --to 0.10.0 --apply \
    >"$work_root/case-2.out" 2>&1
case_2_rc=$?
set -e
assert_eq "$case_2_rc" "20" "case-2: customized file raises EXIT_CONFLICT (20)"

if grep -F "Catalog conflict but file customized" "$work_root/case-2.out" \
  >/dev/null; then
  printf 'PASS: case-2: stderr explains the catalog mismatch\n'
else
  printf 'FAIL: case-2: missing catalog-mismatch hint\n' >&2
  cat "$work_root/case-2.out" >&2
  exit 1
fi

# Re-run with --accept-theirs to confirm the existing escape hatch still works.
set +e
AGENT_SYNC_NOW=2026-05-05T00:02:30Z \
  "$root/scripts/agent-sync.sh" --target "$case_2" --to 0.10.0 --apply \
    --accept-theirs scripts/agent-eval.sh >"$work_root/case-2-rerun.out" 2>&1
case_2_rerun_rc=$?
set -e
if [ "$case_2_rerun_rc" -ne 0 ]; then
  cat "$work_root/case-2-rerun.out"
  printf 'FAIL: case-2: --accept-theirs did not unblock the run\n' >&2
  exit 1
fi
printf 'PASS: case-2: --accept-theirs unblocks the customized file\n'

# ---------- Case 3: no --to falls through with default-latest ----------
case_3="$work_root/case-3"
mkdir -p "$case_3"
build_040_fixture "$case_3"

set +e
AGENT_SYNC_NOW=2026-05-05T00:03:00Z \
  "$root/scripts/agent-sync.sh" --target "$case_3" --apply \
    >"$work_root/case-3.out" 2>&1
case_3_rc=$?
set -e
if [ "$case_3_rc" -ne 0 ]; then
  cat "$work_root/case-3.out"
  printf 'FAIL: case-3: no --to fallback failed (rc=%s)\n' "$case_3_rc" >&2
  exit 1
fi

got_synced_to_3="$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['synced_to_template_version'])" "$case_3/.agent/manifest.json")"
# Latest migratable is the highest core/migrations/<ver>/migration.json.
expected_latest="$(ls "$root/core/migrations" | grep -E '^[0-9]+\.[0-9]+\.[0-9]+' | sort -V | tail -1)"
assert_eq "$got_synced_to_3" "$expected_latest" \
  "case-3: no --to resolves to latest migratable ($expected_latest)"

# ---------- Case 4: catalog hash provenance ----------
provenance_dir="$work_root/provenance-070"
mkdir -p "$provenance_dir"
cp -a "$root/tests/migrations/0.3.0/after/." "$provenance_dir/" >&2
(
  cd "$provenance_dir"
  git init -q
  git -c user.email=t@t -c user.name=Test add .
  git -c user.email=t@t -c user.name=Test commit -q -m "fixture@0.3.0"
) >&2
for v in 0.4.0 0.5.0 0.6.0 0.7.0; do
  AGENT_SYNC_NOW=2026-05-05T00:04:00Z \
    "$root/scripts/agent-sync.sh" --target "$provenance_dir" --to "$v" --apply >&2
  (
    cd "$provenance_dir"
    git -c user.email=t@t -c user.name=Test add .
    git -c user.email=t@t -c user.name=Test commit -q -m "fixture@$v"
  ) >&2
done

provenance_sha="$(sha256sum "$provenance_dir/scripts/agent-eval.sh" | awk '{print $1}')"
catalog_sha="$(python3 -c "
import json, sys
data = json.load(open(sys.argv[1]))
for entry in data.get('known_conflicts', []) or []:
    if entry.get('path') == 'scripts/agent-eval.sh':
        print(entry['baseline_sha256'][0])
        break
" "$root/core/migrations/0.8.0/migration.json")"
assert_eq "$catalog_sha" "$provenance_sha" \
  "case-4: catalog baseline_sha256 matches the canonical 0.7.0 fixture render"

# ---------- Case 5: AC-1 matrix -> latest migratable ----------
# Plan AC-1 (docs/2026-05-05-migration-ux-improvement-plan.md): auto-fallback
# must reach the latest migratable from every supported starting version.
# Locking the full matrix here so a regression at any intermediate hop
# fails CI instead of only showing up via manual smoke.
expected_latest="$(ls "$root/core/migrations" | grep -E '^[0-9]+\.[0-9]+\.[0-9]+' | sort -V | tail -1)"

build_fixture_at() {
  local dest="$1" target_ver="$2"
  cp -a "$root/tests/migrations/0.3.0/after/." "$dest/" >&2
  (
    cd "$dest"
    git init -q
    git -c user.email=t@t -c user.name=Test add .
    git -c user.email=t@t -c user.name=Test commit -q -m "fixture@0.3.0"
  ) >&2
  if [ "$target_ver" != "0.3.0" ]; then
    AGENT_SYNC_NOW=2026-05-05T00:05:00Z \
      "$root/scripts/agent-sync.sh" --target "$dest" --to "$target_ver" \
        --multi-hop --apply >&2
    (
      cd "$dest"
      git -c user.email=t@t -c user.name=Test add .
      git -c user.email=t@t -c user.name=Test commit -q -m "fixture@$target_ver"
    ) >&2
  fi
}

for from_ver in 0.3.0 0.4.0 0.8.1 0.9.0; do
  case_m="$work_root/case-matrix-$from_ver"
  mkdir -p "$case_m"
  build_fixture_at "$case_m" "$from_ver"

  got_from="$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['synced_to_template_version'])" "$case_m/.agent/manifest.json")"
  assert_eq "$got_from" "$from_ver" \
    "case-matrix($from_ver): fixture starts at $from_ver"

  matrix_out="$work_root/case-matrix-$from_ver.out"
  set +e
  AGENT_SYNC_NOW=2026-05-05T00:06:00Z \
    "$root/scripts/agent-sync.sh" --target "$case_m" --apply \
      >"$matrix_out" 2>&1
  matrix_rc=$?
  set -e
  if [ "$matrix_rc" -ne 0 ]; then
    cat "$matrix_out"
    printf 'FAIL: case-matrix(%s): auto-fallback to latest did not succeed (rc=%s)\n' \
      "$from_ver" "$matrix_rc" >&2
    exit 1
  fi
  got_to="$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['synced_to_template_version'])" "$case_m/.agent/manifest.json")"
  assert_eq "$got_to" "$expected_latest" \
    "case-matrix($from_ver -> $expected_latest): manifest synced_to_template_version matches"
done

printf 'All auto-fallback migration tests passed.\n'
