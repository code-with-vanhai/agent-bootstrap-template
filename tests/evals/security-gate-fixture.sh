#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$ROOT"

target_dir="$(mktemp -d "/tmp/security-gate-fixture.XXXXXX")"
mock_bin="$(mktemp -d "/tmp/security-gate-bin.XXXXXX")"
no_tools_bin="$(mktemp -d "/tmp/security-gate-no-tools.XXXXXX")"
cleanup() {
  rm -rf "$target_dir" "$mock_bin" "$no_tools_bin"
}
trap cleanup EXIT

"$ROOT/scripts/bootstrap-request.sh" \
  --harness generic \
  --features standard \
  --target "$target_dir" \
  >/dev/null 2>&1

cat >"$mock_bin/gitleaks" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
if [ "$1" = "dir" ] && [ "${2:-}" = "--help" ]; then
  exit 0
fi
if [ "$1" = "dir" ] && [ "${2:-}" = "--redact" ] && [ "${3:-}" = "." ]; then
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

fake_prefix="AKIA"
fake_suffix="IOSFODNN7EXAMPLE"
fixture_token="${fake_prefix}${fake_suffix}"
printf 'API_KEY = "%s"\n' "$fixture_token" >"$target_dir/leaked-secret.py"

set +e
(
  cd "$target_dir"
  PATH="/usr/bin:/bin" bash scripts/agent-eval.sh security
) >/tmp/security-gate-python.out 2>&1
python_rc=$?
set -e
if [ "$python_rc" -ne 1 ]; then
  printf 'FAIL: python fallback should return 1 on findings, got %s\n' "$python_rc" >&2
  cat /tmp/security-gate-python.out >&2
  exit 1
fi
if ! grep -qF 'FINDING: leaked-secret.py:1 [AWS_ACCESS_KEY_ID]' /tmp/security-gate-python.out; then
  printf 'FAIL: python fallback did not emit redacted AWS finding\n' >&2
  cat /tmp/security-gate-python.out >&2
  exit 1
fi
if grep -qF "$fixture_token" /tmp/security-gate-python.out; then
  printf 'FAIL: python fallback leaked the matched secret value\n' >&2
  cat /tmp/security-gate-python.out >&2
  exit 1
fi
rm -f "$target_dir/leaked-secret.py"

ln -s /usr/bin/date "$no_tools_bin/date"
ln -s /usr/bin/dirname "$no_tools_bin/dirname"
set +e
(
  cd "$target_dir"
  PATH="$no_tools_bin" /usr/bin/bash scripts/agent-eval.sh security
) >/tmp/security-gate-missing.out 2>&1
missing_rc=$?
set -e
if [ "$missing_rc" -ne 2 ]; then
  printf 'FAIL: missing gitleaks and python3 should leave security gate not configured with exit 2, got %s\n' "$missing_rc" >&2
  cat /tmp/security-gate-missing.out >&2
  exit 1
fi

printf 'PASS: security gate runs redacted gitleaks, falls back to redacted python scanning, and reports not configured when no scanner is available.\n'
