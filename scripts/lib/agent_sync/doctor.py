"""Read-only diagnostics for a downstream target (Stage 2.2).

``agent-sync.sh doctor`` reports manifest/version health, distance to the
latest migratable template version, per-managed-file customization state
(vs. the template at the target's current version), and orphan paths.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def run_doctor(*, template_root: Path, target: Path, as_json: bool) -> int:
    from .errors import NoPathError, UsageError
    from .io_utils import read_json
    from .merge import collect_orphans
    from .migrations import expand_file_entries, list_migrations
    from .preflight import _classify_entry
    from .versions import compute_migration_chain, detect_current_version

    manifest_path = target / ".agent" / "manifest.json"
    if not manifest_path.is_file():
        raise UsageError(f"missing manifest: {manifest_path}")

    manifest = read_json(manifest_path)
    current = detect_current_version(manifest)

    _repo_lib = template_root / "scripts" / "lib"
    if str(_repo_lib) not in sys.path:
        sys.path.insert(0, str(_repo_lib))
    import check_version_consistency as vercheck  # noqa: WPS433

    # Plan Stage 2.2 (lines 494-495): doctor must refuse to render when
    # ``synced_to_template_version`` is not a valid semver. Silently
    # coercing a bad value here would make downstream fields (latest
    # migratable, hops-behind, managed-file scan) nonsensical while
    # returning rc=0 and ``manifest_ok=true`` — exactly the failure mode
    # a read-only diagnostic tool is supposed to catch.
    if not current or not vercheck.SEMVER_RE.fullmatch(current):
        raise UsageError(
            f"manifest at {manifest_path} has invalid "
            f"synced_to_template_version: {current!r} (expected semver)"
        )

    mig_versions = list_migrations(template_root)
    if not mig_versions:
        raise UsageError(
            f"no semver migrations under {template_root / 'core/migrations'}"
        )
    latest_m = mig_versions[-1]

    def _migration_has_planned_files(mig_ver: str) -> bool:
        p = template_root / "core" / "migrations" / mig_ver / "migration.json"
        m = read_json(p)
        return bool(m.get("safe_overwrite") or m.get("patches"))

    diagnostic_m = latest_m
    if not _migration_has_planned_files(diagnostic_m):
        for cand in reversed(mig_versions):
            if _migration_has_planned_files(cand):
                diagnostic_m = cand
                break

    changelog_ver = vercheck.extract_changelog_version(template_root)

    asymmetry_note = None
    if changelog_ver:
        chk = vercheck.SEMVER_RE
        if chk.fullmatch(changelog_ver) and chk.fullmatch(latest_m):
            ct = tuple(
                int(p) if p.isdigit() else 0
                for p in changelog_ver.split("-", 1)[0].split(".")
            )
            mt = tuple(
                int(p) if p.isdigit() else 0
                for p in latest_m.split("-", 1)[0].split(".")
            )
            if ct > mt:
                asymmetry_note = (
                    f"CHANGELOG release {changelog_ver} is newer than latest "
                    f"migratable {latest_m}; sync cannot apply beyond {latest_m} "
                    f"until that migration exists."
                )

    hops_behind = 0
    chain_error = None
    try:
        chain = compute_migration_chain(template_root, current, latest_m)
        hops_behind = len(chain)
    except NoPathError as exc:
        chain_error = str(exc)

    mig_path = (
        template_root / "core" / "migrations" / diagnostic_m / "migration.json"
    )
    migration = read_json(mig_path)
    entries, managed_scopes, adapter_report = expand_file_entries(
        template_root, migration, False, manifest
    )
    planned_targets = {e["target"] for e in entries}
    orphans = sorted(collect_orphans(target, managed_scopes, planned_targets))

    managed_files = []
    for entry in entries:
        state = _classify_entry(entry, target, template_root, current)
        managed_files.append(
            {
                "path": entry["target"],
                "kind": entry["kind"],
                "state": state,
            }
        )

    payload = {
        "manifest_ok": True,
        "current_version": current,
        "latest_migratable": latest_m,
        "diagnostic_migration": diagnostic_m,
        "latest_changelog_release": changelog_ver,
        "hops_behind_migratable": hops_behind,
        "migration_chain_error": chain_error,
        "asymmetry_note": asymmetry_note,
        "managed_files": managed_files,
        "orphans": orphans,
        "adapter_report_only": adapter_report,
    }

    if as_json:
        print(json.dumps(payload, indent=2))
        return 0

    print("Doctor (read-only)")
    print(f"  Target:                    {target}")
    print(f"  Current template version:  {current}")
    print(f"  Latest migratable:         {latest_m}")
    print(
        f"  Diagnostic migration:     {diagnostic_m} "
        f"(managed-file scan falls back when {latest_m} is a no-op)"
    )
    print(f"  Latest CHANGELOG release:  {changelog_ver}")
    print(f"  Single-hop hops to latest: {hops_behind}")
    if chain_error:
        print(f"  Migration chain:           ERROR {chain_error}")
    if asymmetry_note:
        print(f"  Asymmetry:                 {asymmetry_note}")
    print(f"  Managed files (vs v{current}): {len(managed_files)}")
    for row in managed_files:
        if row["state"] != "untouched":
            print(f"    {row['path']}: {row['state']} ({row['kind']})")
    print(f"  Orphan paths:              {len(orphans)}")
    for o in orphans[:20]:
        print(f"    {o}")
    if len(orphans) > 20:
        print(f"    ... and {len(orphans) - 20} more")
    if adapter_report:
        print(
            "  Adapter-skipped paths (pass --with-adapters to plan): "
            f"{len(adapter_report)}"
        )
    return 0
