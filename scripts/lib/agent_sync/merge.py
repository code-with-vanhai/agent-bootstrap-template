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

from .errors import ConflictError, UsageError
from .git_ops import git_show, sha, tag_exists, tag_for, try_git_show
from .io_utils import read_bytes, write_bytes


AcceptedRecord = namedtuple("AcceptedRecord", ["path", "reason", "source"])


REASON_USER_FLAG = "user-flag"
REASON_CATALOG_BASELINE_MATCH = "catalog-baseline-match"
REASON_FAST_PATH = "checksum-fast-path"


def _ensure_tags_for_three_way(template_root, migration, _state):
    """Lazy per-hop tag check for the 3-way merge fall-through path.

    Idempotent — once both ``v<from>`` and ``v<to>`` are confirmed for a
    hop, the second-and-later 3-way fall-throughs in the same hop skip
    the subprocess. Stage 3.2 deliberately makes the check lazy so a hop
    where every entry takes the checksum fast-path never needs ``v<from>``
    to exist locally (AC-6).
    """
    if _state.get("validated"):
        return
    for version in (migration["from"], migration["to"]):
        if not tag_exists(template_root, version):
            raise UsageError(
                f"version {version} requires tag {tag_for(version)}; try git fetch --tags"
            )
    _state["validated"] = True


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
    tracked_files=None,
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
    tracked_files:
        Optional ``manifest.tracked_files`` map (Stage 3.1+) used by the
        Stage 3.2 checksum fast-path. When ``ours`` matches the
        recorded ``synced_checksum_sha256`` for ``target_rel``, only
        ``v<to>`` is consulted (for ``theirs``); ``v<from>`` is never
        touched (AC-6). Absent map means every entry takes the existing
        3-way merge path, preserving pre-Stage-3.2 behavior verbatim.
    """

    tracked_files = tracked_files if isinstance(tracked_files, dict) else {}
    tag_state = {"validated": False}

    for entry in entries:
        source = entry["source"]
        target_rel = entry["target"]
        condition = entry.get("enabled_when_path_exists")
        if condition and not (target / condition).exists():
            continue
        target_path = target / target_rel
        if entry.get("skip_if_target_missing") and not target_path.exists():
            continue
        ours = read_bytes(target_path)

        # Stage 3.2 fast-path: when ``ours`` matches a recorded
        # ``synced_checksum_sha256``, the only template-side bytes we
        # need are ``theirs`` from ``v<to>``. ``v<from>`` is never
        # consulted on this branch — that is what makes AC-6 hold in an
        # ephemeral mirror missing ``v<from>``. ``try_git_show`` returns
        # None on either tag-missing or path-missing; both fall through
        # to 3-way merge which raises the existing tag-required hint.
        record = tracked_files.get(target_rel)
        if (
            isinstance(record, dict)
            and ours is not None
            and isinstance(record.get("synced_checksum_sha256"), str)
            and record["synced_checksum_sha256"] == _sha256_hex(ours)
        ):
            theirs_fast = try_git_show(template_root, migration["to"], source)
            if theirs_fast is not None:
                if theirs_fast == ours:
                    continue
                writes[target_rel] = theirs_fast
                accepted.append(
                    AcceptedRecord(
                        path=target_rel,
                        reason=REASON_FAST_PATH,
                        source=f"tracked_files@{record.get('synced_at_version', '?')}",
                    )
                )
                updated.append(target_rel)
                continue
            # theirs_fast is None: fall through to 3-way merge so the
            # existing missing-tag UsageError surfaces with the
            # actionable "git fetch --tags" hint.

        # 3-way merge (unchanged semantics). Lazy tag check fires on
        # the first entry that actually needs it; fast-path entries do
        # not pay this cost.
        _ensure_tags_for_three_way(template_root, migration, tag_state)
        base = git_show(template_root, migration["from"], source)
        theirs = git_show(template_root, migration["to"], source, required=True)

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
