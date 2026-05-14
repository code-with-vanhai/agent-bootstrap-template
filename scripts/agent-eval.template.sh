#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$ROOT"

gate="${1:-fast}"

if [ "$#" -gt 1 ]; then
  printf 'Usage: %s [changed|fast|frontend|backend|shared|e2e|full|security|release]\n' "$0" >&2
  printf 'Received unsupported extra arguments: %s\n' "$*" >&2
  exit 1
fi

_audit_epoch_ms() {
  now_ms="$(date -u +%s%3N 2>/dev/null || true)"
  case "$now_ms" in
    ""|*[!0-9]*) printf '%s000' "$(date -u +%s)" ;;
    *) printf '%s' "$now_ms" ;;
  esac
}

audit_start_epoch_ms="$(_audit_epoch_ms)"

_audit_emit_gate_exit() {
  exit_code=$?
  if [ "${AGENT_EVAL_SUPPRESS_AUDIT:-0}" = "1" ]; then
    return 0
  fi
  audit_end_epoch_ms="$(_audit_epoch_ms)"
  duration_ms=$((audit_end_epoch_ms - audit_start_epoch_ms))
  if [ "$duration_ms" -lt 0 ]; then
    duration_ms=0
  fi
  if [ -x "$ROOT/scripts/agent-audit-log.sh" ]; then
    "$ROOT/scripts/agent-audit-log.sh" \
      --kind gate_run \
      --actor scripts/agent-eval.sh \
      --field "gate=$gate" \
      --field "exit_code=$exit_code" \
      --field "duration_ms=$duration_ms" || true
  fi
}

trap '_audit_emit_gate_exit' EXIT

gate_modes_path=""
if [ -f "$ROOT/.agent/gate-modes.json" ]; then
  gate_modes_path="$ROOT/.agent/gate-modes.json"
elif [ -f "$ROOT/core/gate-modes.json" ]; then
  gate_modes_path="$ROOT/core/gate-modes.json"
fi

if [ -n "$gate_modes_path" ] && [ -f "$ROOT/scripts/lib/gate_runner.py" ] && command -v python3 >/dev/null 2>&1; then
  composite_check="$(python3 "$ROOT/scripts/lib/gate_runner.py" is-composite --gate "$gate" --gate-modes "$gate_modes_path" 2>/dev/null || true)"
  if [ "$composite_check" = "yes" ]; then
    exec python3 "$ROOT/scripts/lib/gate_runner.py" run \
      --gate "$gate" \
      --gate-modes "$gate_modes_path" \
      --eval-script "$0" \
      --root "$ROOT"
  fi
fi

run() {
  printf '\n>>> %s\n' "$*"
  "$@"
}

not_configured() {
  printf 'Gate "%s" is not configured for this repository yet.\n' "$gate" >&2
  printf 'Update scripts/agent-eval.sh and .agent/gates.md after scanning the repo.\n' >&2
  exit 2
}

case "$gate" in
  changed)
    # Replace with repo-specific changed-file checks.
    # Examples:
    # run npm run lint -- --cache
    # run go test ./...
    # >>> AGENT-CANDIDATES gate=changed — review before promoting <<<
    # <<< END AGENT-CANDIDATES gate=changed <<<
    not_configured
    ;;
  fast)
    # Replace with fast repo-wide checks.
    # Examples:
    # run npm run typecheck
    # run npm test
    # run npm run lint
    # >>> AGENT-CANDIDATES gate=fast — review before promoting <<<
    # <<< END AGENT-CANDIDATES gate=fast <<<
    not_configured
    ;;
  frontend)
    # Replace with frontend-specific checks.
    # >>> AGENT-CANDIDATES gate=frontend — review before promoting <<<
    # <<< END AGENT-CANDIDATES gate=frontend <<<
    not_configured
    ;;
  backend)
    # Replace with backend-specific checks.
    # >>> AGENT-CANDIDATES gate=backend — review before promoting <<<
    # <<< END AGENT-CANDIDATES gate=backend <<<
    not_configured
    ;;
  shared)
    # Replace with shared contract/library checks.
    # >>> AGENT-CANDIDATES gate=shared — review before promoting <<<
    # <<< END AGENT-CANDIDATES gate=shared <<<
    not_configured
    ;;
  e2e)
    # Replace with end-to-end checks.
    # >>> AGENT-CANDIDATES gate=e2e — review before promoting <<<
    # <<< END AGENT-CANDIDATES gate=e2e <<<
    not_configured
    ;;
  full)
    # Replace with full verification.
    # >>> AGENT-CANDIDATES gate=full — review before promoting <<<
    # <<< END AGENT-CANDIDATES gate=full <<<
    not_configured
    ;;
  security)
    # Replace with repo-specific security-sensitive checks after scanning.
    # Examples:
    # run npm audit --audit-level high
    # run semgrep --config auto
    # run scripts/check-authz.sh
    # >>> AGENT-CANDIDATES gate=security — review before promoting <<<
    # <<< END AGENT-CANDIDATES gate=security <<<
    if command -v gitleaks >/dev/null 2>&1; then
      if gitleaks dir --help >/dev/null 2>&1; then
        run gitleaks dir --redact .
      else
        run gitleaks detect --redact --source .
      fi
    elif command -v python3 >/dev/null 2>&1 && [ -f "$ROOT/scripts/lib/secret_scan_redacted.py" ]; then
      run python3 "$ROOT/scripts/lib/secret_scan_redacted.py" --root .
    else
      printf 'No secret scanner command found. Install/configure gitleaks or python3 with scripts/lib/secret_scan_redacted.py, or keep the security gate not configured.\n' >&2
      not_configured
    fi
    ;;
  release)
    # Replace with release candidate checks.
    # This must not deploy unless explicitly approved.
    # >>> AGENT-CANDIDATES gate=release — review before promoting <<<
    # <<< END AGENT-CANDIDATES gate=release <<<
    not_configured
    ;;
  *)
    printf 'Unknown gate: %s\n' "$gate" >&2
    printf 'Available gates: changed, fast, frontend, backend, shared, e2e, full, security, release\n' >&2
    exit 1
    ;;
esac
