"""``.agent/sync-log.md`` entry formatters and appender.

The migration fixture suite greps the produced text for headings like
``"## ... Sync to X.Y.Z"`` and chain markers such as
``"Chain: 0.4.0 -> 0.5.0 -> ..."``, so the body of each helper here is
byte-stable and intentionally not generated through any templating
library.
"""

from __future__ import annotations


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
        lines.extend(f"  - {item}" for item in accepted)
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
        lines.extend(f"  - {item}" for item in accepted)
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
