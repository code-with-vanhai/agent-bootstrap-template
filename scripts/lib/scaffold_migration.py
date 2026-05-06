#!/usr/bin/env python3
"""Scaffold a schema-v1 ``migration.json`` skeleton (Stage 3.4).

Mechanical, read-only release helper. Given two release tags ``v<from>``
and ``v<to>``, this module diffs scoped template trees across the two
tags and emits a ``migration.json`` skeleton the release author can land
as-is for empty hops, or fill in for hops with patches / new
``manifest_updates`` directives.

Scoped trees (additive as of Medium-hardening, May 2026):

  - ``core/`` — auto-map prefixes (commands, workflows, roles, hooks,
    template suffix strip) plus template-internal skips.
  - ``scripts/`` — source and target coincide (canonical sync layout).
  - ``adapters/`` — canonical adapter sources map to downstream targets
    (matching real migrations since 0.9.0); unknown adapter paths emit
    ``source``/``target`` verbatim and remain in ``review``.

A second pass examines the repository-wide ``git diff`` between the
same tags and lists paths **outside** the scaffold pathspec (minus a
small ignore list for release-only noise) on stderr so a release
author cannot miss e.g. a root ``README.md`` change even when it is not
auto-included in ``safe_overwrite``.

Design constraints (locked by Stage 3.4):

  - **Python stdlib only.** No external packages. The whole runner
    pipeline is stdlib-only and the release tooling must not introduce a
    new toolchain (no Node, no semver libraries).
  - **No mutating git operations.** Reads tag trees via ``git diff`` /
    ``git rev-parse``. Never tags, fetches, pushes, or rewrites refs.
    The release-process docs explicitly forbid silent tag push by
    tooling; this module is a hard fence on that contract.
  - **Conservative target mapping.** Auto-maps only the well-known
    synced trees (``core/commands/*``, ``core/workflows/*``,
    ``core/roles/*``, ``core/hooks/*``, and ``core/<x>.template.<ext>``
    files that strip the ``.template`` segment to land under
    ``.agent/``). Everything else is emitted with ``source == target``
    and surfaced in the stderr review report so the author cannot
    silently ship a wrong target mapping.
  - **Renames and deletes always become removals.** A renamed or
    deleted ``core/`` path that previously had a downstream target
    (under the auto-map rules) lands in
    ``manifest_updates.tracked_files_remove`` so the Stage 3.3
    explicit-removal directive drops the stale tracked-files record on
    apply. The new path of a rename is added back as a normal
    ``safe_overwrite`` entry under its new mapping.

The output is always a *skeleton*: ``patches`` is empty, the notes
string is a placeholder, and the author is expected to review and
augment before committing. ``--write`` will refuse to overwrite an
existing ``migration.json`` unless ``--force`` is also passed; the
default is to print to stdout so an interactive run cannot accidentally
clobber a hand-edited migration.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

VERSION_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+(-[0-9A-Za-z.-]+)?$")

# ---------------------------------------------------------------------------
# Target-mapping rules.
#
# Each rule maps a ``core/<...>`` source path to a downstream target path
# under ``.agent/<...>``. Order matters — first match wins. Everything
# below the rule list is either skipped (template-only) or emitted with a
# ``source == target`` verbatim mapping plus a review hint. Keeping this
# list short and explicit makes the scaffolder transparent: a release
# author can read the rules and predict the output without running the
# tool.

_AUTO_MAP_PREFIXES = (
    ("core/commands/", ".agent/commands/"),
    ("core/workflows/", ".agent/workflows/"),
    ("core/roles/", ".agent/roles/"),
    ("core/hooks/", ".agent/hooks/"),
)

# One-off ``core/<file>`` paths whose downstream target does not follow a
# prefix rule but still has a known canonical mapping (verified against
# committed migrations, e.g. ``core/migrations/0.9.0/migration.json``).
# Listing them here keeps the scaffolder honest: a release that touches
# ``core/README.md`` produces the right ``.agent/README.md`` entry instead
# of silently dropping it under the template-internal skip list.
_CORE_EXACT_MAP = {
    "core/README.md": ".agent/README.md",
}

# Native-skills source files map to TWO downstream targets — one per
# Claude native skill root — guarded by ``enabled_when_path_exists`` so
# a downstream repo that opted out of one root does not get an unrelated
# tree materialized. Mirrors ``core/migrations/0.9.0/migration.json`` for
# ``core/skills/data-safety/SKILL.md``.
_SKILL_SOURCE_PREFIX = "core/skills/"
_SKILL_DOWNSTREAM_ROOTS = (
    ".agents/skills/agent-bootstrap",
    ".claude/skills/agent-bootstrap",
)

# ``adapters/*.md(c)`` in the template repo map to discrete downstream
# targets matching `core/migrations/0.9.0/migration.json` semantics.
_ADAPTER_MAP = {
    "adapters/AGENTS.md": {"target": "AGENTS.md"},
    "adapters/CLAUDE.md": {
        "target": "CLAUDE.md",
        "skip_if_target_missing": True,
    },
    "adapters/GEMINI.md": {
        "target": "GEMINI.md",
        "skip_if_target_missing": True,
    },
    "adapters/cursor-agent-system.mdc": {
        "target": ".cursor/rules/agent-system.mdc",
        "skip_if_target_missing": True,
    },
    "adapters/copilot-instructions.md": {
        "target": ".github/copilot-instructions.md",
        "skip_if_target_missing": True,
    },
}

_SCAFFOLD_PATHSPECS = ("core/", "scripts/", "adapters/")

# Prefixes suppressed in the informational "outside scaffold pathspec"
# notice — files here still changed in Git, they are intentionally not
# part of deterministic ``safe_overwrite`` scaffolding.
_OUTSIDE_SCAFFOLD_NOTICE_IGNORE_PREFIXES = (
    ".claude-plugin/",
    "tests/",
    "docs/",
    ".github/workflows/",
)


def is_template_test_file(source):
    """Return True iff ``source`` is a Python test module under ``scripts/``.

    Empirically (verified by ``rg`` over every committed migration),
    no schema-v1 ``migration.json`` has ever placed a
    ``scripts/**/test_*.py`` row under ``safe_overwrite`` — those
    modules are template-only CI gates with no downstream consumer
    and would only over-scaffold the skeleton with entries the author
    has to manually delete before release.

    The scaffolder filters them by default and surfaces the filtered
    paths in the stderr review report so the author still sees the
    diff. Pass ``--include-tests`` to override (rare; defensive).

    Pure / no I/O — also exported so unit tests can pin the heuristic
    without rebuilding a synthetic git repo.
    """

    if not source.startswith("scripts/"):
        return False
    name = source.rsplit("/", 1)[-1]
    return name.startswith("test_") and name.endswith(".py")

# Paths that are template-internal (consumed by the runner / release
# pipeline / template docs) and must never end up in a downstream sync.
_SKIP_PREFIXES = (
    "core/migrations/",
    "core/github/",
    "core/mcp/",
)
_SKIP_EXACT = frozenset(
    {
        "core/skills/README.md",
        "core/skills/manifest.json",
        "core/release-process.md",
        "core/release-tags.md",
        "core/research-basis.md",
        "core/command-conventions.md",
        "core/instantiation-prompt.md",
        "core/bootstrap-checklist.md",
        "core/bootstrap-steps.md",
        "core/gate-modes.json",
        "core/manifest.schema.json",
        "core/manifest.template.json",
    }
)


def classify_source_path(source):
    """Classify a template path for migration scaffolding.

    Returns ``(kind, source, target, review, extras)``:

      - ``kind=="skip"`` — template-internal; no ``safe_overwrite`` row.
        ``target`` is ``None``.
      - ``kind=="emit"`` — emit ``{"source": source, "target": target}``
        plus any non-empty ``extras`` (adapter flags).
        ``review`` asks the author to double-check ambiguous mappings.

        ``extras`` MUST only contain migration JSON keys copied verbatim
        into the entry (see ``adapter_files`` / ``skip_if_target_missing``
        symmetry on adapters).

    Pure function — easy to unit-test without touching git.
    """

    if source.startswith("scripts/"):
        # ``scripts/<dir>/<basename>.template.<ext>`` →
        # ``scripts/<dir>/<basename>.<ext>``. Mirrors the ``core/`` template
        # suffix rule so a release that ships e.g.
        # ``scripts/agent-eval.template.sh`` lands as ``scripts/agent-eval.sh``
        # downstream (matching ``core/migrations/0.9.0/migration.json``).
        head, sep, rest = source.rpartition("/")
        basename = rest if sep else source
        if ".template." in basename:
            stem, _, tail = basename.partition(".template.")
            stripped = f"{stem}.{tail}"
            tgt = f"{head}/{stripped}" if sep else stripped
            return ("emit", source, tgt, False, {})
        return ("emit", source, source, False, {})

    mapped = _ADAPTER_MAP.get(source)
    if mapped is not None:
        tgt = mapped["target"]
        extras = {k: v for k, v in mapped.items() if k != "target"}
        return ("emit", source, tgt, False, extras)

    if source.startswith("adapters/"):
        return ("emit", source, source, True, {})

    if not source.startswith("core/"):
        return ("emit", source, source, True, {})
    if source in _SKIP_EXACT:
        return ("skip", source, None, False, {})
    for prefix in _SKIP_PREFIXES:
        if source.startswith(prefix):
            return ("skip", source, None, False, {})
    if source.startswith(_SKILL_SOURCE_PREFIX):
        # Skill paths produce multiple entries — return the first as a
        # backward-compat shim. Multi-entry callers must use
        # ``classify_source_path_entries``.
        return _classify_skill_entries(source)[0]
    if source in _CORE_EXACT_MAP:
        return ("emit", source, _CORE_EXACT_MAP[source], False, {})
    for src_prefix, tgt_prefix in _AUTO_MAP_PREFIXES:
        if source.startswith(src_prefix):
            tgt = tgt_prefix + source[len(src_prefix):]
            return ("emit", source, tgt, False, {})
    # ``core/<basename>.template.<ext>`` → ``.agent/<basename>.<ext>``
    rest = source[len("core/"):]
    parts = rest.split("/")
    if len(parts) == 1 and ".template." in parts[0]:
        head, _, tail = parts[0].partition(".template.")
        tgt = f".agent/{head}.{tail}"
        return ("emit", source, tgt, False, {})
    return ("emit", source, source, True, {})


def _classify_skill_entries(source):
    """Return the list of dual-target entries for a ``core/skills/`` path.

    Empirically (verified against ``core/migrations/0.9.0/migration.json``)
    only nested skill content (``core/skills/<skill>/<...>``) gets the
    dual ``.agents/`` + ``.claude/`` mapping. Top-level files under
    ``core/skills/`` (``README.md``, ``manifest.json``) are
    template-internal and stay in ``_SKIP_EXACT``.
    """

    rel = source[len(_SKILL_SOURCE_PREFIX):]
    if "/" not in rel:
        # Top-level files under core/skills/ are handled by _SKIP_EXACT
        # — this branch only fires for paths the skip list missed.
        return [("skip", source, None, False, {})]
    entries = []
    for root in _SKILL_DOWNSTREAM_ROOTS:
        target = f"{root}/{rel}"
        entries.append(
            (
                "emit",
                source,
                target,
                False,
                {"enabled_when_path_exists": root},
            )
        )
    return entries


def classify_source_path_entries(source):
    """Return all migration entries for ``source`` (multi-target aware).

    Most paths produce a single entry — this function is a thin wrapper
    around :func:`classify_source_path`. ``core/skills/<skill>/<...>``
    paths produce two entries (one per Claude native skill root) so
    a single template source can land in both ``.agents/skills/...``
    and ``.claude/skills/...`` with the appropriate
    ``enabled_when_path_exists`` guard.

    Each element has the same ``(kind, source, target, review, extras)``
    shape as :func:`classify_source_path`. Pure / no I/O.
    """

    if source.startswith(_SKILL_SOURCE_PREFIX) and source not in _SKIP_EXACT:
        return _classify_skill_entries(source)
    return [classify_source_path(source)]


# ---------------------------------------------------------------------------
# Git helpers (read-only).


def _run_git(repo, *args):
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"git {' '.join(args)} failed: {proc.stderr.strip() or proc.stdout.strip()}"
        )
    return proc.stdout


def _tag_for(version):
    return f"v{version}"


def _ensure_tag(repo, version):
    """Read-only equivalent of ``git_ops.tag_commit`` for the scaffolder.

    The scaffolder cannot import :mod:`scripts.lib.agent_sync.git_ops`
    here because that module raises ``UsageError`` from a sync-runner
    error class hierarchy; this is a release-time tool. We mirror the
    canonical hint format so the author sees the same ``try git fetch
    --tags`` cue the runner shows on missing-tag errors.
    """

    try:
        _run_git(repo, "rev-parse", "--verify", f"{_tag_for(version)}^{{commit}}")
    except RuntimeError as exc:
        raise SystemExit(
            f"version {version} requires tag {_tag_for(version)}; "
            f"try git fetch --tags ({exc})"
        )


def _parse_name_status(text):
    """Parse ``git diff --name-status`` output into structured groups.

    Recognized statuses (schema v1 of git's name-status):

      - ``A`` — added in ``v<to>``.
      - ``M`` — modified between ``v<from>`` and ``v<to>``.
      - ``D`` — deleted in ``v<to>``.
      - ``R<score>`` — renamed (followed by old\\tnew).
      - ``C<score>`` — copied (followed by old\\tnew).
      - ``T`` — type changed (rare; treated like modify).

    Returns ``dict`` with lists ``added``, ``modified``, ``deleted``,
    ``renamed`` (list of ``(old, new)``), and ``copied`` (same shape).
    """

    added = []
    modified = []
    deleted = []
    renamed = []
    copied = []
    for raw in text.splitlines():
        if not raw:
            continue
        parts = raw.split("\t")
        status = parts[0]
        if status.startswith("R") and len(parts) >= 3:
            renamed.append((parts[1], parts[2]))
            continue
        if status.startswith("C") and len(parts) >= 3:
            copied.append((parts[1], parts[2]))
            continue
        if len(parts) < 2:
            continue
        path = parts[1]
        if status == "A":
            added.append(path)
        elif status in {"M", "T"}:
            modified.append(path)
        elif status == "D":
            deleted.append(path)
    return {
        "added": added,
        "modified": modified,
        "deleted": deleted,
        "renamed": renamed,
        "copied": copied,
    }


def _all_touch_paths(diff):
    paths = set()
    for bucket in ("added", "modified", "deleted"):
        paths.update(diff[bucket])
    for old, new in diff["renamed"]:
        paths.add(old)
        paths.add(new)
    for old, new in diff["copied"]:
        paths.add(old)
        paths.add(new)
    return paths


def _under_scaffold_pathspec(path):
    return path.startswith(_SCAFFOLD_PATHSPECS)


def _outside_scaffold_paths(full_diff):
    """Paths touched repo-wide minus scaffold scope and noise prefixes."""

    noisy = []
    for p in sorted(_all_touch_paths(full_diff)):
        if _under_scaffold_pathspec(p):
            continue
        if any(p.startswith(pref) for pref in _OUTSIDE_SCAFFOLD_NOTICE_IGNORE_PREFIXES):
            continue
        noisy.append(p)
    return noisy


def _diff_scaffold_scope(repo, from_version, to_version):
    text = _run_git(
        repo,
        "diff",
        "--name-status",
        "--find-renames",
        f"{_tag_for(from_version)}",
        f"{_tag_for(to_version)}",
        "--",
        *_SCAFFOLD_PATHSPECS,
    )
    return _parse_name_status(text)


def _diff_full_repo(repo, from_version, to_version):
    text = _run_git(
        repo,
        "diff",
        "--name-status",
        "--find-renames",
        f"{_tag_for(from_version)}",
        f"{_tag_for(to_version)}",
    )
    return _parse_name_status(text)


def removal_tracked_files_keys(source_path):
    """Return all downstream keys for ``tracked_files_remove``.

    Returns ``[]`` if the path is template-internal (skipped). For
    multi-target sources (``core/skills/<skill>/<...>``) returns one
    key per downstream root so a delete / rename clears every record
    the writer might have written for that source.
    """

    keys = []
    has_emit = False
    for kind, _, target, _, _ in classify_source_path_entries(source_path):
        if kind == "skip":
            continue
        has_emit = True
        keys.append(target if target is not None else source_path)
    if not has_emit:
        return []
    return keys


def removal_tracked_files_key(source_path):
    """Backward-compat: first downstream key, or ``None`` if skipped."""

    keys = removal_tracked_files_keys(source_path)
    return keys[0] if keys else None


# ---------------------------------------------------------------------------
# Skeleton builder.


def _is_post_1_0(version):
    """Return True if ``version`` is at or beyond 1.0.0.

    Used to decide whether to default ``update_tracked_files: true`` in
    the skeleton. Pre-1.0.0 migrations stay opt-out by default to keep
    every legacy fixture byte-stable; post-1.0.0 migrations inherit the
    Stage 3.3 backfill state and should keep the writer on so
    ``manifest.tracked_files`` stays current.
    """

    parts = version.split("-", 1)[0].split(".")
    try:
        major = int(parts[0])
    except (ValueError, IndexError):
        return False
    return major >= 1


def build_skeleton(repo, from_version, to_version, *, include_tests=False):
    """Build a schema-v1 ``migration.json`` skeleton + a review report.

    Returns ``(skeleton_dict, report)``. ``report`` contains
    ``review_required``, ``skipped`` (template-internal under the scoped
    diff plus any ``scripts/**/test_*.py`` filtered out by the default
    test-exclusion policy), and ``outside_scaffold`` (repo-wide changes
    outside ``core/`` / ``scripts/`` / ``adapters/`` minus noise
    prefixes — informational only).

    ``include_tests`` (default ``False``) overrides the default
    exclusion of ``scripts/**/test_*.py``. The default is
    safe-by-empirical-precedent: every committed migration verifiably
    omits test modules from ``safe_overwrite``. Pass ``True`` to opt
    back in (CLI: ``--include-tests``).
    """

    if not VERSION_RE.match(from_version):
        raise SystemExit(f"invalid <from> version: {from_version}")
    if not VERSION_RE.match(to_version):
        raise SystemExit(f"invalid <to> version: {to_version}")
    if from_version == to_version:
        raise SystemExit(f"<from> ({from_version}) must differ from <to> ({to_version})")

    _ensure_tag(repo, from_version)
    _ensure_tag(repo, to_version)

    scoped_diff = _diff_scaffold_scope(repo, from_version, to_version)
    full_diff = _diff_full_repo(repo, from_version, to_version)

    safe_overwrite = []
    tracked_files_remove = []
    review_required = []
    skipped = []
    seen_targets = set()

    def emit_entry(kind, src, tgt, review, extras):
        if kind != "emit" or tgt is None:
            return
        if tgt in seen_targets:
            return
        seen_targets.add(tgt)
        entry = {"source": src, "target": tgt}
        entry.update(extras)
        safe_overwrite.append(entry)
        if review:
            review_required.append(f"{src} -> {tgt}")

    def _filtered_test(source):
        # Default-on test-filter: short-circuits before classify so a
        # ``scripts/**/test_*.py`` change lands in the skipped report
        # exactly like a ``core/migrations/`` directive change does
        # under ``classify_source_path``.
        return (not include_tests) and is_template_test_file(source)

    def _emit_or_skip(source):
        entries = classify_source_path_entries(source)
        if all(e[0] == "skip" for e in entries):
            skipped.append(source)
            return
        for entry in entries:
            if entry[0] == "skip":
                continue
            emit_entry(*entry)

    for source in sorted(set(scoped_diff["added"]) | set(scoped_diff["modified"])):
        if _filtered_test(source):
            skipped.append(source)
            continue
        _emit_or_skip(source)

    # Renames: emit a removal for the OLD target (if it had a known
    # downstream mapping) and a safe_overwrite for the NEW source.
    for old_source, new_source in scoped_diff["renamed"]:
        if _filtered_test(old_source):
            skipped.append(old_source)
        else:
            old_entries = classify_source_path_entries(old_source)
            tracked_files_remove.extend(removal_tracked_files_keys(old_source))
            if any(e[0] == "emit" and e[3] for e in old_entries):
                review_required.append(f"removed: {old_source} (rename)")
        if _filtered_test(new_source):
            skipped.append(new_source)
            continue
        _emit_or_skip(new_source)

    # Pure deletes: removal only.
    for source in scoped_diff["deleted"]:
        if _filtered_test(source):
            skipped.append(source)
            continue
        entries = classify_source_path_entries(source)
        if all(e[0] == "skip" for e in entries):
            skipped.append(source)
            continue
        tracked_files_remove.extend(removal_tracked_files_keys(source))
        if any(e[0] == "emit" and e[3] for e in entries):
            review_required.append(f"removed: {source}")

    # Copies are rare; treat the new path like an add.
    for _old, new_source in scoped_diff["copied"]:
        if _filtered_test(new_source):
            skipped.append(new_source)
            continue
        _emit_or_skip(new_source)

    tracked_files_remove = sorted(set(tracked_files_remove))

    manifest_updates = {
        "replace": {
            "template_version": to_version,
            "synced_to_template_version": to_version,
        },
        "replace_from_git_tag": {
            "synced_to_template_commit": to_version,
        },
        "append_to_array_unique": {
            "notes": (
                f"Synced to v{to_version}: scaffolded skeleton — "
                f"replace this note with a human summary before release."
            ),
        },
        "merge_array_unique": {},
    }

    # Default ``update_tracked_files`` on for any hop that is anchored
    # at 1.0.0+ on either end so the Stage 3.1 writer keeps the map
    # fresh after the 1.0.0 backfill. Pre-1.0.0 patch migrations stay
    # opt-out by default so legacy fixtures continue to assert
    # byte-stable manifests.
    if _is_post_1_0(from_version) or _is_post_1_0(to_version):
        manifest_updates["update_tracked_files"] = True

    if tracked_files_remove:
        manifest_updates["update_tracked_files"] = True
        manifest_updates["tracked_files_remove"] = tracked_files_remove

    skeleton = {
        "schema_version": 1,
        "version": to_version,
        "from_versions": [from_version],
        "to": to_version,
        "safe_overwrite": safe_overwrite,
        "patches": [],
        "manifest_updates": manifest_updates,
    }

    outside = _outside_scaffold_paths(full_diff)

    return skeleton, {
        "review_required": sorted(set(review_required)),
        "skipped": sorted(set(skipped)),
        "outside_scaffold": outside,
    }


# ---------------------------------------------------------------------------
# CLI.


def _format_skeleton(skeleton):
    """Pretty-print skeleton with stable 2-space indent.

    Matches the formatting of every existing
    ``core/migrations/*/migration.json`` so a ``--write`` run produces
    a file the author can land without re-running a formatter.
    """

    return json.dumps(skeleton, indent=2, ensure_ascii=False) + "\n"


def _emit_review(report, stream):
    if report["review_required"]:
        stream.write("Review required (target mapping not auto-derived):\n")
        for line in report["review_required"]:
            stream.write(f"  - {line}\n")
    if report["skipped"]:
        stream.write("Skipped (template-internal, not synced downstream):\n")
        for line in report["skipped"]:
            stream.write(f"  - {line}\n")
    if report.get("outside_scaffold"):
        stream.write(
            "Changed outside scaffold pathspec (not auto-added to skeleton):\n"
        )
        for line in report["outside_scaffold"]:
            stream.write(f"  - {line}\n")


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="scaffold-migration",
        description="Scaffold a schema-v1 migration.json from a tag diff.",
    )
    parser.add_argument("from_version", metavar="<from>")
    parser.add_argument("to_version", metavar="<to>")
    parser.add_argument(
        "--template-root",
        default=".",
        help="Template repo root (default: cwd).",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Write to core/migrations/<to>/migration.json instead of stdout.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="With --write, overwrite an existing migration.json (default: refuse).",
    )
    parser.add_argument(
        "--include-tests",
        action="store_true",
        help=(
            "Include scripts/**/test_*.py changes in the skeleton "
            "(default: filter and surface in the stderr review report). "
            "No committed migration has historically shipped test files; "
            "pass this only if you intentionally want them in safe_overwrite."
        ),
    )
    args = parser.parse_args(argv)

    repo = Path(args.template_root).resolve()
    if not (repo / ".git").exists():
        raise SystemExit(f"--template-root is not a git repo: {repo}")

    skeleton, report = build_skeleton(
        repo,
        args.from_version,
        args.to_version,
        include_tests=args.include_tests,
    )
    text = _format_skeleton(skeleton)

    if args.write:
        target = repo / "core" / "migrations" / args.to_version / "migration.json"
        if target.exists() and not args.force:
            raise SystemExit(
                f"refusing to overwrite existing migration: {target} "
                f"(pass --force to overwrite)"
            )
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
        sys.stdout.write(f"wrote {target}\n")
    else:
        sys.stdout.write(text)

    _emit_review(report, sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
