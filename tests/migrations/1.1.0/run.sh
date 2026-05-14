#!/usr/bin/env bash
set -euo pipefail

root="$(git rev-parse --show-toplevel)"
work_root="$(mktemp -d /tmp/migration-110.XXXXXX)"
ephemeral_tags=""

cleanup() {
  for tag in $ephemeral_tags; do
    git -C "$root" tag -d "$tag" >/dev/null 2>&1 || true
  done
  rm -rf "$work_root"
}
trap cleanup EXIT

ensure_head_tag() {
  version="$1"
  if git -C "$root" rev-parse --verify --quiet "v$version^{commit}" >/dev/null; then
    return 0
  fi
  git -C "$root" tag "v$version"
  ephemeral_tags="$ephemeral_tags v$version"
}

tag_current_worktree() {
  version="$1"
  if git -C "$root" rev-parse --verify --quiet "v$version^{commit}" >/dev/null; then
    return 0
  fi
  index_file="$work_root/index-$version"
  GIT_INDEX_FILE="$index_file" git -C "$root" read-tree HEAD
  GIT_INDEX_FILE="$index_file" git -C "$root" add -A
  tree="$(GIT_INDEX_FILE="$index_file" git -C "$root" write-tree)"
  commit="$(printf 'ephemeral v%s\n' "$version" | git -C "$root" commit-tree "$tree" -p HEAD)"
  git -C "$root" tag "v$version" "$commit"
  ephemeral_tags="$ephemeral_tags v$version"
  rm -f "$index_file"
}

set_manifest_version() {
  fixture="$1"
  python3 - "$fixture/.agent/manifest.json" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
data = json.loads(path.read_text(encoding="utf-8"))
data["template_version"] = "1.0.0"
data["synced_to_template_version"] = "1.0.0"
data["synced_to_template_commit"] = "test-v1.0.0"
data.pop("tracked_files", None)
path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY
}

ensure_head_tag "1.0.0"
tag_current_worktree "1.1.0"

fixture="$work_root/repo"
mkdir -p "$fixture"
"$root/scripts/bootstrap-request.sh" \
  --harness generic \
  --features standard \
  --target "$fixture" >/dev/null 2>&1

rm -f \
  "$fixture/scripts/agent-lock.sh" \
  "$fixture/scripts/lib/agent_lock.py" \
  "$fixture/scripts/lib/gate_runner.py" \
  "$fixture/scripts/lib/secret_scan_redacted.py" \
  "$fixture/scripts/lib/agent_system_validation/monitored_paths.py"
printf '__pycache__/\n*.pyc\n' >"$fixture/.gitignore"
set_manifest_version "$fixture"

(
  cd "$fixture"
  git init -q
  git -c user.email=t@t -c user.name=Test add .
  git -c user.email=t@t -c user.name=Test commit -q -m "fixture@1.0.0"
)

AGENT_SYNC_NOW=2026-05-14T00:00:00Z \
  "$root/scripts/agent-sync.sh" --target "$fixture" --to 1.1.0 --apply

for path in \
  scripts/agent-lock.sh \
  scripts/lib/agent_lock.py \
  scripts/lib/gate_runner.py \
  scripts/lib/secret_scan_redacted.py \
  scripts/lib/agent_system_validation/monitored_paths.py
do
  if [ ! -f "$fixture/$path" ]; then
    printf 'FAIL: migration did not create %s\n' "$path" >&2
    exit 1
  fi
done
printf 'PASS: 1.1.0 migration created new runtime files\n'

if ! grep -qF '.agent/locks/' "$fixture/.gitignore"; then
  printf 'FAIL: .gitignore missing .agent/locks/\n' >&2
  exit 1
fi
printf 'PASS: 1.1.0 migration patches .gitignore\n'

if [ -e "$fixture/.agent/gate-modes.json" ]; then
  printf 'FAIL: migration must not create .agent/gate-modes.json\n' >&2
  exit 1
fi
printf 'PASS: 1.1.0 migration does not create .agent/gate-modes.json\n'

python3 - "$fixture/.agent/manifest.json" <<'PY'
import json
import sys
from pathlib import Path

data = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
if data.get("synced_to_template_version") != "1.1.0":
    raise SystemExit("FAIL: manifest not bumped to 1.1.0")
tracked = data.get("tracked_files")
if not isinstance(tracked, dict) or "scripts/lib/secret_scan_redacted.py" not in tracked:
    raise SystemExit("FAIL: tracked_files missing secret scanner entry")
print("PASS: manifest bumped and tracked_files refreshed")
PY

(
  cd "$fixture"
  git -c user.email=t@t -c user.name=Test add .
  git -c user.email=t@t -c user.name=Test commit -q -m "fixture@1.1.0"
)

AGENT_SYNC_NOW=2026-05-14T00:01:00Z \
  "$root/scripts/agent-sync.sh" --target "$fixture" --to 1.1.0 --apply

if [ -n "$(git -C "$fixture" status --short)" ]; then
  git -C "$fixture" status --short >&2
  printf 'FAIL: 1.1.0 migration re-apply produced changes\n' >&2
  exit 1
fi
printf 'PASS: 1.1.0 migration re-apply is a no-op\n'
