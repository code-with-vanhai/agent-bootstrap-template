"""Three-way safe-overwrite planner, write applier, and orphan collector.

The planner is intentionally conservative: it raises
:class:`ConflictError` (printing base/ours/theirs SHAs and inspect
commands to stderr) the moment any local modification disagrees with
both the previous and incoming template version, unless the caller
listed that path in ``--accept-theirs`` or the migration declares the
path under ``known_conflicts`` AND the current sha256 matches one of
the recorded ``baseline_sha256`` values for that path (Stage 1.1
hash-guarded catalog).

:func:`apply_writes` is the single funnel for writes: every entry from
the planner ends up here, and shell scripts under ``scripts/`` are
chmod-ed ``0o755`` so the generated repo gets executables right.

:func:`collect_orphans` walks each ``managed_scope`` (a directory that
the migration claims ownership of) and reports any file there that the
plan did NOT touch — those are typically renamed/dropped artifacts the
target should review.

D-12 (revision 7 of the migration UX plan) replaces the previous
``accepted: list[str]`` API with ``list[AcceptedRecord]`` so the audit
trail can distinguish ``--accept-theirs`` overrides from
``known_conflicts`` baseline-hash auto-accepts.
"""

from __future__ import annotations

import hashlib
import sys
from collections import namedtuple

from .errors import ConflictError
from .git_ops import git_show, sha, tag_for
from .io_utils import read_bytes, write_bytes


AcceptedRecord = namedtuple("AcceptedRecord", ["path", "reason", "source"])


REASON_USER_FLAG = "user-flag"
REASON_CATALOG_BASELINE_MATCH = "catalog-baseline-match"


def _sha256_hex(data):
    return hashlib.sha256(data).hexdigest()


def compute_base_sha(entry, template_root, version):
    """Return the sha256 hex digest of the template-side source at ``v<version>``.

    Returns ``None`` when the source path did not exist at that tag (e.g.
    a file added in a later release). Source and target paths can differ
    (rendered template vs. relocated downstream), so this helper is the
    canonical way for preflight / fast-path code to reason about base
    bytes without re-implementing ``git show v<v>:<entry["source"]>``.
    """
    data = git_show(template_root, version, entry["source"])
    if data is None:
        return None
    return _sha256_hex(data)


def _catalog_lookup(known_conflicts, target_rel):
    """Return the ``CatalogEntry`` dict that targets ``target_rel`` or ``None``.

    Per the plan's schema, each entry is
    ``{"path": str, "baseline_sha256": list[str]}``. Unknown / malformed
    entries are silently skipped — the catalog is a best-effort hint.
    """
    if not known_conflicts:
        return None
    for entry in known_conflicts:
        if not isinstance(entry, dict):
            continue
        if entry.get("path") == target_rel:
            baselines = entry.get("baseline_sha256")
            if isinstance(baselines, list) and all(
                isinstance(item, str) for item in baselines
            ):
                return entry
    return None


def plan_safe_overwrites(
    template_root,
    target,
    migration,
    entries,
    accept_theirs,
    writes,
    updated,
    accepted,
    known_conflicts=None,
    catalog_source_label=None,
):
    """Plan ``safe_overwrite`` writes with hash-guarded catalog support.

    Parameters
    ----------
    known_conflicts:
        Optional list of catalog entries (``{"path": str,
        "baseline_sha256": list[str]}``). When the per-file 3-way merge
        falls into the conflict branch and the target is listed AND the
        current sha matches one of ``baseline_sha256``, the entry is
        auto-accepted with reason ``catalog-baseline-match``. If the
        target is listed but the sha does not match, the conflict still
        surfaces (per ``core/migrations/README.md:20``).
    catalog_source_label:
        Free-form string (e.g. ``"0.7.0->0.8.0 catalog"``) used in the
        accepted record's ``source`` field so the sync-log can attribute
        the auto-accept to the originating hop.
    """

    for entry in entries:
        source = entry["source"]
        target_rel = entry["target"]
        condition = entry.get("enabled_when_path_exists")
        if condition and not (target / condition).exists():
            continue
        target_path = target / target_rel
        if entry.get("skip_if_target_missing") and not target_path.exists():
            continue
        base = git_show(template_root, migration["from"], source)
        theirs = git_show(template_root, migration["to"], source, required=True)
        ours = read_bytes(target_path)

        if ours == theirs:
            continue
        if base is not None and ours == base:
            writes[target_rel] = theirs
            updated.append(target_rel)
            continue
        if base is None and ours is None:
            writes[target_rel] = theirs
            updated.append(target_rel)
            continue
        if target_rel in accept_theirs:
            writes[target_rel] = theirs
            accepted.append(
                AcceptedRecord(
                    path=target_rel, reason=REASON_USER_FLAG, source="cli"
                )
            )
            updated.append(target_rel)
            continue

        catalog_entry = _catalog_lookup(known_conflicts, target_rel)
        if catalog_entry is not None and ours is not None:
            current_sha = _sha256_hex(ours)
            if current_sha in catalog_entry["baseline_sha256"]:
                writes[target_rel] = theirs
                accepted.append(
                    AcceptedRecord(
                        path=target_rel,
                        reason=REASON_CATALOG_BASELINE_MATCH,
                        source=catalog_source_label or "catalog",
                    )
                )
                updated.append(target_rel)
                print(
                    f"Auto-accepting catalog conflict: {target_rel} "
                    f"[reason={REASON_CATALOG_BASELINE_MATCH}]",
                    file=sys.stderr,
                )
                continue
            print(
                f"Catalog conflict but file customized: {target_rel} "
                f"(sha differs from all known baselines; pass "
                f"--accept-theirs to proceed)",
                file=sys.stderr,
            )

        print(f"CONFLICT: {target_rel}", file=sys.stderr)
        print(f"  base:   {sha(base)}", file=sys.stderr)
        print(f"  ours:   {sha(ours)}", file=sys.stderr)
        print(f"  theirs: {sha(theirs)}", file=sys.stderr)
        print(
            f"  inspect base:   git -C {template_root} show {tag_for(migration['from'])}:{source}",
            file=sys.stderr,
        )
        print(
            f"  inspect theirs: git -C {template_root} show {tag_for(migration['to'])}:{source}",
            file=sys.stderr,
        )
        print(f"  inspect ours:   sed -n '1,220p' {target_path}", file=sys.stderr)
        raise ConflictError(
            f"conflict detected in {target_rel}; aborted before writes"
        )


def apply_writes(target, writes):
    for rel, data in sorted(writes.items()):
        mode = None
        if rel.startswith("scripts/") and rel.endswith(".sh"):
            mode = 0o755
        write_bytes(target / rel, data, mode)


def collect_orphans(target, managed_scopes, planned_targets):
    orphans = []
    for managed_dir, first_component_prefix in sorted(managed_scopes):
        root = target / managed_dir
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            rel = path.relative_to(target).as_posix()
            rel_to_managed = path.relative_to(root)
            first_component = rel_to_managed.parts[0] if rel_to_managed.parts else ""
            if first_component_prefix and not first_component.startswith(
                first_component_prefix
            ):
                continue
            if rel not in planned_targets:
                orphans.append(rel)
    return sorted(orphans)
