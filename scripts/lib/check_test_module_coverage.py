#!/usr/bin/env python3
"""Verify CI gates every scripts/lib/test_*.py module.

Drift check that fails loudly when a new test module is added under
scripts/lib/ but the CI workflow does not invoke it via `python3 -m unittest
scripts.lib.<module>`. Stdlib only; no YAML dependency.

Usage:
    python3 scripts/lib/check_test_module_coverage.py .github/workflows/ci.yml
"""

from __future__ import annotations

import pathlib
import re
import sys


def discover_test_modules(lib_dir: pathlib.Path) -> set[str]:
    """Return scripts.lib.test_* module names present on disk."""
    modules: set[str] = set()
    for path in sorted(lib_dir.glob("test_*.py")):
        if path.name == "__init__.py":
            continue
        modules.add(f"scripts.lib.{path.stem}")
    return modules


def parse_ci_invocations(ci_text: str) -> set[str]:
    """Return modules referenced by `python3 -m unittest <module> ...` in CI.

    Supports both one-module-per-line invocations and multiple modules on a
    single line. Matches `python3 -m unittest <args>` and collects every
    whitespace-separated dotted-path argument that looks like a module
    (`scripts.lib.test_*`). Other unittest flags (e.g. `-v`, `discover`) are
    ignored.
    """
    modules: set[str] = set()
    pattern = re.compile(r"python3?\s+-m\s+unittest\b([^\n]*)")
    for match in pattern.finditer(ci_text):
        tail = match.group(1)
        for token in tail.split():
            if token.startswith("-"):
                continue
            if token == "discover":
                continue
            if token.startswith("scripts.lib.test_"):
                modules.add(token)
    return modules


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(
            "usage: check_test_module_coverage.py <ci-workflow-yaml>",
            file=sys.stderr,
        )
        return 2

    ci_path = pathlib.Path(argv[1])
    if not ci_path.is_file():
        print(f"FAIL: CI workflow not found: {ci_path}", file=sys.stderr)
        return 2

    repo_root = pathlib.Path(__file__).resolve().parents[2]
    lib_dir = repo_root / "scripts" / "lib"
    if not lib_dir.is_dir():
        print(f"FAIL: scripts/lib not found at {lib_dir}", file=sys.stderr)
        return 2

    on_disk = discover_test_modules(lib_dir)
    in_ci = parse_ci_invocations(ci_path.read_text(encoding="utf-8"))

    missing = sorted(on_disk - in_ci)
    extra = sorted(in_ci - on_disk)

    if missing:
        print(
            "FAIL: CI does not invoke these test modules:\n  "
            + "\n  ".join(missing),
            file=sys.stderr,
        )
        print(
            "Add `python3 -m unittest <module>` for each missing module to "
            f"{ci_path}.",
            file=sys.stderr,
        )
        return 1

    if extra:
        print(
            "FAIL: CI references test modules that do not exist on disk:\n  "
            + "\n  ".join(extra),
            file=sys.stderr,
        )
        return 1

    print(f"PASS: {len(on_disk)} scripts.lib.test_* module(s) gated by CI.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
