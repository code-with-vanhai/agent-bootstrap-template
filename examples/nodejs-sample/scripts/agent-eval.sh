#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$ROOT"

gate="${1:-fast}"

run() {
  printf '\n>>> %s\n' "$*"
  "$@"
}

case "$gate" in
  changed|fast)
    run npm run typecheck
    run npm test
    run npm run lint
    ;;
  backend|full)
    run npm run typecheck
    run npm test
    run npm run lint
    run npm run build
    ;;
  frontend|e2e|release)
    printf 'Gate "%s" is not configured for this sample.\n' "$gate" >&2
    exit 2
    ;;
  *)
    printf 'Unknown gate: %s\n' "$gate" >&2
    exit 1
    ;;
esac

