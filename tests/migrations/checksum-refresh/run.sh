#!/usr/bin/env bash
# Stage 3.3 (Stage 3.1 reuse) fixture — subsequent hops refresh
# tracked_files entries to the new content.
#
# After 1.0.0 backfills tracked_files with synced_at_version=0.11.0
# (the pre-hop version), a SUBSEQUENT migration that opts into
# update_tracked_files: true and writes new bytes to a tracked path
# must:
#   - record synced_at_version = the subsequent hop's `to`,
#   - record synced_checksum_sha256 = sha256(post-write bytes),
#   - leave entries for paths the subsequent hop does NOT touch
#     unchanged (still synced_at_version=0.11.0 / sha=disk-at-backfill).
#
# v1.0.0 is unreleased so we cannot rely on a real later release. The
# fixture builds a synthetic ``1.0.1`` migration in a temporary
# template clone, tags it ephemerally, and runs ``--to 1.0.1 --apply``
# against the post-1.0.0 fixture state. This isolates the refresh
# semantics without touching the live ``core/migrations/`` tree.

set -euo pipefail

root="$(git rev-parse --show-toplevel)"
work_root="$(mktemp -d /tmp/migration-checksum-refresh.XXXXXX)"

ephemeral_v100_real="0"

cleanup() {
  if [ "$ephemeral_v100_real" = "1" ]; then
    git -C "$root" tag -d v1.0.0 >/dev/null 2>&1 || true
  fi
  rm -rf "$work_root"
}
trap cleanup EXIT

ensure_real_tag() {
  if git -C "$root" rev-parse --verify --quiet "v$1^{commit}" >/dev/null; then
    return 0
  fi
  printf 'SKIP: v%s tag missing; cannot run Stage 3.3 refresh fixture.\n' "$1"
  exit 0
}

remove_pycache() { find "$1" -type d -name __pycache__ -prune -exec rm -rf {} +; }

ensure_real_tag "0.10.0"
ensure_real_tag "0.11.0"

# Seed an ephemeral v1.0.0 tag in the live repo so the 1.0.0 migration
# resolves its replace_from_git_tag SHA.
if ! git -C "$root" rev-parse --verify --quiet "v1.0.0^{commit}" >/dev/null; then
  git -C "$root" tag v1.0.0
  ephemeral_v100_real="1"
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

# ---------- Step 1: build a 1.0.0 fixture (backfill state) ----------
fixture="$work_root/clean-from-1.0.0"
cp -a "$root/tests/migrations/0.3.0/after/." "$fixture/"
(
  cd "$fixture"
  git init -q
  git -c user.email=t@t -c user.name=Test add .
  git -c user.email=t@t -c user.name=Test commit -q -m "fixture@0.3.0"
)

AGENT_SYNC_NOW=2026-05-06T00:00:00Z \
  "$root/scripts/agent-sync.sh" --multi-hop --target "$fixture" --to 0.10.0 --apply \
    --accept-theirs scripts/agent-eval.sh >/dev/null
remove_pycache "$fixture"
(
  cd "$fixture"
  git -c user.email=t@t -c user.name=Test add .
  git -c user.email=t@t -c user.name=Test commit -q -m "fixture@0.10.0"
)

AGENT_SYNC_NOW=2026-05-06T00:01:00Z \
  "$root/scripts/agent-sync.sh" --target "$fixture" --to 0.11.0 --apply >/dev/null
remove_pycache "$fixture"
(
  cd "$fixture"
  git -c user.email=t@t -c user.name=Test add .
  git -c user.email=t@t -c user.name=Test commit -q -m "fixture@0.11.0"
)

AGENT_SYNC_NOW=2026-05-06T00:02:00Z \
  "$root/scripts/agent-sync.sh" --target "$fixture" --to 1.0.0 --apply >/dev/null
remove_pycache "$fixture"
(
  cd "$fixture"
  git -c user.email=t@t -c user.name=Test add .
  git -c user.email=t@t -c user.name=Test commit -q -m "fixture@1.0.0+backfill"
)

backfill_rb_sha="$(python3 -c "
import json, sys
m = json.load(open(sys.argv[1]))
print(m['tracked_files']['.agent/rulebase.md']['synced_checksum_sha256'])
" "$fixture/.agent/manifest.json")"
backfill_rb_ver="$(python3 -c "
import json, sys
m = json.load(open(sys.argv[1]))
print(m['tracked_files']['.agent/rulebase.md']['synced_at_version'])
" "$fixture/.agent/manifest.json")"
assert_eq "$backfill_rb_ver" "0.11.0" "[step 1] rulebase.md backfill version is 0.11.0 (pre-hop)"
printf 'PASS: [step 1] backfilled rulebase.md sha = %s\n' "$backfill_rb_sha"

# ---------- Step 2: synthesize a 1.0.1 template clone ----------
template_clone="$work_root/template-clone"
git clone -q --no-hardlinks "$root" "$template_clone"

# Drop any stale ephemeral 1.0.0 tag the parent process created, then
# re-tag at HEAD inside the clone so the 1.0.0 migration's
# replace_from_git_tag still resolves inside the clone.
git -C "$template_clone" tag -d v1.0.0 >/dev/null 2>&1 || true
git -C "$template_clone" tag v1.0.0

# Author a 1.0.1 migration that DOES write new bytes to one canonical
# path (.agent/rulebase.md) plus opts into update_tracked_files. Use a
# temp-only canonical sentinel inside the clone so the rest of the
# canonical_files set stays untouched.
mkdir -p "$template_clone/core/migrations/1.0.1"
cat > "$template_clone/core/migrations/1.0.1/migration.json" <<'JSON'
{
  "schema_version": 1,
  "version": "1.0.1",
  "from_versions": ["1.0.0"],
  "to": "1.0.1",
  "safe_overwrite": [
    {
      "source": "core/rulebase.template.md",
      "target": ".agent/rulebase.md"
    }
  ],
  "patches": [],
  "manifest_updates": {
    "replace": {
      "template_version": "1.0.1",
      "synced_to_template_version": "1.0.1"
    },
    "replace_from_git_tag": {
      "synced_to_template_commit": "1.0.1"
    },
    "append_to_array_unique": {
      "notes": "Synthetic 1.0.1 hop for tests/migrations/checksum-refresh."
    },
    "merge_array_unique": {},
    "update_tracked_files": true
  }
}
JSON

# Materially mutate core/rulebase.template.md inside the clone so the
# 1.0.1 hop has new bytes vs. v1.0.0 (and vs. the fixture's on-disk
# rulebase). This is the byte mutation that drives the refresh.
printf '\n<!-- 1.0.1 refresh-test marker -->\n' \
  >> "$template_clone/core/rulebase.template.md"
(
  cd "$template_clone"
  git -c user.email=t@t -c user.name=Test add core/migrations/1.0.1 core/rulebase.template.md
  git -c user.email=t@t -c user.name=Test commit -q -m "synthetic 1.0.1"
  git tag v1.0.1
)

# ---------- Step 3: apply 1.0.1 against the post-backfill fixture ----------
AGENT_SYNC_NOW=2026-05-06T00:03:00Z \
  python3 "$root/scripts/agent-sync.py" \
    --template-root "$template_clone" \
    --target "$fixture" \
    --to 1.0.1 \
    --apply
remove_pycache "$fixture"

# Refresh assertions inspected via Python.
python3 - "$fixture" "$backfill_rb_sha" <<'PY'
import hashlib
import json
import sys
from pathlib import Path

fixture = Path(sys.argv[1])
backfill_sha = sys.argv[2]
manifest = json.loads((fixture / ".agent" / "manifest.json").read_text(encoding="utf-8"))

tracked = manifest.get("tracked_files") or {}
rulebase = tracked.get(".agent/rulebase.md")
if not rulebase:
    raise SystemExit("FAIL: tracked_files dropped .agent/rulebase.md after the refresh hop")

# 1) Refreshed entry must record the new hop's `to` version.
if rulebase["synced_at_version"] != "1.0.1":
    raise SystemExit(
        f"FAIL: rulebase synced_at_version={rulebase['synced_at_version']!r}, "
        "expected 1.0.1 (post-refresh)"
    )
print("PASS: [refresh] rulebase.md synced_at_version bumped to 1.0.1")

# 2) Recorded sha must match the bytes now on disk (the 1.0.1 theirs).
disk_sha = hashlib.sha256(
    (fixture / ".agent/rulebase.md").read_bytes()
).hexdigest()
if rulebase["synced_checksum_sha256"] != disk_sha:
    raise SystemExit(
        f"FAIL: rulebase sha={rulebase['synced_checksum_sha256']} != "
        f"sha(disk)={disk_sha}"
    )
print("PASS: [refresh] rulebase.md sha256 matches the new on-disk bytes")

# 3) The recorded sha MUST differ from the backfill-time sha (otherwise
#    the 1.0.1 hop did not actually rewrite the file and the refresh
#    contract is vacuous).
if rulebase["synced_checksum_sha256"] == backfill_sha:
    raise SystemExit(
        "FAIL: refresh sha equals backfill sha; the synthetic 1.0.1 hop "
        "did not actually mutate rulebase bytes"
    )
print("PASS: [refresh] rulebase.md sha256 differs from the backfill-time sha")

# 4) Untouched paths preserve their backfill-time records.
unchanged_examples = [
    p for p in (".agent/gates.md", ".agent/ownership.md")
    if p in tracked
]
if not unchanged_examples:
    raise SystemExit("FAIL: no unchanged canonical paths found in tracked_files")
for path in unchanged_examples:
    record = tracked[path]
    if record["synced_at_version"] != "0.11.0":
        raise SystemExit(
            f"FAIL: {path} synced_at_version={record['synced_at_version']!r}, "
            "expected 0.11.0 (untouched by 1.0.1 hop)"
        )
print(
    f"PASS: [refresh] {len(unchanged_examples)} untouched canonical paths "
    "still record synced_at_version=0.11.0"
)
PY

# 5) The refresh hop wrote at least .agent/rulebase.md plus the
#    manifest + sync-log; assert that subset shows up in git status.
status="$(git -C "$fixture" status --short | LC_ALL=C sort)"
if ! grep -qF '.agent/rulebase.md' <<<"$status"; then
  printf 'FAIL: [refresh] rulebase.md missing from git status\n%s\n' "$status" >&2
  exit 1
fi
if ! grep -qF '.agent/manifest.json' <<<"$status"; then
  printf 'FAIL: [refresh] manifest.json missing from git status\n%s\n' "$status" >&2
  exit 1
fi
printf 'PASS: [refresh] git status includes rulebase.md + manifest.json\n'

printf '\nAll checksum-refresh assertions passed.\n'
