#!/usr/bin/env bash
# Mock Codex CLI that emits an authentication-required error matching the
# conservative codex regex in scripts/lib/llm_provider.sh.
#
# Used by PR-2 AC-9 (mocks are checked in and stable).
#
# This mock ignores its arguments and stdin.
set -euo pipefail
printf "authentication error: invalid api key, please log in.\n"
exit 0
