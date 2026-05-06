#!/usr/bin/env python3
"""Atomic template version bump (Stage 2.1).

Updates the five sources checked by :mod:`check_version_consistency` plus
``core/release-tags.md`` (new row with ``<PENDING>`` commit until the
human records the tag SHA per ``core/release-process.md``).

Usage:
    python3 scripts/lib/bump_version.py [--root DIR] [--date YYYY-MM-DD] NEW_VERSION

Exits non-zero if pre-flight consistency check fails or ``NEW_VERSION``
is not strictly greater than the current unified version (or use the same
version for a no-op when already bumped).
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import pathlib
import sys
import tempfile

REPO_LIB = pathlib.Path(__file__).resolve().parent
if str(REPO_LIB) not in sys.path:
    sys.path.insert(0, str(REPO_LIB))

import check_version_consistency as vercheck  # noqa: E402
from release_tags_io import (  # noqa: E402
    inject_release_tags_table,
    insert_replace_row,
    parse_release_tag_rows,
    render_release_tags_table,
)


class BumpError(Exception):
    pass


def _semver_tuple(version: str) -> tuple[int, ...]:
    return tuple(
        int(p) if p.isdigit() else 0
        for p in version.split("-", 1)[0].split(".")
    )


def _atomic_write(path: pathlib.Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(
        dir=str(path.parent), prefix=f".{path.name}.", text=False
    )
    try:
        os.write(fd, data)
        os.close(fd)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.close(fd)
        except OSError:
            pass
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _update_bootstrap(root: pathlib.Path, new_ver: str) -> bytes:
    path = root / "scripts" / "bootstrap-request.sh"
    text = path.read_text(encoding="utf-8")
    text2, n = re.subn(
        r'^(template_version\s*=\s*")[^"]+(")',
        rf"\g<1>{new_ver}\g<2>",
        text,
        count=1,
        flags=re.MULTILINE,
    )
    if n != 1:
        raise BumpError(f"{path}: expected exactly one template_version= line")
    return text2.encode("utf-8")


def _update_json_version(path: pathlib.Path, new_ver: str) -> bytes:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise BumpError(f"{path}: root must be object")
    data["version"] = new_ver
    return (json.dumps(data, indent=2) + "\n").encode("utf-8")


def _update_marketplace(path: pathlib.Path, new_ver: str) -> bytes:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise BumpError(f"{path}: root must be object")
    meta = data.get("metadata")
    if isinstance(meta, dict):
        meta["version"] = new_ver
    for entry in data.get("plugins", []):
        if isinstance(entry, dict) and entry.get("name") == "agent-bootstrap":
            entry["version"] = new_ver
            break
    return (json.dumps(data, indent=2) + "\n").encode("utf-8")


def _insert_changelog_heading(text: str, new_ver: str, date: str) -> str:
    """Insert or promote a release heading.

    If a ``## Unreleased`` heading exists, it is promoted in-place to
    ``## <new_ver> - <date>`` so any prose authors accumulated under
    Unreleased becomes the body of the new release. This matches the
    keepachangelog / semantic-release convention and avoids stranding
    hand-written prose under a stale Unreleased anchor.

    Otherwise, the legacy behavior applies: a fresh
    ``## <new_ver> - <date>\\n\\n- \\n\\n`` block is inserted above the
    first dated release heading. The empty bullet is the sentinel
    :func:`release_prepare.patch_changelog_with_draft` later replaces.
    """

    unreleased_pattern = re.compile(
        # Use ``[ \t]*`` (not ``\s*``) so the trailing newline of the
        # heading line is preserved; otherwise greedy ``\s*`` swallows
        # the blank line that separates the heading from the first
        # bullet, producing ``## X.Y.Z - <date>\n- ...`` instead of
        # ``## X.Y.Z - <date>\n\n- ...``.
        r"^##[ \t]+Unreleased[ \t]*$",
        re.MULTILINE | re.IGNORECASE,
    )
    m_unreleased = unreleased_pattern.search(text)
    if m_unreleased:
        replacement = f"## {new_ver} - {date}"
        return text[: m_unreleased.start()] + replacement + text[m_unreleased.end():]

    pattern = re.compile(
        r"^(##\s+\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?\s+-\s+\d{4}-\d{2}-\d{2})",
        re.MULTILINE,
    )
    m = pattern.search(text)
    if not m:
        raise BumpError("CHANGELOG.md: no dated release heading found")
    insert = f"## {new_ver} - {date}\n\n- \n\n"
    return text[: m.start()] + insert + text[m.start():]


def _update_release_tags(root: pathlib.Path, new_ver: str) -> bytes:
    path = root / "core" / "release-tags.md"
    if not path.is_file():
        raise BumpError(f"missing {path}")
    text = path.read_text(encoding="utf-8")
    rows = parse_release_tag_rows(text)
    notes = (
        f"Replace `<PENDING>` with the release commit after "
        f"`git tag -a v{new_ver}` (see core/release-process.md)."
    )
    new_rows = insert_replace_row(
        rows,
        version=new_ver,
        commit="<PENDING>",
        notes=notes,
    )
    table = render_release_tags_table(new_rows)
    updated = inject_release_tags_table(text, table)
    return updated.encode("utf-8")


def bump(root: pathlib.Path, new_version: str, date: str) -> bool:
    """Apply version bump. Returns False if already at ``new_version`` (no writes)."""

    if not vercheck.SEMVER_RE.fullmatch(new_version):
        raise BumpError(f"not a semver version: {new_version!r}")

    rows_pre = list(vercheck.collect(root))
    if vercheck.report(rows_pre) != 0:
        raise BumpError("pre-bump version consistency check failed; fix sources first")

    current = rows_pre[0][1]
    assert current is not None
    if current == new_version:
        return False

    if _semver_tuple(new_version) <= _semver_tuple(current):
        raise BumpError(
            f"new version {new_version} must be greater than current {current}"
        )

    snapshots: dict[pathlib.Path, bytes | None] = {}
    targets = [
        root / "scripts" / "bootstrap-request.sh",
        root / ".claude-plugin" / "plugin.json",
        root / ".claude-plugin" / "marketplace.json",
        root / "CHANGELOG.md",
        root / "core" / "release-tags.md",
    ]
    for p in targets:
        snapshots[p] = p.read_bytes() if p.is_file() else None

    try:
        planned: dict[pathlib.Path, bytes] = {
            root / "scripts" / "bootstrap-request.sh": _update_bootstrap(
                root, new_version
            ),
            root / ".claude-plugin" / "plugin.json": _update_json_version(
                root / ".claude-plugin" / "plugin.json", new_version
            ),
            root / ".claude-plugin" / "marketplace.json": _update_marketplace(
                root / ".claude-plugin" / "marketplace.json", new_version
            ),
            root / "CHANGELOG.md": _insert_changelog_heading(
                (root / "CHANGELOG.md").read_text(encoding="utf-8"),
                new_version,
                date,
            ).encode("utf-8"),
            root / "core" / "release-tags.md": _update_release_tags(root, new_version),
        }
        for path, body in planned.items():
            _atomic_write(path, body)

        rows_post = list(vercheck.collect(root))
        if vercheck.report(rows_post) != 0:
            raise BumpError("internal error: post-bump basic check failed")
    except BaseException:
        for path, prev in snapshots.items():
            if prev is None:
                if path.exists():
                    path.unlink()
            else:
                _atomic_write(path, prev)
        raise
    return True


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        default=str(pathlib.Path(__file__).resolve().parents[2]),
        help="Repository root",
    )
    parser.add_argument(
        "--date",
        default=None,
        help="Release date for CHANGELOG (default: today UTC)",
    )
    parser.add_argument("new_version", help="Semver without v prefix, e.g. 0.12.0")
    args = parser.parse_args(argv)
    root = pathlib.Path(args.root)
    date = args.date
    if date is None:
        date = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
    try:
        changed = bump(root, args.new_version, date)
    except BumpError as exc:
        print(f"bump_version: {exc}", file=sys.stderr)
        return 1
    if not changed:
        print(f"Already at {args.new_version}; no files changed.")
        return 0
    print(f"Bumped template version to {args.new_version} (CHANGELOG date {date}).")
    print(
        "Next: edit CHANGELOG bullets, run tests, tag the commit, replace "
        "<PENDING> in core/release-tags.md, then re-run:\n"
        f"  python3 scripts/lib/check_version_consistency.py --root {root} --strict"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
