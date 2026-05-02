#!/usr/bin/env bash
# Migration regression test for 0.8.0 -> 0.8.1.

set -euo pipefail

root="$(git rev-parse --show-toplevel)"
work_root="$(mktemp -d /tmp/migration-0.8.1.XXXXXX)"

ephemeral_v081_created="0"

cleanup() {
  if [ "$ephemeral_v081_created" = "1" ]; then
    git -C "$root" tag -d v0.8.1 >/dev/null 2>&1 || true
  fi
  rm -rf "$work_root"
}
trap cleanup EXIT

assert_file_contains() {
  path="$1"
  needle="$2"
  desc="$3"
  if grep -qF -- "$needle" "$path"; then
    printf 'PASS: %s\n' "$desc"
  else
    printf 'FAIL: %s\n  file=%s\n  needle=%s\n' "$desc" "$path" "$needle" >&2
    exit 1
  fi
}

ensure_previous_release_tag() {
  if git -C "$root" rev-parse --verify --quiet "v0.8.0^{commit}" >/dev/null; then
    return 0
  fi
  printf 'SKIP: v0.8.0 tag is missing; cannot build the 0.8.0 regression fixture.\n'
  exit 0
}

ensure_current_release_tag() {
  if git -C "$root" rev-parse --verify --quiet "v0.8.1^{commit}" >/dev/null; then
    return 0
  fi
  if ! git -C "$root" diff --quiet -- \
    core/migrations/0.8.1 \
    scripts/lib/validate_agent_system.py; then
    printf 'SKIP: v0.8.1 tag is missing and 0.8.1 migration sources are not committed yet.\n'
    exit 0
  fi
  git -C "$root" tag v0.8.1
  ephemeral_v081_created="1"
}

complete_bootstrap_fixture() {
  fixture_dir="$1"
  python3 - "$fixture_dir" <<'PY'
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
marker = "not confirmed - complete .agent/bootstrap-pending.md"
for rel in [".agent", "AGENTS.md", ".cursor", ".github"]:
    path = root / rel
    if path.is_file():
        files = [path]
    elif path.is_dir():
        files = [item for item in path.rglob("*") if item.is_file()]
    else:
        continue
    for item in files:
        text = item.read_text(encoding="utf-8", errors="replace")
        if marker in text:
            item.write_text(text.replace(marker, "confirmed by migration fixture"), encoding="utf-8")
pending = root / ".agent" / "bootstrap-pending.md"
if pending.exists():
    pending.unlink()
PY
}

set_manifest_version() {
  fixture_dir="$1"
  version="$2"
  commit="$3"
  python3 - "$fixture_dir/.agent/manifest.json" "$version" "$commit" <<'PY'
import json
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
version = sys.argv[2]
commit = sys.argv[3]
data = json.loads(path.read_text(encoding="utf-8"))
data["template_version"] = version
data["synced_to_template_version"] = version
data["synced_to_template_commit"] = commit
path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
PY
}

remove_pycache() {
  dir="$1"
  find "$dir" -type d -name __pycache__ -prune -exec rm -rf {} +
}

setup_080_fixture() {
  fixture_dir="$work_root/clean-from-0.8.0"
  mkdir -p "$fixture_dir"
  "$root/scripts/bootstrap-request.sh" --target "$fixture_dir" >/dev/null
  complete_bootstrap_fixture "$fixture_dir"
  git -C "$root" show v0.8.0:scripts/lib/validate_agent_system.py \
    >"$fixture_dir/scripts/lib/validate_agent_system.py"
  python3 -m py_compile "$fixture_dir/scripts/lib/validate_agent_system.py"
  remove_pycache "$fixture_dir"
  set_manifest_version "$fixture_dir" "0.8.0" "$(git -C "$root" rev-parse v0.8.0)"

  (
    cd "$fixture_dir"
    git init -q
    git -c user.email=t@t -c user.name=Test add .
    git -c user.email=t@t -c user.name=Test commit -q -m "fixture@0.8.0"
  ) >&2

  if AGENT_ROOT="$fixture_dir" bash "$fixture_dir/scripts/agent-validate.sh" >/tmp/migration-0.8.1-pre.out 2>&1; then
    printf 'FAIL: [setup] 0.8.0 fixture unexpectedly passed old validator\n' >&2
    exit 1
  fi
  assert_file_contains "/tmp/migration-0.8.1-pre.out" "bootstrap completion markers remain" \
    "[setup] old validator false positive reproduced" >&2
  remove_pycache "$fixture_dir"

  printf '%s\n' "$fixture_dir"
}

ensure_previous_release_tag
ensure_current_release_tag
fixture="$(setup_080_fixture)"

AGENT_SYNC_NOW=2026-04-28T05:00:00Z \
  "$root/scripts/agent-sync.sh" --target "$fixture" --to 0.8.1 --apply

assert_file_contains "$fixture/.agent/manifest.json" '"template_version": "0.8.1"' \
  "[clean-from-0.8.0] manifest template_version=0.8.1"
assert_file_contains "$fixture/.agent/manifest.json" '"synced_to_template_version": "0.8.1"' \
  "[clean-from-0.8.0] manifest synced_to=0.8.1"
assert_file_contains "$fixture/.agent/sync-log.md" "Sync to 0.8.1" \
  "[clean-from-0.8.0] sync log appended"
assert_file_contains "$fixture/scripts/lib/validate_agent_system.py" "GENERATED_TEXT_ROOTS" \
  "[clean-from-0.8.0] validator text roots installed"
assert_file_contains "$fixture/scripts/lib/validate_agent_system.py" "GENERATED_SCAN_EXCLUDED_SUFFIXES" \
  "[clean-from-0.8.0] validator cache-file filter installed"

AGENT_ROOT="$fixture" bash "$fixture/scripts/agent-validate.sh" >/tmp/migration-0.8.1-validate.out
assert_file_contains "/tmp/migration-0.8.1-validate.out" "All validation checks passed." \
  "[clean-from-0.8.0] generated validator passes"

remove_pycache "$fixture"
(
  cd "$fixture"
  git -c user.email=t@t -c user.name=Test add .
  git -c user.email=t@t -c user.name=Test commit -q -m "first 0.8.1 apply"
)

AGENT_SYNC_NOW=2026-04-28T05:00:00Z \
  "$root/scripts/agent-sync.sh" --target "$fixture" --to 0.8.1 --apply

remove_pycache "$fixture"
if [ -n "$(git -C "$fixture" status --short)" ]; then
  git -C "$fixture" status --short
  printf 'FAIL: [clean-from-0.8.0] re-apply produced changes\n' >&2
  exit 1
fi
printf 'PASS: [clean-from-0.8.0] idempotent re-apply\n'

printf '\nAll 0.8.1 migration assertions passed.\n'
