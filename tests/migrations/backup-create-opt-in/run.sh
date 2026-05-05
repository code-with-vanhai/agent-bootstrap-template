#!/usr/bin/env bash
# Stage 1.3 fixture (revision 7 of the 2026-05-05 migration UX plan):
#   --backup is opt-in (D-2 default off) and the snapshot lives outside
#   the target repo (D-4 external cache) so the target's git status
#   stays byte-identical to existing fixtures.

set -euo pipefail

root="$(git rev-parse --show-toplevel)"
work_root="$(mktemp -d /tmp/migration-backup-opt-in.XXXXXX)"
trap 'rm -rf "$work_root"' EXIT

# Use an ephemeral cache so the test never writes into ~/.cache.
export XDG_CACHE_HOME="$work_root/cache"
mkdir -p "$XDG_CACHE_HOME"

# Build a fixture sitting at 0.4.0 with a normal apply already committed.
work="$work_root/target"
mkdir -p "$work"
cp -a "$root/tests/migrations/0.3.0/after/." "$work/"
( cd "$work" && git init -q
  git -c user.email=t@t -c user.name=Test add .
  git -c user.email=t@t -c user.name=Test commit -q -m fixture@0.3.0 )

AGENT_SYNC_NOW=2026-05-05T00:00:00Z \
  "$root/scripts/agent-sync.sh" --target "$work" --to 0.4.0 --apply >/dev/null
( cd "$work"
  git -c user.email=t@t -c user.name=Test add .
  git -c user.email=t@t -c user.name=Test commit -q -m fixture@0.4.0 )

# 1) Apply 0.5.0 WITHOUT --backup. D-2: default off must not write any
#    backup directory. Use 0.5.0 because it is a no-op data migration
#    (per tests/migrations/0.5.0/run.sh:119) so the post-apply tree is
#    a stable byte-identical reference.
work_default="$work_root/target-default"
cp -a "$work" "$work_default"
AGENT_SYNC_NOW=2026-05-05T00:01:00Z \
  "$root/scripts/agent-sync.sh" --target "$work_default" --to 0.5.0 --apply \
    >/dev/null

actual_status="$(git -C "$work_default" status --short | LC_ALL=C sort)"
expected_status="$(printf ' M .agent/manifest.json\n M .agent/sync-log.md')"
if [ "$actual_status" != "$expected_status" ]; then
  printf 'FAIL: --backup default-off changed unexpected paths\n' >&2
  printf 'Expected:\n%s\n' "$expected_status" >&2
  printf 'Actual:\n%s\n' "$actual_status" >&2
  exit 1
fi
printf 'PASS: default-off keeps target tree unchanged outside manifest+sync-log\n'

if [ -d "$XDG_CACHE_HOME/agent-bootstrap" ]; then
  printf 'FAIL: backup cache materialized despite no --backup flag\n' >&2
  exit 1
fi
printf 'PASS: default-off does not materialize $XDG_CACHE_HOME/agent-bootstrap\n'

# 2) Apply 0.5.0 WITH --backup on a parallel target. The git status of
#    the target must be byte-identical to the default-off run, and the
#    backup must materialize OUTSIDE the target tree.
work_backup="$work_root/target-backup"
cp -a "$work" "$work_backup"
AGENT_SYNC_NOW=2026-05-05T00:02:00Z \
  "$root/scripts/agent-sync.sh" --target "$work_backup" --to 0.5.0 --apply --backup \
    >/dev/null

if ! ls "$XDG_CACHE_HOME/agent-bootstrap/backups/"*"/" >/dev/null 2>&1; then
  printf 'FAIL: --backup did not write to $XDG_CACHE_HOME/agent-bootstrap/backups\n' >&2
  exit 1
fi
printf 'PASS: --backup writes to $XDG_CACHE_HOME/agent-bootstrap/backups\n'

backup_dir="$(find "$XDG_CACHE_HOME/agent-bootstrap/backups" -mindepth 2 -maxdepth 2 -type d | head -1)"
if [ ! -f "$backup_dir/meta.json" ]; then
  printf 'FAIL: backup is missing meta.json at %s\n' "$backup_dir" >&2
  exit 1
fi
if ! python3 -c "
import json, sys
m = json.load(open(sys.argv[1]))
assert 'entries' in m and isinstance(m['entries'], list)
assert any(e.get('pre_state') == 'present' for e in m['entries']), 'no pre_state=present entries'
" "$backup_dir/meta.json"; then
  printf 'FAIL: backup meta.json is malformed (%s)\n' "$backup_dir/meta.json" >&2
  exit 1
fi
printf 'PASS: backup meta.json contains pre_state entries\n'

actual_status_backup="$(git -C "$work_backup" status --short | LC_ALL=C sort)"
if [ "$actual_status_backup" != "$expected_status" ]; then
  printf 'FAIL: --backup wrote into the target tree (unexpected paths)\n' >&2
  git -C "$work_backup" status --short >&2
  exit 1
fi
printf 'PASS: --backup leaves target tree byte-identical to default-off run\n'

printf 'All backup-create-opt-in tests passed.\n'
