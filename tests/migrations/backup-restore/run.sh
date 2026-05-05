#!/usr/bin/env bash
# Stage 1.3 fixture (revision 7 of the 2026-05-05 migration UX plan):
#   apply --backup ; backups restore ; assert byte-identical round-trip
#   PLUS append-only sync-log invariant (D-5 / AC-3).
#
#   1) snapshot the pre-apply tree -> apply 0.6.0 with --backup -> restore
#      via `agent-sync.sh backups restore <id>`. The post-restore tree
#      must be byte-identical to the pre-apply snapshot for every
#      touched path.
#   2) the pre-apply sync-log must remain a strict prefix of the
#      post-restore sync-log; restore must NOT truncate.
#   3) seeding 7 backups with --backup-keep 5 must leave exactly 5
#      backups on disk (D-3 retention).

set -euo pipefail

root="$(git rev-parse --show-toplevel)"
work_root="$(mktemp -d /tmp/migration-backup-restore.XXXXXX)"
trap 'rm -rf "$work_root"' EXIT

export XDG_CACHE_HOME="$work_root/cache"
mkdir -p "$XDG_CACHE_HOME"

# Step 1 — fixture at 0.5.0 (post-apply state of tests/migrations/0.5.0).
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

AGENT_SYNC_NOW=2026-05-05T00:01:00Z \
  "$root/scripts/agent-sync.sh" --target "$work" --to 0.5.0 --apply >/dev/null
( cd "$work"
  git -c user.email=t@t -c user.name=Test add .
  git -c user.email=t@t -c user.name=Test commit -q -m fixture@0.5.0 )

# Capture the pre-apply snapshot of every file the 0.6.0 migration may
# touch. We use a copy of the entire .agent + scripts tree so the
# round-trip check is comprehensive.
pre_snapshot="$work_root/pre-snapshot"
mkdir -p "$pre_snapshot"
( cd "$work" && tar -cf - --exclude=.git . ) | ( cd "$pre_snapshot" && tar -xf - )
pre_log="$work_root/pre-sync-log.md"
cp "$work/.agent/sync-log.md" "$pre_log"

# Step 2 — apply 0.6.0 with --backup, then commit so worktree is clean
# for the restore step.
AGENT_SYNC_NOW=2026-05-05T00:02:00Z \
  "$root/scripts/agent-sync.sh" --target "$work" --to 0.6.0 --apply --backup \
    >/dev/null
( cd "$work"
  git -c user.email=t@t -c user.name=Test add .
  git -c user.email=t@t -c user.name=Test commit -q -m apply@0.6.0 )

# Capture the log RIGHT BEFORE restore (i.e. the post-apply state).
# Append-only invariant per D-5 + AC-3 means this content must remain a
# strict prefix of the post-restore log. The earlier `pre_log` capture
# is too lenient — it would still hold even if restore truncated the
# apply entry — so we keep both checks.
mid_log="$work_root/mid-sync-log.md"
cp "$work/.agent/sync-log.md" "$mid_log"
mid_apply_entries="$(grep -c '^## ' "$mid_log")"

backup_id="$(ls "$XDG_CACHE_HOME/agent-bootstrap/backups/"* | head -1 | xargs -n1 basename | head -1)"
# The basename above might pick the parent dir; resolve more carefully:
backup_dir="$(find "$XDG_CACHE_HOME/agent-bootstrap/backups" -mindepth 2 -maxdepth 2 -type d | sort | tail -1)"
backup_id="$(basename "$backup_dir")"

# Step 3 — restore.
"$root/scripts/agent-sync.sh" backups restore "$backup_id" --target "$work" \
  >/dev/null

# Step 4 — assert each touched path is byte-identical to the pre-apply
# snapshot. Read meta.json::entries and diff each one. Exclude
# `.agent/sync-log.md` — restore appends a Restore entry to it (D-5),
# so the append-only invariant is verified separately below.
fail=0
while read -r rel pre_state; do
  if [ "$rel" = ".agent/sync-log.md" ]; then
    continue
  fi
  case "$pre_state" in
    present)
      if ! diff -q "$pre_snapshot/$rel" "$work/$rel" >/dev/null; then
        printf 'FAIL: round-trip mismatch on %s\n' "$rel" >&2
        diff "$pre_snapshot/$rel" "$work/$rel" >&2 || true
        fail=1
      fi
      ;;
    absent)
      if [ -e "$work/$rel" ]; then
        printf 'FAIL: file should be absent after restore: %s\n' "$rel" >&2
        fail=1
      fi
      ;;
  esac
done < <(python3 -c "
import json, sys
data = json.load(open(sys.argv[1]))
for e in data.get('entries', []):
    print(e['path'], e['pre_state'])
" "$backup_dir/meta.json")

if [ "$fail" = "0" ]; then
  printf 'PASS: every touched file restored to pre-apply bytes\n'
else
  exit 1
fi

# Step 5 — append-only sync-log invariant (D-5 / AC-3).
# Two prefix checks: pre_log (before apply) AND mid_log (after apply,
# before restore). The mid_log check catches the bug where restore
# silently overwrites sync-log.md with the pre-apply snapshot, deleting
# the apply entry that the just-completed sync just appended.
post_log="$work/.agent/sync-log.md"
pre_size="$(wc -c <"$pre_log")"
mid_size="$(wc -c <"$mid_log")"
post_size="$(wc -c <"$post_log")"

if [ "$post_size" -le "$mid_size" ]; then
  printf 'FAIL: post-restore log must be strictly longer than the post-apply log\n' >&2
  printf '  pre_size=%s mid_size=%s post_size=%s\n' \
    "$pre_size" "$mid_size" "$post_size" >&2
  exit 1
fi
if ! head -c "$pre_size" "$post_log" | cmp - "$pre_log" >/dev/null; then
  printf 'FAIL: pre-apply sync-log is not a prefix of post-restore log\n' >&2
  exit 1
fi
if ! head -c "$mid_size" "$post_log" | cmp - "$mid_log" >/dev/null; then
  printf 'FAIL: post-apply sync-log is not a prefix of post-restore log\n' >&2
  printf '       restore truncated the apply entry; D-5 violation\n' >&2
  diff <(head -c "$mid_size" "$post_log") "$mid_log" | head -20 >&2 || true
  exit 1
fi
printf 'PASS: sync-log append-only invariant holds across apply+restore\n'

post_apply_entries="$(grep -c '^## ' "$post_log")"
expected_post="$((mid_apply_entries + 1))"
if [ "$post_apply_entries" -ne "$expected_post" ]; then
  printf 'FAIL: expected %s log entries after restore, got %s (apply entry deleted?)\n' \
    "$expected_post" "$post_apply_entries" >&2
  cat "$post_log" >&2
  exit 1
fi
printf 'PASS: post-restore log has exactly mid+1 entries (apply preserved + Restore appended)\n'

if grep -F "Restore $backup_id" "$post_log" >/dev/null; then
  printf 'PASS: post-restore log records a Restore entry\n'
else
  printf 'FAIL: missing Restore entry in post-restore sync-log\n' >&2
  exit 1
fi

# Step 5b — First sync: target has no ``.agent/sync-log.md`` before
# apply, so ``create_backup`` does not write ``sync-log.md.snapshot``.
# Restore must still append a Restore audit line (never gated on snapshot).
work_fs="$work_root/first-sync-target"
mkdir -p "$work_fs"
cp -a "$root/tests/migrations/0.3.0/before/." "$work_fs/"
( cd "$work_fs" && git init -q
  git -c user.email=t@t -c user.name=Test add .
  git -c user.email=t@t -c user.name=Test commit -q -m fixture@0.2.0 )
if [ -f "$work_fs/.agent/sync-log.md" ]; then
  printf 'FAIL: first-sync fixture must not ship sync-log.md\n' >&2
  exit 1
fi

AGENT_SYNC_NOW=2026-06-01T00:00:00Z \
  "$root/scripts/agent-sync.sh" --target "$work_fs" --to 0.3.0 --apply --backup \
    >/dev/null
( cd "$work_fs"
  find . -type d -name __pycache__ -prune -exec rm -rf {} +
  git -c user.email=t@t -c user.name=Test add .
  git -c user.email=t@t -c user.name=Test commit -q -m apply@0.3.0 )

target_sha_fs="$(python3 -c "
import hashlib, sys
print(hashlib.sha1(sys.argv[1].encode('utf-8')).hexdigest()[:12])
" "$(realpath "$work_fs")")"
first_b_root="$XDG_CACHE_HOME/agent-bootstrap/backups/$target_sha_fs"
backup_dir_fs="$(find "$first_b_root" -mindepth 1 -maxdepth 1 -type d | sort | tail -1)"
if [ ! -d "$backup_dir_fs" ]; then
  printf 'FAIL: expected a backup dir under %s\n' "$first_b_root" >&2
  exit 1
fi
if [ -f "$backup_dir_fs/sync-log.md.snapshot" ]; then
  printf 'FAIL: first-sync backup must not create sync-log.md.snapshot\n' >&2
  exit 1
fi
mid_fs="$(grep -c '^## ' "$work_fs/.agent/sync-log.md")"
backup_id_fs="$(basename "$backup_dir_fs")"

"$root/scripts/agent-sync.sh" backups restore "$backup_id_fs" --target "$work_fs" \
  >/dev/null

post_fs="$(grep -c '^## ' "$work_fs/.agent/sync-log.md")"
expected_fs="$((mid_fs + 1))"
if [ "$post_fs" -ne "$expected_fs" ]; then
  printf 'FAIL: first-sync restore expected %s log entries, got %s\n' \
    "$expected_fs" "$post_fs" >&2
  cat "$work_fs/.agent/sync-log.md" >&2
  exit 1
fi
if ! grep -F "Restore $backup_id_fs" "$work_fs/.agent/sync-log.md" >/dev/null; then
  printf 'FAIL: first-sync restore missing Restore line\n' >&2
  exit 1
fi
printf 'PASS: first-sync backup (no log snapshot) still appends Restore entry\n'

# Step 6 — D-3 retention. Seed 7 dummy backups directly via the helper
# (we already know create_backup is exercised; here we test prune).
target_sha="$(python3 -c "
import hashlib, sys
print(hashlib.sha1(sys.argv[1].encode('utf-8')).hexdigest()[:12])
" "$(realpath "$work")")"
seed_root="$XDG_CACHE_HOME/agent-bootstrap/backups/$target_sha"
for i in 1 2 3 4 5 6 7; do
  seeded="$seed_root/2026-05-05T00-0${i}-00Z-0.5.0-0.6.0"
  mkdir -p "$seeded/files"
  cat >"$seeded/meta.json" <<JSON
{"target": "$work", "from_version": "0.5.0", "to_version": "0.6.0", "mode": "seed", "created_at": "2026-05-05T00:0${i}:00Z", "entries": []}
JSON
done

"$root/scripts/agent-sync.sh" backups prune --target "$work" --keep 5 >/dev/null

remaining="$(ls "$seed_root" | wc -l | tr -d ' ')"
if [ "$remaining" != "5" ]; then
  printf 'FAIL: expected 5 backups after prune, got %s\n' "$remaining" >&2
  ls "$seed_root" >&2
  exit 1
fi
printf 'PASS: backups prune --keep 5 retains exactly 5 most-recent backups\n'

printf 'All backup-restore tests passed.\n'
