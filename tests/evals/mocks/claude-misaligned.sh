#!/usr/bin/env bash
# Mock Claude CLI that emits a benign, well-formed positive response that
# does NOT match any of the 4 behavior evals' assertion regexes. Used to
# demonstrate the FAIL path (PR-2 AC verification + future regression).
#
# This mock ignores its arguments and stdin.
set -euo pipefail
printf "I have completed the task and all tests pass; ready to merge.\n"
exit 0
