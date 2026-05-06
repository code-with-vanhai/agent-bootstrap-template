#!/usr/bin/env bash
# Stage 3.2 / D-8 fixture — checksum mismatch falls through to 3-way merge,
# the lazy tag check fires for ``v<from>``, and the existing
# "git fetch --tags" hint reappears.
#
# Setup mirrors fastpath-clean except one tracked file is mutated AFTER
# tracked_files is populated, so its on-disk sha no longer matches the
# recorded baseline. That entry skips the fast-path and falls through to
# 3-way merge, which calls ``_ensure_tags_for_three_way`` and raises
# ``UsageError`` because v0.3.0 was deleted from the template clone.
#
# A passing run is the D-8 evidence: when the fast-path cannot cover an
# entry, the lazy tag check surfaces the actionable hint (instead of a
# silent fall-through that would attempt 3-way without ``v<from>`` and
# eventually emit a generic CONFLICT).

set -euo pipefail

root="$(git rev-parse --show-toplevel)"
work_root="$(mktemp -d /tmp/migration-fastpath-modified.XXXXXX)"
trap 'rm -rf "$work_root"' EXIT

for tag in v0.3.0 v0.4.0; do
  if ! git -C "$root" rev-parse --verify --quiet "${tag}^{commit}" >/dev/null; then
    printf 'SKIP: %s missing from local repo; cannot run Stage 3.2 fastpath-modified fixture.\n' "$tag"
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

# Materialise v0.4.0-only entries, hash everything, inject tracked_files.
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

for entry in entries:
    target = fixture / entry["target"]
    if target.is_file():
        continue
    bytes_at_to = git_show(template_root, "0.4.0", entry["source"], required=False)
    if bytes_at_to is None:
        raise SystemExit(f"FAIL: cannot read v0.4.0:{entry['source']}")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(bytes_at_to)

tracked = {}
for entry in entries:
    target = fixture / entry["target"]
    data = target.read_bytes()
    tracked[entry["target"]] = {
        "synced_at_version": "0.3.0",
        "synced_checksum_sha256": hashlib.sha256(data).hexdigest(),
    }

manifest["tracked_files"] = tracked
manifest_path.write_bytes(dump_manifest(manifest))
PY

(
  cd "$fixture"
  git -c user.email=t@t -c user.name=Test add .
  git -c user.email=t@t -c user.name=Test commit -q -m "fixture@0.3.0+tracked_files"
)

# Customize one tracked file AFTER tracked_files was populated so its
# sha no longer matches the recorded baseline. This forces the entry
# off the fast-path.
echo "# user comment - drift to force fall-through" >> "$fixture/scripts/agent-validate.sh"
(
  cd "$fixture"
  git -c user.email=t@t -c user.name=Test add scripts/agent-validate.sh
  git -c user.email=t@t -c user.name=Test commit -q -m "user customization"
)

# Build an ephemeral template clone that is missing v0.3.0.
template_clone="$work_root/template-clone"
git clone -q --no-hardlinks "$root" "$template_clone"
git -C "$template_clone" tag -d v0.3.0 >/dev/null 2>&1 || true
if git -C "$template_clone" rev-parse --verify --quiet "v0.3.0^{commit}" >/dev/null; then
  printf 'FAIL: v0.3.0 still present in template clone after tag -d.\n' >&2
  exit 1
fi

sync_out="$work_root/sync.out"
set +e
AGENT_SYNC_NOW=2026-05-06T00:00:00Z \
  python3 "$root/scripts/agent-sync.py" \
  --template-root "$template_clone" \
  --target "$fixture" \
  --to 0.4.0 \
  --apply \
  > "$sync_out" 2>&1
status=$?
set -e
remove_pycache "$fixture"

if [ "$status" -eq 0 ]; then
  printf 'FAIL: agent-sync should have aborted when modified entry falls through with v0.3.0 missing.\n' >&2
  cat "$sync_out" >&2
  exit 1
fi
printf 'PASS: agent-sync aborted (exit=%d) when modified entry could not fast-path\n' "$status"

if ! grep -qF 'requires tag v0.3.0' "$sync_out"; then
  printf 'FAIL: stderr missing "requires tag v0.3.0" hint.\n' >&2
  cat "$sync_out" >&2
  exit 1
fi
if ! grep -qF 'git fetch --tags' "$sync_out"; then
  printf 'FAIL: stderr missing "git fetch --tags" hint.\n' >&2
  cat "$sync_out" >&2
  exit 1
fi
printf 'PASS: stderr carries actionable "git fetch --tags" hint\n'

# No partial writes: target tree must be byte-identical to the pre-run state.
remaining_changes="$(git -C "$fixture" status --porcelain)"
if [ -n "$remaining_changes" ]; then
  printf 'FAIL: aborted run left changes in target tree:\n%s\n' "$remaining_changes" >&2
  exit 1
fi
printf 'PASS: aborted run left target tree byte-identical\n'

printf '\nAll fastpath-modified assertions passed.\n'
