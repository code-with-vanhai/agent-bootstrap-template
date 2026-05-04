"""Output renderers for the agent-system validator.

Three formats:
  - ``human``: human-readable PASS/FAIL/SKIP lines with a summary tail
    (matches the wording the existing tests assert).
  - ``github``: ``::error`` annotations consumable by GitHub Actions.
  - ``json``: machine-readable payload for downstream tooling and the
    test-suite parsers.
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path

from .core import Check


def render_human(results: list[Check], mode: str) -> int:
    failures = [item for item in results if item.status == "FAIL"]
    for item in results:
        line = f"{item.status}: {item.message}"
        print(line, file=sys.stderr if item.status == "FAIL" else sys.stdout)
    if failures:
        noun = (
            "template skill validation check(s)"
            if mode == "template"
            else "validation check(s)"
        )
        print(f"\n{len(failures)} {noun} failed.", file=sys.stderr)
        return 1
    if mode == "template":
        print("\nAll template skill validation checks passed.")
    else:
        print("\nAll validation checks passed.")
    return 0


def render_github(results: list[Check]) -> int:
    failures = [item for item in results if item.status == "FAIL"]
    for item in failures:
        attrs = f" file={item.path}" if item.path else ""
        print(f"::error{attrs}::{item.message}")
    return 1 if failures else 0


def render_json(
    results: list[Check], root: Path, mode: str, root_source: str
) -> int:
    failures = [item for item in results if item.status == "FAIL"]
    payload = {
        "root": str(root),
        "root_source": root_source,
        "mode": mode,
        "failure_count": len(failures),
        "results": [asdict(item) for item in results],
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 1 if failures else 0
