#!/usr/bin/env bash
# Mock Codex CLI that emits a quota-exhausted error string matching the
# conservative codex regex in scripts/lib/llm_provider.sh.
#
# Used by PR-2 AC-2 (provider=codex routes correctly via SKIP) and AC-9
# (mocks are checked in and stable, no /tmp ad-hoc).
#
# This mock ignores its arguments and stdin.
set -euo pipefail
printf "Error: rate limit exceeded for organization (HTTP 429: too many requests).\n"
exit 0
