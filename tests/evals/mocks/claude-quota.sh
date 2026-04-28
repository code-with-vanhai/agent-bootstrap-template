#!/usr/bin/env bash
# Mock Claude CLI that emits a known quota-exhausted error string.
#
# Used by:
#   - PR-1 AC-6: behavior evals SKIP cleanly when CLAUDE_BIN points here.
#   - PR-2 AC-3 / AC-17: cross-checked routing through the provider registry.
#
# This mock ignores its arguments and stdin and prints a single line that
# matches the Claude branch of llm_provider_is_unavailable.
set -euo pipefail
printf "You've hit your limit · resets 8pm (Asia/Bangkok)\n"
exit 0
