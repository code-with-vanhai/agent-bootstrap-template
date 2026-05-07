#!/usr/bin/env bash
# Stage 3.3 / D-7 fixture — one-shot tracked_files backfill at the 1.0.0 hop.
#
# Post-0.12.0 audit finding H-3 tightened the parent edge of the 1.0.0
# migration so `from_versions: ["0.12.0"]` (was `["0.11.0"]`). The
# canonical pre-1.0.0 chain is now `0.10.0 → 0.11.0 → 0.12.0 → 1.0.0`,
# and the 1.0.0 hop only fires after the user has reached 0.12.0. This
# fixture exercises the chain end-to-end via auto multi-hop.
#
# Strategy:
#   1. Build a 0.10.0 fixture from the canonical 0.3.0 baseline via
#      multi-hop sync (mirrors tests/migrations/0.11.0/run.sh).
#   2. Single-hop to 0.11.0 so the manifest is the production
#      "no-op-migration" shape Stage 3.3 expects to find on disk.
#   3. Apply --to 1.0.0 with NO --multi-hop flag. The runner's auto
#      multi-hop fallback (Stage 1.1) composes the chain
#      0.11.0 → 0.12.0 → 1.0.0 transparently. Both intermediate hops
#      are no-op for downstream bytes; the 1.0.0 hop is the first to
#      set manifest_updates.update_tracked_files: true, so the runner
#      must:
#        a) enumerate expand_file_entries(1.0.0) ∪ canonical_files,
#        b) for every existing managed file on disk, record
#           tracked_files[path] = {synced_at_version: "0.12.0",
#                                  synced_checksum_sha256: sha256(disk)}.
#      The recorded version is 0.12.0 (the user's sync version at the
#      moment the 1.0.0 backfill fires — i.e., AFTER the no-op
#      0.11.0 → 0.12.0 hop has bumped the manifest). The bytes hashed
#      are byte-identical to the 0.11.0 baseline because
#      0.11.0 → 0.12.0 is no-op for downstream content.
#   4. Assertions cover the four post-conditions from the plan:
#        - tracked_files exists in the manifest;
#        - every canonical_files path that exists on disk has an entry;
#        - the recorded sha matches sha256(disk);
#        - synced_at_version is the user's PRE-1.0.0-hop version
#          (0.12.0), not the migration's `to`.
#   5. The "manifest-only no-op" contract (only manifest + sync-log
#      modified) still holds because 1.0.0's safe_overwrite is empty
#      and tracked_files lives inside the manifest.
#
# The fixture seeds an ephemeral v1.0.0 tag at HEAD because v1.0.0 is
# unreleased; the 1.0.0 migration's manifest_updates.replace_from_git_tag
# only resolves the SHA, so HEAD content is irrelevant for this test.

set -euo pipefail

root="$(git rev-parse --show-toplevel)"
work_root="$(mktemp -d /tmp/migration-checksum-backfill.XXXXXX)"

ephemeral_v100_created="0"

cleanup() {
  if [ "$ephemeral_v100_created" = "1" ]; then
    git -C "$root" tag -d v1.0.0 >/dev/null 2>&1 || true
  fi
  rm -rf "$work_root"
}
trap cleanup EXIT

ensure_tag() {
  if git -C "$root" rev-parse --verify --quiet "v$1^{commit}" >/dev/null; then
    return 0
  fi
  printf 'SKIP: v%s tag missing; cannot run Stage 3.3 backfill fixture.\n' "$1"
  exit 0
}

remove_pycache() { find "$1" -type d -name __pycache__ -prune -exec rm -rf {} +; }

ensure_tag "0.10.0"
ensure_tag "0.11.0"
ensure_tag "0.12.0"
if ! git -C "$root" rev-parse --verify --quiet "v1.0.0^{commit}" >/dev/null; then
  git -C "$root" tag v1.0.0
  ephemeral_v100_created="1"
fi

assert_eq() {
  local got="$1" want="$2" desc="$3"
  if [ "$got" = "$want" ]; then
    printf 'PASS: %s\n' "$desc"
  else
    printf 'FAIL: %s\n  got:  %q\n  want: %q\n' "$desc" "$got" "$want" >&2
    exit 1
  fi
}

setup_0110_fixture() {
  fixture_dir="$work_root/clean-from-0.11.0"
  cp -a "$root/tests/migrations/0.3.0/after/." "$fixture_dir/" >&2
  (
    cd "$fixture_dir"
    git init -q
    git -c user.email=t@t -c user.name=Test add .
    git -c user.email=t@t -c user.name=Test commit -q -m "fixture@0.3.0"
  ) >&2

  AGENT_SYNC_NOW=2026-05-06T00:00:00Z \
    "$root/scripts/agent-sync.sh" --multi-hop --target "$fixture_dir" --to 0.10.0 --apply \
      --accept-theirs scripts/agent-eval.sh >&2
  remove_pycache "$fixture_dir"
  (
    cd "$fixture_dir"
    git -c user.email=t@t -c user.name=Test add .
    git -c user.email=t@t -c user.name=Test commit -q -m "fixture@0.10.0"
  ) >&2

  AGENT_SYNC_NOW=2026-05-06T00:01:00Z \
    "$root/scripts/agent-sync.sh" --target "$fixture_dir" --to 0.11.0 --apply >&2
  remove_pycache "$fixture_dir"
  (
    cd "$fixture_dir"
    git -c user.email=t@t -c user.name=Test add .
    git -c user.email=t@t -c user.name=Test commit -q -m "fixture@0.11.0"
  ) >&2

  printf '%s\n' "$fixture_dir"
}

fixture="$(setup_0110_fixture)"

# Pre-state assertions: manifest must NOT yet have tracked_files.
if grep -qF '"tracked_files"' "$fixture/.agent/manifest.json"; then
  printf 'FAIL: [setup] tracked_files already present before 1.0.0 backfill\n' >&2
  exit 1
fi
printf 'PASS: [setup] manifest has no tracked_files key before 1.0.0\n'

AGENT_SYNC_NOW=2026-05-06T00:02:00Z \
  "$root/scripts/agent-sync.sh" --target "$fixture" --to 1.0.0 --apply
remove_pycache "$fixture"

# Manifest sync metadata bumped (D-11 contract; 1.0.0 reuses the same
# replace_from_git_tag shape so synced_to_template_commit cannot stay
# stale even though no downstream content changed).
if ! grep -qF '"template_version": "1.0.0"' "$fixture/.agent/manifest.json"; then
  printf 'FAIL: manifest template_version not bumped to 1.0.0\n' >&2
  exit 1
fi
if ! grep -qF '"synced_to_template_version": "1.0.0"' "$fixture/.agent/manifest.json"; then
  printf 'FAIL: manifest synced_to_template_version not bumped to 1.0.0\n' >&2
  exit 1
fi
printf 'PASS: [clean-from-0.11.0] manifest sync metadata bumped to 1.0.0\n'

# Backfill post-conditions inspected via Python so the sha256 matches
# the on-disk bytes byte-for-byte.
python3 - "$fixture" <<'PY'
import hashlib
import json
import sys
from pathlib import Path

fixture = Path(sys.argv[1])
manifest = json.loads((fixture / ".agent" / "manifest.json").read_text(encoding="utf-8"))

tracked = manifest.get("tracked_files")
if not isinstance(tracked, dict) or not tracked:
    raise SystemExit("FAIL: manifest.tracked_files is missing or empty after 1.0.0 backfill")
print(f"PASS: manifest.tracked_files populated with {len(tracked)} entries")

canonical = manifest.get("canonical_files") or []
present_canonical = [p for p in canonical if (fixture / p).is_file()]
if not present_canonical:
    raise SystemExit("FAIL: no canonical_files exist on disk; fixture build is broken")

missing = [p for p in present_canonical if p not in tracked]
if missing:
    raise SystemExit(
        f"FAIL: backfill missed {len(missing)} canonical paths: {missing[:5]}"
    )
print(f"PASS: every existing canonical_files path ({len(present_canonical)}) is tracked")

# Skip-paths must be absent.
for skip in (".agent/manifest.json", ".agent/sync-log.md"):
    if skip in tracked:
        raise SystemExit(f"FAIL: {skip} unexpectedly present in tracked_files")
print("PASS: .agent/manifest.json and .agent/sync-log.md are excluded from tracked_files")

mismatched = []
wrong_version = []
for rel, record in tracked.items():
    target_path = fixture / rel
    if not target_path.is_file():
        # Backfill never fabricates entries for absent paths.
        raise SystemExit(f"FAIL: tracked_files lists {rel} but file is absent on disk")
    body = target_path.read_bytes()
    expected = hashlib.sha256(body).hexdigest()
    if record.get("synced_checksum_sha256") != expected:
        mismatched.append(rel)
    # 1.0.0's safe_overwrite is empty, so EVERY entry should carry the
    # user's PRE-1.0.0-hop sync version (0.12.0 after the post-0.12.0
    # H-3 retighten), not the migration's `to` (1.0.0). This is the
    # D-7 / Stage 3.3 contract that the recorded version is the
    # provenance of the bytes on disk. Bytes are byte-identical to the
    # 0.11.0 baseline because 0.11.0 → 0.12.0 is a no-op hop; only
    # the version label has advanced.
    if record.get("synced_at_version") != "0.12.0":
        wrong_version.append((rel, record.get("synced_at_version")))

if mismatched:
    raise SystemExit(f"FAIL: {len(mismatched)} entries have wrong sha256: {mismatched[:5]}")
print("PASS: every tracked_files sha256 matches sha256(disk bytes)")

if wrong_version:
    raise SystemExit(
        f"FAIL: {len(wrong_version)} entries have wrong synced_at_version "
        f"(expected 0.12.0, got: {wrong_version[:5]})"
    )
print("PASS: every tracked_files entry records synced_at_version=0.12.0 (pre-1.0.0-hop, not `to`)")
PY

# Manifest-only no-op contract (mirrors 0.5.0 / 0.11.0): only
# .agent/manifest.json and .agent/sync-log.md should appear in
# `git status --short`. tracked_files lives inside the manifest, so
# this assertion is the byte-stable contract for downstream content.
actual_status="$(git -C "$fixture" status --short | LC_ALL=C sort)"
expected_status="$(printf ' M .agent/manifest.json\n M .agent/sync-log.md')"
if [ "$actual_status" != "$expected_status" ]; then
  printf 'FAIL: [clean-from-0.11.0] no-op contract changed unexpected paths\n' >&2
  printf 'Expected:\n%s\n' "$expected_status" >&2
  printf 'Actual:\n%s\n' "$actual_status" >&2
  exit 1
fi
printf 'PASS: [clean-from-0.11.0] only manifest and sync-log changed (downstream content untouched)\n'

# Sync-log heading appended.
if ! grep -qF "Sync to 1.0.0" "$fixture/.agent/sync-log.md"; then
  printf 'FAIL: sync-log missing "Sync to 1.0.0" heading\n' >&2
  exit 1
fi
printf 'PASS: sync-log appended with "Sync to 1.0.0" entry\n'

(
  cd "$fixture"
  git -c user.email=t@t -c user.name=Test add .
  git -c user.email=t@t -c user.name=Test commit -q -m "first 1.0.0 apply"
)

# Idempotent re-apply (current-version shortcut).
AGENT_SYNC_NOW=2026-05-06T00:03:00Z \
  "$root/scripts/agent-sync.sh" --target "$fixture" --to 1.0.0 --apply
remove_pycache "$fixture"

if [ -n "$(git -C "$fixture" status --short)" ]; then
  git -C "$fixture" status --short
  printf 'FAIL: [clean-from-0.11.0] re-apply produced changes (current-version shortcut leaked)\n' >&2
  exit 1
fi
printf 'PASS: [clean-from-0.11.0] idempotent re-apply\n'

printf '\nAll checksum-backfill assertions passed.\n'
