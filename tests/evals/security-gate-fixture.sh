#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$ROOT"

target_dir="$(mktemp -d "/tmp/security-gate-fixture.XXXXXX")"
mock_bin="$(mktemp -d "/tmp/security-gate-bin.XXXXXX")"
cleanup() {
  rm -rf "$target_dir" "$mock_bin"
}
trap cleanup EXIT

"$ROOT/scripts/bootstrap-request.sh" \
  --harness generic \
  --features standard \
  --target "$target_dir" \
  >/dev/null 2>&1

set +e
PATH="/usr/bin:/bin" bash "$target_dir/scripts/agent-eval.sh" security >/tmp/security-gate-missing.out 2>&1
missing_rc=$?
set -e
if [ "$missing_rc" -ne 2 ]; then
  printf 'FAIL: missing gitleaks should leave security gate not configured with exit 2, got %s\n' "$missing_rc" >&2
  cat /tmp/security-gate-missing.out >&2
  exit 1
fi

cat >"$mock_bin/gitleaks" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
if [ "$1" = "dir" ] && [ "${2:-}" = "--help" ]; then
  exit 0
fi
if [ "$1" = "dir" ] && [ "${2:-}" = "." ]; then
  printf 'gitleaks-dir-ran\n' >"$GITLEAKS_MARKER"
  exit 0
fi
printf 'unexpected gitleaks args: %s\n' "$*" >&2
exit 64
EOF
chmod +x "$mock_bin/gitleaks"

marker="$target_dir/gitleaks-marker.txt"
GITLEAKS_MARKER="$marker" PATH="$mock_bin:$PATH" bash "$target_dir/scripts/agent-eval.sh" security >/tmp/security-gate-gitleaks.out 2>&1

if [ "$(cat "$marker")" != "gitleaks-dir-ran" ]; then
  printf 'FAIL: gitleaks dir mock was not invoked\n' >&2
  cat /tmp/security-gate-gitleaks.out >&2
  exit 1
fi

printf 'PASS: security gate reports not configured without gitleaks and runs gitleaks dir when available.\n'
