"""Post-apply validation runner.

Runs ``scripts/agent-validate.sh`` and ``bash -n scripts/agent-eval.sh``
against the freshly migrated target. Returns a list of ``"name: passed"``
strings for the sync-log entry. Raises ``SystemExit(EXIT_VALIDATION)`` —
not a :class:`SyncError` subclass — so the orchestrator can wrap the
failure with an explicit "to revert: git restore ./ git clean -fd" hint
before re-raising.
"""

from __future__ import annotations

import os
import subprocess
import sys

from .errors import EXIT_VALIDATION


def run_validation(target, verify_fast):
    validation = []
    validator = target / "scripts" / "agent-validate.sh"
    if validator.is_file():
        result = subprocess.run(
            ["bash", str(validator)],
            cwd=str(target),
            env={**os.environ, "AGENT_ROOT": str(target)},
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if result.returncode != 0:
            print(result.stdout, end="")
            print(result.stderr, end="", file=sys.stderr)
            raise SystemExit(EXIT_VALIDATION)
        validation.append("agent-validate: passed")

    agent_eval = target / "scripts" / "agent-eval.sh"
    if agent_eval.is_file():
        result = subprocess.run(
            ["bash", "-n", str(agent_eval)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if result.returncode != 0:
            print(result.stderr, end="", file=sys.stderr)
            raise SystemExit(EXIT_VALIDATION)
        validation.append("bash -n agent-eval.sh: passed")

    if verify_fast:
        result = subprocess.run(
            ["bash", str(agent_eval), "fast"], cwd=str(target), text=True
        )
        if result.returncode != 0:
            raise SystemExit(EXIT_VALIDATION)
        validation.append("agent-eval fast: passed")
    return validation
