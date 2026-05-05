"""Parse and rewrite ``core/release-tags.md`` tables (Stage 2.1).

Used by :mod:`bump_version` and strict checks in
:mod:`check_version_consistency`. Table rows are sorted by semver.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


def _semver_key(version: str) -> tuple[int, ...]:
    return tuple(
        int(p) if p.isdigit() else 0
        for p in version.split("-", 1)[0].split(".")
    )


@dataclass(frozen=True)
class ReleaseTagRow:
    version: str
    tag: str
    commit: str
    notes: str


def parse_release_tag_rows(text: str) -> list[ReleaseTagRow]:
    """Extract data rows from the release-tags markdown table."""

    rows: list[ReleaseTagRow] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        parts = [p.strip() for p in stripped.split("|")]
        if len(parts) < 6:
            continue
        ver = parts[1]
        if ver == "Version":
            continue
        if not re.match(r"^\d+\.\d+\.\d+", ver):
            continue
        tag_raw = parts[2].strip("`")
        commit_raw = parts[3].strip("`")
        notes = parts[4]
        rows.append(
            ReleaseTagRow(
                version=ver,
                tag=tag_raw,
                commit=commit_raw,
                notes=notes,
            )
        )
    return rows


def render_release_tags_table(rows: list[ReleaseTagRow]) -> str:
    sorted_rows = sorted(rows, key=lambda r: _semver_key(r.version))
    lines = [
        "| Version | Tag | Commit | Notes |",
        "|---------|-----|--------|-------|",
    ]
    for r in sorted_rows:
        lines.append(
            f"| {r.version} | `{r.tag}` | `{r.commit}` | {r.notes} |"
        )
    return "\n".join(lines) + "\n"


def insert_replace_row(
    rows: list[ReleaseTagRow],
    *,
    version: str,
    commit: str,
    notes: str,
) -> list[ReleaseTagRow]:
    """Insert or replace the row for ``version``, then return sorted copy."""

    tag = f"v{version}"
    by_ver = {r.version: r for r in rows}
    by_ver[version] = ReleaseTagRow(
        version=version, tag=tag, commit=commit, notes=notes
    )
    return sorted(by_ver.values(), key=lambda r: _semver_key(r.version))


def latest_release_tag_row(rows: list[ReleaseTagRow]) -> ReleaseTagRow | None:
    if not rows:
        return None
    return max(rows, key=lambda r: _semver_key(r.version))


def row_commit_is_pending(row: ReleaseTagRow) -> bool:
    return "<PENDING>" in row.commit.upper()


def inject_release_tags_table(text: str, new_table: str) -> str:
    """Replace first ``| Version |`` / ``|---|`` table block with ``new_table``."""

    lines = text.splitlines(keepends=True)
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("|") and "| Version |" in line:
            out.append(new_table)
            i += 1
            while i < len(lines) and lines[i].strip().startswith("|"):
                i += 1
            continue
        out.append(line)
        i += 1
    return "".join(out)
