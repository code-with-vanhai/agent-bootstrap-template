"""Command-line entrypoint for the agent-system validator."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .core import AgentSystemValidator
from .output import render_github, render_human, render_json
from .runtime import detect_mode, resolve_root


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate Agent Bootstrap template-source or generated-repo structure."
    )
    parser.add_argument(
        "--mode", choices=("template", "generated", "auto"), default="auto"
    )
    parser.add_argument(
        "--format", choices=("human", "github", "json"), default="human"
    )
    args = parser.parse_args(argv)

    root, root_source = resolve_root(Path.cwd())
    mode = detect_mode(root, args.mode)
    if args.format == "human":
        print(f"Resolving root: {root} (source: {root_source})", file=sys.stderr)

    validator = AgentSystemValidator(root, mode)
    results = validator.run()

    if args.format == "github":
        return render_github(results)
    if args.format == "json":
        return render_json(results, root, mode, root_source)
    return render_human(results, mode)
