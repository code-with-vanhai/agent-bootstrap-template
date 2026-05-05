#!/usr/bin/env bash
# Stage 1.2 fixture (revision 7 of the 2026-05-05 migration UX plan):
#   With --verbose, every dry-run / apply prints the Pre-flight summary
#   block before any disk write. The block includes the target path,
#   from/to versions, the walk display, worktree state, and a
#   "Customized files: <N>" line so CI logs make planning visible.

set -euo pipefail

root="$(git rev-parse --show-toplevel)"
work_root="$(mktemp -d /tmp/migration-preflight.XXXXXX)"
trap 'rm -rf "$work_root"' EXIT

assert_contains() {
  local needle="$1" path="$2" desc="$3"
  if grep -F -- "$needle" "$path" >/dev/null; then
    printf 'PASS: %s\n' "$desc"
  else
    printf 'FAIL: %s\n  needle: %q\n  file:   %s\n' "$desc" "$needle" "$path" >&2
    cat "$path" >&2
    exit 1
  fi
}

work="$work_root/repo"
mkdir -p "$work"
cp -a "$root/tests/migrations/0.3.0/before/." "$work/"
( cd "$work" && git init -q
  git -c user.email=t@t -c user.name=Test add .
  git -c user.email=t@t -c user.name=Test commit -q -m fixture )

# Dry-run with --verbose: must emit the preflight block on stdout.
dry_out="$work_root/dry.out"
AGENT_SYNC_NOW=2026-05-05T00:00:00Z \
  "$root/scripts/agent-sync.sh" --target "$work" --to 0.3.0 --verbose \
    >"$dry_out" 2>&1

assert_contains "Pre-flight summary" "$dry_out" \
  "[dry-run] preflight header printed"
assert_contains "Current version:  0.2.0" "$dry_out" \
  "[dry-run] preflight reports current version"
assert_contains "Target version:   0.3.0" "$dry_out" \
  "[dry-run] preflight reports target version"
assert_contains "Worktree:         clean" "$dry_out" \
  "[dry-run] preflight reports clean worktree"
assert_contains "Customized files:" "$dry_out" \
  "[dry-run] preflight reports customization count"
assert_contains "Backup:           disabled (pass --backup to enable)" \
  "$dry_out" "[dry-run] preflight reports backup default"

# Revision-7 review fix: "Planned changes" must be the authoritative
# post-planner count, not the pre-planner heuristic. Compare with the
# count of "  update <path>" lines from the same dry-run.
planned_n="$(grep -E '^  Planned changes:  [0-9]+ writes' "$dry_out" \
  | sed -E 's/^  Planned changes:  ([0-9]+) writes.*/\1/' | tail -1)"
update_n="$(grep -c '^  update ' "$dry_out")"
if [ -z "$planned_n" ] || [ "$planned_n" = "0" ]; then
  printf 'FAIL: [dry-run] could not parse "Planned changes" count\n' >&2
  cat "$dry_out" >&2
  exit 1
fi
if [ "$planned_n" != "$update_n" ]; then
  printf 'FAIL: [dry-run] preflight write count (%s) != actual updates (%s)\n' \
    "$planned_n" "$update_n" >&2
  exit 1
fi
printf 'PASS: [dry-run] preflight write count matches actual planned updates (%s)\n' "$planned_n"

# Without --verbose and stdout redirected (non-TTY), the block must not
# appear so CI logs stay short.
quiet_out="$work_root/quiet.out"
AGENT_SYNC_NOW=2026-05-05T00:00:00Z \
  "$root/scripts/agent-sync.sh" --target "$work" --to 0.3.0 \
    >"$quiet_out" 2>&1
if grep -q "Pre-flight summary" "$quiet_out"; then
  printf 'FAIL: [quiet] preflight block leaked into non-TTY default run\n' >&2
  cat "$quiet_out" >&2
  exit 1
fi
printf 'PASS: [quiet] preflight is suppressed on non-TTY without --verbose\n'

# Apply path: --verbose + --apply must still emit the preflight block.
apply_out="$work_root/apply.out"
AGENT_SYNC_NOW=2026-05-05T00:00:00Z \
  "$root/scripts/agent-sync.sh" --target "$work" --to 0.3.0 --apply --verbose \
    >"$apply_out" 2>&1

assert_contains "Pre-flight summary" "$apply_out" \
  "[apply] preflight header printed before apply"

printf 'All preflight-output migration tests passed.\n'
