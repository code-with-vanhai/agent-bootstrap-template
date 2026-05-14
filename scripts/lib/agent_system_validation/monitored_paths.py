#!/usr/bin/env python3
"""Monitored path list for generated-repo incremental validation."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


MONITORED_PATHS_FOR_INCREMENTAL: tuple[str, ...] = (
    ".agent/",
    ".agent/README.md",
    ".agent/manifest.json",
    ".agent/project-profile.md",
    ".agent/rulebase.md",
    ".agent/ownership.md",
    ".agent/gates.md",
    ".agent/decisions.md",
    ".agent/lessons.md",
    ".agent/roles/planner.md",
    ".agent/roles/implementer.md",
    ".agent/roles/reviewer.md",
    ".agent/roles/gate-runner.md",
    ".agent/roles/prompts/planner-subagent.md",
    ".agent/roles/prompts/implementer-subagent.md",
    ".agent/roles/prompts/reviewer-subagent.md",
    ".agent/roles/prompts/gate-runner-subagent.md",
    ".agent/workflows/bootstrap-workflow.md",
    ".agent/workflows/feature-workflow.md",
    ".agent/workflows/bugfix-workflow.md",
    ".agent/workflows/refactor-workflow.md",
    ".agent/workflows/review-workflow.md",
    ".agent/workflows/security-review-workflow.md",
    ".agent/workflows/improvement-cycle-workflow.md",
    ".agent/workflows/rule-evolution-workflow.md",
    ".agent/workflows/release-check-workflow.md",
    "AGENTS.md",
    "CLAUDE.md",
    "GEMINI.md",
    ".cursor/rules/agent-system.mdc",
    ".github/copilot-instructions.md",
    ".github/PULL_REQUEST_TEMPLATE.md",
    "scripts/agent-audit-log.sh",
    "scripts/agent-eval.sh",
    "scripts/agent-gate-discover.sh",
    "scripts/agent-lock.sh",
    "scripts/agent-validate-plan.sh",
    "scripts/agent-validate.sh",
    "scripts/lib/agent_lock.py",
    "scripts/lib/audit_log.py",
    "scripts/lib/gate_discovery.py",
    "scripts/lib/gate_modes.py",
    "scripts/lib/gate_runner.py",
    "scripts/lib/insert_gate_candidates.py",
    "scripts/lib/secret_scan_redacted.py",
    "scripts/lib/validate_agent_system.py",
    "scripts/lib/validate_mcp_config.py",
    "scripts/lib/validate_plan.py",
    "scripts/lib/agent_system_validation/",
    "scripts/lib/agent_system_validation/__init__.py",
    "scripts/lib/agent_system_validation/cli.py",
    "scripts/lib/agent_system_validation/monitored_paths.py",
    "scripts/lib/plan_validation/",
    "scripts/lib/plan_validation/cli.py",
    "scripts/lib/plan_validation/validator.py",
)


def diff_quiet(root: Path, base: str) -> int:
    result = subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "diff",
            "--quiet",
            base,
            "--",
            *MONITORED_PATHS_FOR_INCREMENTAL,
        ]
    )
    return int(result.returncode)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command")

    diff_parser = subparsers.add_parser("diff-quiet")
    diff_parser.add_argument("--root", required=True)
    diff_parser.add_argument("--base", required=True)

    args = parser.parse_args(argv)
    if args.command == "diff-quiet":
        return diff_quiet(Path(args.root), args.base)
    parser.print_usage(sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
