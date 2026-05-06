#!/usr/bin/env bash
# Stage 3.2 / AC-6 fixture — checksum fast-path skips ``v<from>`` entirely.
#
# Setup:
#   1. Build a 0.3.0 fixture from tests/migrations/0.3.0/after.
#   2. Inject manifest.tracked_files for every safe_overwrite target the
#      0.3.0 -> 0.4.0 migration would touch, with sha256 of the actual
#      bytes on disk. This simulates what the Stage 3.3 backfill will do.
#   3. Clone the template into a separate directory and DELETE v0.3.0
#      from the clone. The clone keeps v0.4.0 (needed for ``theirs``).
#   4. Run agent-sync against the fixture using the clone as
#      --template-root. Every safe_overwrite entry must take the
#      checksum fast-path; if a single one falls through to 3-way merge,
#      the lazy tag check raises ``v0.3.0 requires tag v0.3.0``.
#
# A passing run is the AC-6 evidence: ``v<from>`` was not consulted.

set -euo pipefail

root="$(git rev-parse --show-toplevel)"
work_root="$(mktemp -d /tmp/migration-fastpath-clean.XXXXXX)"
trap 'rm -rf "$work_root"' EXIT

for tag in v0.3.0 v0.4.0; do
  if ! git -C "$root" rev-parse --verify --quiet "${tag}^{commit}" >/dev/null; then
    printf 'SKIP: %s missing from local repo; cannot run Stage 3.2 fast-path fixture.\n' "$tag"
    exit 0
  fi
done

remove_pycache() { find "$1" -type d -name __pycache__ -prune -exec rm -rf {} +; }

fixture="$work_root/fixture"
cp -a "$root/tests/migrations/0.3.0/after/." "$fixture/"
(
  cd "$fixture"
  git init -q
  git -c user.email=t@t -c user.name=Test add .
  git -c user.email=t@t -c user.name=Test commit -q -m "fixture@0.3.0"
)

# Pre-create files that the 0.4.0 migration introduces but the 0.3.0
# baseline does not carry (e.g. scripts/agent-validate-plan.sh). The
# Stage 3.3 backfill will populate ``tracked_files`` for every managed
# path; for AC-6 the fixture mimics that post-backfill state by
# materialising every entry on disk so the fast-path can fire across
# the full safe_overwrite list. Using v0.4.0 bytes for these new files
# makes the fast-path branch take the noop arm (theirs == ours), which
# also exercises ``test_fast_path_noop_when_theirs_equals_ours``'s
# integration counterpart.
python3 - "$fixture" "$root" <<'PY'
import hashlib
import sys
from pathlib import Path

fixture = Path(sys.argv[1])
template_root = Path(sys.argv[2])
sys.path.insert(0, str(template_root / "scripts" / "lib"))

from agent_sync.git_ops import git_show  # noqa: E402
from agent_sync.io_utils import dump_manifest, read_json  # noqa: E402
from agent_sync.migrations import expand_file_entries, load_migration  # noqa: E402

manifest_path = fixture / ".agent" / "manifest.json"
manifest = read_json(manifest_path)
migration = load_migration(template_root, "0.3.0", "0.4.0")
entries, _, _ = expand_file_entries(template_root, migration, False, manifest)

# Step 1: pre-create any v0.4.0 entry whose target is absent. Without
# this every absent path would fall through to 3-way merge and pull
# v0.3.0 in for the base check (defeating AC-6).
materialised = []
for entry in entries:
    target = fixture / entry["target"]
    if target.is_file():
        continue
    bytes_at_to = git_show(template_root, "0.4.0", entry["source"], required=False)
    if bytes_at_to is None:
        raise SystemExit(f"FAIL: cannot read v0.4.0:{entry['source']}")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(bytes_at_to)
    materialised.append(entry["target"])

# Step 2: hash whatever is now on disk and inject tracked_files. This
# is the same shape the Stage 3.3 backfill will emit.
tracked = {}
for entry in entries:
    target = fixture / entry["target"]
    data = target.read_bytes()
    tracked[entry["target"]] = {
        "synced_at_version": "0.3.0",
        "synced_checksum_sha256": hashlib.sha256(data).hexdigest(),
    }

if not tracked:
    raise SystemExit("FAIL: tracked_files injection produced 0 entries")

manifest["tracked_files"] = tracked
manifest_path.write_bytes(dump_manifest(manifest))
print(f"materialised {len(materialised)} v0.4.0 entries; tracked_files covers {len(tracked)} paths")
PY

(
  cd "$fixture"
  git -c user.email=t@t -c user.name=Test add .
  git -c user.email=t@t -c user.name=Test commit -q -m "fixture@0.3.0+tracked_files"
)

# Build an ephemeral template clone that is missing v0.3.0.
template_clone="$work_root/template-clone"
git clone -q --no-hardlinks "$root" "$template_clone"
git -C "$template_clone" tag -d v0.3.0 >/dev/null 2>&1 || true

if git -C "$template_clone" rev-parse --verify --quiet "v0.3.0^{commit}" >/dev/null; then
  printf 'FAIL: v0.3.0 still present in template clone after tag -d.\n' >&2
  exit 1
fi
printf 'PASS: ephemeral template clone has v0.3.0 deleted\n'

if ! git -C "$template_clone" rev-parse --verify --quiet "v0.4.0^{commit}" >/dev/null; then
  printf 'FAIL: v0.4.0 missing from template clone (needed for theirs).\n' >&2
  exit 1
fi

# Run the runner from $root (this checkout is what we are testing) but
# point --template-root at the v0.3.0-less clone. AGENT_SYNC_NOW pins the
# sync timestamp so the sync-log line is byte-stable.
sync_log="$work_root/sync.out"
set +e
AGENT_SYNC_NOW=2026-05-06T00:00:00Z \
  python3 "$root/scripts/agent-sync.py" \
  --template-root "$template_clone" \
  --target "$fixture" \
  --to 0.4.0 \
  --apply \
  > "$sync_log" 2>&1
status=$?
set -e
remove_pycache "$fixture"

if [ "$status" -ne 0 ]; then
  printf 'FAIL: agent-sync exited with %d when v0.3.0 missing; fast-path did not cover every entry.\n' "$status" >&2
  cat "$sync_log" >&2
  exit 1
fi
printf 'PASS: agent-sync apply succeeded with v0.3.0 absent (fast-path covered every entry)\n'

# Manifest bumped.
if ! grep -qF '"synced_to_template_version": "0.4.0"' "$fixture/.agent/manifest.json"; then
  printf 'FAIL: manifest synced_to_template_version not bumped to 0.4.0.\n' >&2
  exit 1
fi
printf 'PASS: manifest bumped to 0.4.0\n'

# Sync-log carries the fast-path reason marker on at least one accepted line.
if ! grep -qF 'reason=checksum-fast-path' "$fixture/.agent/sync-log.md"; then
  printf 'FAIL: sync-log missing [reason=checksum-fast-path] marker.\n' >&2
  cat "$fixture/.agent/sync-log.md" >&2
  exit 1
fi
printf 'PASS: sync-log carries [reason=checksum-fast-path] marker\n'

printf '\nAll fastpath-clean assertions passed.\n'
