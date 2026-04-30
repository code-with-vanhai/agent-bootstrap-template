from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional

from .models import Finding, SEVERITY_HIGH, SEVERITY_MEDIUM
from .repo_context import detect_repo_context
from .validator import (
    _MIN_TEMPLATE_VERSION,
    _semver_tuple,
    collect_plan_files,
    detect_target_template_version,
    filter_for_exit,
    validate_plan,
)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate .agent/runs/<slug>/plan.md and spec.md artifacts."
    )
    parser.add_argument("target", help="Plan file or .agent/runs/<slug>/ directory")
    parser.add_argument("--strict", action="store_true", help="Treat Medium findings as failures")
    parser.add_argument("--repo-root", help="Override repo root for context detection")
    parser.add_argument("--format", choices=("human", "github", "json"), default="human")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Validate even if the target repo has not yet synced to template >= 0.4.0",
    )
    args = parser.parse_args(argv)

    target = Path(args.target).resolve()
    repo_root = Path(args.repo_root).resolve() if args.repo_root else _detect_repo_root(target)

    if not args.force:
        synced_version = detect_target_template_version(repo_root)
        if synced_version is not None and _semver_tuple(synced_version) < _MIN_TEMPLATE_VERSION:
            min_str = ".".join(str(p) for p in _MIN_TEMPLATE_VERSION)
            print(
                f"SKIP: target repo template version {synced_version} < {min_str}; "
                f"skipping plan validation. Pass --force to override.",
                file=sys.stderr,
            )
            return 0

    plan_files = collect_plan_files(target)
    if not plan_files:
        print(f"No plan.md or spec.md found at {target}", file=sys.stderr)
        return 2

    repo_ctx = detect_repo_context(repo_root)

    all_findings: List[Finding] = []
    for plan in plan_files:
        all_findings.extend(validate_plan(plan, repo_ctx, args.strict))

    # Render output.
    high_count = sum(1 for f in all_findings if f.severity == SEVERITY_HIGH)
    medium_count = sum(1 for f in all_findings if f.severity == SEVERITY_MEDIUM)
    failing = filter_for_exit(all_findings, args.strict)

    if args.format == "github":
        for f in all_findings:
            print(f.format_for_github())
    elif args.format == "json":
        payload = {
            "format": "json",
            "strict": args.strict,
            "target": str(target),
            "repo_root": str(repo_root),
            "high_count": high_count,
            "medium_count": medium_count,
            "failure_count": len(failing),
            "detected_signals": list(repo_ctx.detected_signals),
            "react_version": repo_ctx.react_version,
            "files": [
                {
                    "path": str(plan.path),
                    "findings": [f.to_dict() for f in all_findings if f.file == plan.path],
                }
                for plan in plan_files
            ],
            "findings": [f.to_dict() for f in all_findings],
        }
        try:
            print(json.dumps(payload, indent=2, sort_keys=True))
        except (TypeError, ValueError) as exc:
            print(f"ERROR: failed to serialize JSON output: {exc}", file=sys.stderr)
            return 2
    else:
        for plan in plan_files:
            plan_findings = [f for f in all_findings if f.file == plan.path]
            print(f"{plan.path}:")
            if not plan_findings:
                print("  (no findings)")
                continue
            for f in plan_findings:
                print(f.format_for_human())
        print()
        print(f"Summary: {high_count} High, {medium_count} Medium "
              f"(strict={args.strict}, repo_root={repo_root})")
        if repo_ctx.detected_signals:
            print(f"Repo signals: {'; '.join(repo_ctx.detected_signals)}")
        if repo_ctx.react_version:
            print(f"React version: {repo_ctx.react_version}")

    return 1 if failing else 0


def _detect_repo_root(start: Path) -> Path:
    cur = start if start.is_dir() else start.parent
    cur = cur.resolve()
    while cur != cur.parent:
        if (cur / ".git").exists() or (cur / "package.json").exists() or (cur / ".agent").is_dir():
            return cur
        cur = cur.parent
    return start.parent.resolve()
