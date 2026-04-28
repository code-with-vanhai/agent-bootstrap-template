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
    not_configured
    ;;
  fast)
    # Replace with fast repo-wide checks.
    # Examples:
    # run npm run typecheck
    # run npm test
    # run npm run lint
    not_configured
    ;;
  frontend)
    # Replace with frontend-specific checks.
    not_configured
    ;;
  backend)
    # Replace with backend-specific checks.
    not_configured
    ;;
  shared)
    # Replace with shared contract/library checks.
    not_configured
    ;;
  e2e)
    # Replace with end-to-end checks.
    not_configured
    ;;
  full)
    # Replace with full verification.
    not_configured
    ;;
  security)
    # Replace with repo-specific security-sensitive checks after scanning.
    # Examples:
    # run npm audit --audit-level high
    # run semgrep --config auto
    # run scripts/check-authz.sh
    if command -v gitleaks >/dev/null 2>&1; then
      if gitleaks dir --help >/dev/null 2>&1; then
        run gitleaks dir .
      else
        run gitleaks detect --source .
      fi
    else
      printf 'No secret scanner command found. Install/configure gitleaks or keep the security gate not configured.\n' >&2
      not_configured
    fi
    ;;
  release)
    # Replace with release candidate checks.
    # This must not deploy unless explicitly approved.
    not_configured
    ;;
  *)
    printf 'Unknown gate: %s\n' "$gate" >&2
    printf 'Available gates: changed, fast, frontend, backend, shared, e2e, full, security, release\n' >&2
    exit 1
    ;;
esac
