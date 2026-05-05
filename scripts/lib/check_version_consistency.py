#!/usr/bin/env python3
"""Verify all release-version sources agree.

Compares the template version recorded in:

- ``scripts/bootstrap-request.sh`` (``template_version="..."``)
- ``.claude-plugin/plugin.json`` (``version``)
- ``.claude-plugin/marketplace.json`` (``metadata.version`` and the
  ``agent-bootstrap`` plugin entry's ``version``)
- ``CHANGELOG.md`` (the topmost ``## <version> - YYYY-MM-DD`` heading)

A skew in any one source is a release-integrity bug. Historical migration
JSON files intentionally retain older versions and are NOT checked here.

Usage:
    python3 scripts/lib/check_version_consistency.py
    python3 scripts/lib/check_version_consistency.py --root .
    python3 scripts/lib/check_version_consistency.py --strict
    python3 scripts/lib/check_version_consistency.py --bump 0.12.0
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
from typing import Iterable

_REPO_LIB = pathlib.Path(__file__).resolve().parent
if str(_REPO_LIB) not in sys.path:
    sys.path.insert(0, str(_REPO_LIB))
from release_tags_io import (  # noqa: E402
    latest_release_tag_row,
    parse_release_tag_rows,
    row_commit_is_pending,
)

SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")


def _read_text(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8")


def extract_bootstrap_version(root: pathlib.Path) -> str | None:
    path = root / "scripts" / "bootstrap-request.sh"
    if not path.is_file():
        return None
    match = re.search(
        r'^template_version\s*=\s*"([^"]+)"', _read_text(path), re.MULTILINE
    )
    return match.group(1) if match else None


def extract_plugin_version(root: pathlib.Path) -> str | None:
    path = root / ".claude-plugin" / "plugin.json"
    if not path.is_file():
        return None
    data = json.loads(_read_text(path))
    if isinstance(data, dict) and isinstance(data.get("version"), str):
        return data["version"]
    return None


def extract_marketplace_versions(
    root: pathlib.Path,
) -> tuple[str | None, str | None]:
    """Return (metadata.version, agent-bootstrap plugin.version)."""

    path = root / ".claude-plugin" / "marketplace.json"
    if not path.is_file():
        return None, None
    data = json.loads(_read_text(path))
    metadata_version = None
    plugin_version = None
    if isinstance(data, dict):
        metadata = data.get("metadata", {})
        if isinstance(metadata, dict):
            value = metadata.get("version")
            if isinstance(value, str):
                metadata_version = value
        for entry in data.get("plugins", []):
            if isinstance(entry, dict) and entry.get("name") == "agent-bootstrap":
                value = entry.get("version")
                if isinstance(value, str):
                    plugin_version = value
                break
    return metadata_version, plugin_version


def extract_changelog_version(root: pathlib.Path) -> str | None:
    path = root / "CHANGELOG.md"
    if not path.is_file():
        return None
    pattern = re.compile(
        r"^##\s+(?P<version>\S+)\s+-\s+\d{4}-\d{2}-\d{2}", re.MULTILINE
    )
    match = pattern.search(_read_text(path))
    return match.group("version") if match else None


def collect(root: pathlib.Path) -> list[tuple[str, str | None]]:
    market_meta, market_plugin = extract_marketplace_versions(root)
    return [
        ("scripts/bootstrap-request.sh::template_version", extract_bootstrap_version(root)),
        (".claude-plugin/plugin.json::version", extract_plugin_version(root)),
        (".claude-plugin/marketplace.json::metadata.version", market_meta),
        (".claude-plugin/marketplace.json::plugins[agent-bootstrap].version", market_plugin),
        ("CHANGELOG.md::latest-release-heading", extract_changelog_version(root)),
    ]


def strict_release_tags_pending(root: pathlib.Path) -> tuple[int, str]:
    """Fail when ``core/release-tags.md`` is out of sync with CHANGELOG.

    Two checks:

    1. The newest semver row must not carry a ``<PENDING>`` commit
       marker. Left in place it means someone bumped the version but
       forgot to backfill the annotated-tag SHA after
       ``git tag -a v<x>``.
    2. The CHANGELOG's topmost release heading must have a matching row
       in ``release-tags.md``. Without this, deleting a released row
       (or forgetting to add one during bump) silently passes strict —
       ``core/release-process.md:31`` requires ``release-tags.md`` to
       map *every* released version.
    """

    path = root / "core" / "release-tags.md"
    if not path.is_file():
        return 0, ""
    rows = parse_release_tag_rows(path.read_text(encoding="utf-8"))
    latest = latest_release_tag_row(rows)
    if latest is None:
        return 0, ""
    if row_commit_is_pending(latest):
        return (
            1,
            (
                f"FAIL: {path}: latest row ({latest.version}) commit is still "
                f"<PENDING>. Record the annotated-tag SHA after "
                f"`git tag -a v{latest.version}` "
                f"(core/release-process.md)."
            ),
        )
    changelog_ver = extract_changelog_version(root)
    if changelog_ver and SEMVER_RE.fullmatch(changelog_ver):
        known = {r.version for r in rows}
        if changelog_ver not in known:
            return (
                1,
                (
                    f"FAIL: {path}: CHANGELOG latest release {changelog_ver} "
                    f"has no matching row in release-tags.md. "
                    f"core/release-process.md requires every released tag to "
                    f"be mapped; run `scripts/bump-version.sh {changelog_ver}` "
                    f"or add the row manually before merging."
                ),
            )
    return 0, ""


def report(rows: Iterable[tuple[str, str | None]]) -> int:
    rows = list(rows)
    width = max(len(name) for name, _ in rows)
    print("Version sources:")
    for name, value in rows:
        print(f"  {name.ljust(width)}  {value!r}")
    # Flush stdout before any stderr writes so the report and FAIL lines stay
    # in order under `2>&1` redirection (Python buffers per-stream).
    sys.stdout.flush()

    missing = [name for name, value in rows if value is None]
    if missing:
        print("\nFAIL: missing version in:", file=sys.stderr)
        for name in missing:
            print(f"  - {name}", file=sys.stderr)
        return 1

    bad_semver = [
        (name, value) for name, value in rows if not SEMVER_RE.fullmatch(value or "")
    ]
    if bad_semver:
        print("\nFAIL: non-semver values:", file=sys.stderr)
        for name, value in bad_semver:
            print(f"  - {name}: {value!r}", file=sys.stderr)
        return 1

    distinct = {value for _, value in rows}
    if len(distinct) != 1:
        print("\nFAIL: version skew detected; sources disagree.", file=sys.stderr)
        return 1

    only = next(iter(distinct))
    print(f"\nPASS: all {len(rows)} sources agree on version {only}.")
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        default=str(pathlib.Path(__file__).resolve().parents[2]),
        help="Repository root (default: parent of scripts/lib)",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help=(
            "After the five-source check, fail if core/release-tags.md newest "
            "row still contains <PENDING> (Stage 2.1 release gate)."
        ),
    )
    parser.add_argument(
        "--bump",
        metavar="NEW_VERSION",
        default=None,
        help="Run bump_version.py for NEW_VERSION (same repo root).",
    )
    args = parser.parse_args(argv)
    root = pathlib.Path(args.root)
    if args.bump:
        import bump_version as bv  # noqa: WPS433

        return bv.main([args.bump, "--root", str(root)])

    code = report(collect(root))
    if code != 0:
        return code
    if args.strict:
        err, msg = strict_release_tags_pending(root)
        if err:
            print(msg, file=sys.stderr)
            return err
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
