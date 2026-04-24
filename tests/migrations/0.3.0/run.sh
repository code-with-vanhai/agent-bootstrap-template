#!/usr/bin/env bash
set -euo pipefail

root="$(git rev-parse --show-toplevel)"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

cp -a "$root/tests/migrations/0.3.0/before/." "$work/"
( cd "$work" && git init -q && git add . && git -c user.email=test@example.com -c user.name='Test User' commit -q -m "fixture" )

AGENT_SYNC_NOW=2026-04-23T00:00:00Z \
  "$root/scripts/agent-sync.sh" \
  --target "$work" \
  --to 0.3.0 \
  --apply

diff -r "$root/tests/migrations/0.3.0/after/" "$work/" \
  --exclude=.git

( cd "$work" && git add . && git -c user.email=test@example.com -c user.name='Test User' commit -q -m "first apply" )

# Current-version shortcut must be a clean no-op.
AGENT_SYNC_NOW=2026-04-23T00:00:00Z \
  "$root/scripts/agent-sync.sh" \
  --target "$work" \
  --to 0.3.0 \
  --apply

if [ -n "$(git -C "$work" status --short)" ]; then
  git -C "$work" status --short
  printf 'Current-version no-op produced changes.\n' >&2
  exit 1
fi

python3 - "$work/.agent/manifest.json" <<'PY'
import json
import sys
from collections import OrderedDict

path = sys.argv[1]
with open(path, "r", encoding="utf-8") as fh:
    data = json.load(fh, object_pairs_hook=OrderedDict)

data["synced_to_template_version"] = "0.2.0"
data["template_version"] = "0.2.0"

with open(path, "w", encoding="utf-8") as fh:
    json.dump(data, fh, indent=2)
    fh.write("\n")
PY
rm "$work/.agent/sync-log.md"
( cd "$work" && git add . && git -c user.email=test@example.com -c user.name='Test User' commit -q -m "reset sync marker" )

# This apply exercises byte-exact ours==theirs, patch skip_if_contains,
# wrapper no-op, and append_unique behavior instead of the version shortcut.
AGENT_SYNC_NOW=2026-04-23T00:00:00Z \
  "$root/scripts/agent-sync.sh" \
  --target "$work" \
  --to 0.3.0 \
  --apply

diff -r "$root/tests/migrations/0.3.0/after/" "$work/" \
  --exclude=.git \
  --exclude=sync-log.md
