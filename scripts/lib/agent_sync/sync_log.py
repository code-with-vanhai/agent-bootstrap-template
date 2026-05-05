"""``.agent/sync-log.md`` entry formatters, appender, and reader.

The migration fixture suite greps the produced text for headings like
``"## ... Sync to X.Y.Z"`` and chain markers such as
``"Chain: 0.4.0 -> 0.5.0 -> ..."``, so the body of each helper here is
byte-stable and intentionally not generated through any templating
library.

D-12 (revision 7 of the migration UX plan) bumps the accepted-list
shape on the writer side from ``- <path>`` to
``- <path> [reason=<reason>, source=<source>]`` so tooling can
distinguish ``--accept-theirs`` overrides from
``known_conflicts`` baseline-hash auto-accepts. The reader-side helper
:func:`parse_accepted_lines` accepts both shapes so existing
append-only logs written by pre-0.12.0 runners remain parseable.
"""

from __future__ import annotations

import re
from collections import namedtuple


_ACCEPTED_LINE_RE = re.compile(
    r"^\s*-\s+(?P<path>\S.*?)\s*\[reason=(?P<reason>[^,\]]+)"
    r",\s*source=(?P<source>[^\]]+)\]\s*$"
)
_LEGACY_ACCEPTED_LINE_RE = re.compile(r"^\s*-\s+(?P<path>\S.*?)\s*$")


ParsedAccepted = namedtuple("ParsedAccepted", ["path", "reason", "source"])


def _format_accepted_line(record):
    """Render one accepted entry in the D-12 shape.

    Tolerates both :class:`merge.AcceptedRecord` namedtuples and the
    legacy bare-string callsites; bare strings are upgraded with
    ``reason=user-flag, source=cli`` because that is the only path that
    historically produced an entry on this list.
    """

    if isinstance(record, str):
        path = record
        reason = "user-flag"
        source = "cli"
    else:
        path = record.path
        reason = record.reason
        source = record.source
    return f"  - {path} [reason={reason}, source={source}]"


def parse_accepted_lines(lines):
    """Parse a sync-log accepted block. Accepts new and legacy shapes.

    ``lines`` is the iterable of body lines under ``- Accepted theirs:``
    (i.e. the ``  - ...`` continuations). Returns a list of
    :class:`ParsedAccepted`. The literal ``  - none`` placeholder is
    returned as an empty list.
    """

    out = []
    for raw in lines:
        line = raw.rstrip("\n")
        if not line.strip():
            continue
        # Match only the canonical placeholder shapes the writer can
        # emit: ``- none``, ``none``, or the indented ``  - none``. The
        # earlier ``endswith(" none")`` catch-all was too loose — it
        # would silently swallow a future path literally named ``none``.
        if line.strip() in {"- none", "none"}:
            continue
        match = _ACCEPTED_LINE_RE.match(line)
        if match:
            out.append(
                ParsedAccepted(
                    path=match.group("path").strip(),
                    reason=match.group("reason").strip(),
                    source=match.group("source").strip(),
                )
            )
            continue
        legacy = _LEGACY_ACCEPTED_LINE_RE.match(line)
        if legacy:
            out.append(
                ParsedAccepted(
                    path=legacy.group("path").strip(),
                    reason="legacy",
                    source="legacy",
                )
            )
    return out


def sync_log_entry(
    sync_now, migration, template_commit, updated, accepted, orphans, validation
):
    lines = [
        f"## {sync_now} - Sync to {migration['to']}",
        "",
        f"- From: {migration['from']}",
        f"- To: {migration['to']}",
        f"- Template commit: {template_commit[:7]}",
        "- Updated:",
    ]
    if updated:
        lines.extend(f"  - {item}" for item in updated)
    else:
        lines.append("  - none")
    lines.append("- Accepted theirs:")
    if accepted:
        lines.extend(_format_accepted_line(item) for item in accepted)
    else:
        lines.append("  - none")
    lines.extend([
        "- Preserved:",
        "  - .agent/project-profile.md",
        "  - .agent/gates.md",
        "  - .agent/ownership.md",
        "  - scripts/agent-eval.sh repo-specific gates",
        "- Warnings:",
    ])
    if orphans:
        lines.extend(f"  - orphan managed file: {item}" for item in orphans)
    else:
        lines.append("  - no managed-directory orphan files")
    lines.append("- Validation:")
    for item in validation:
        lines.append(f"  - {item}")
    return "\n".join(lines) + "\n"


def multi_hop_sync_log_entry(
    sync_now,
    original_from,
    final_to,
    chain,
    template_commit,
    updated,
    accepted,
    orphans,
    validation,
):
    chain_display = " -> ".join([original_from] + list(chain))
    lines = [
        f"## {sync_now} - Sync to {final_to} (multi-hop from {original_from})",
        "",
        f"- From: {original_from}",
        f"- To: {final_to}",
        f"- Chain: {chain_display}",
        f"- Template commit: {template_commit[:7]}",
        "- Updated:",
    ]
    if updated:
        lines.extend(f"  - {item}" for item in updated)
    else:
        lines.append("  - none")
    lines.append("- Accepted theirs:")
    if accepted:
        lines.extend(_format_accepted_line(item) for item in accepted)
    else:
        lines.append("  - none")
    lines.extend([
        "- Preserved:",
        "  - .agent/project-profile.md",
        "  - .agent/gates.md",
        "  - .agent/ownership.md",
        "  - scripts/agent-eval.sh repo-specific gates",
        "- Warnings:",
    ])
    if orphans:
        lines.extend(f"  - orphan managed file: {item}" for item in orphans)
    else:
        lines.append("  - no managed-directory orphan files")
    lines.append("- Validation:")
    for item in validation:
        lines.append(f"  - {item}")
    return "\n".join(lines) + "\n"


def restore_log_entry(sync_now, backup_id, restored_from, file_count, backup_dir):
    """Single-line audit entry appended after ``backups restore``.

    Per D-5, the log is **append-only**; restore must never truncate.
    The shape is fixed and grep-friendly.
    """

    return (
        f"## {sync_now} - Restore {backup_id}: reverted {file_count} files "
        f"to state at {restored_from}, source = {backup_dir}\n"
    )


def append_sync_log(target, entry):
    path = target / ".agent" / "sync-log.md"
    if path.exists():
        existing = path.read_text(encoding="utf-8")
        if not existing.endswith("\n"):
            existing += "\n"
        text = existing + "\n" + entry
    else:
        text = "# Sync Log\n\n" + entry
    path.write_text(text, encoding="utf-8")
