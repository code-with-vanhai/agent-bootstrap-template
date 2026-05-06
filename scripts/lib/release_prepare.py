#!/usr/bin/env python3
"""Semantic-release-style scaffold for mechanical release prep (Stage 3.4).

Replaces the npm ``semantic-release`` toolchain the original Stage 3.4
plan implied. The whole runner is **Python stdlib only**, so we inline a
small, transparent helper that mirrors the few pieces of the
``semantic-release`` workflow we actually want automated for this
template:

  - read commits in ``<latest-tag>..HEAD`` (or any other range) and
    classify each subject through the same rules as
    :mod:`scripts.lib.check_conventional_commits`;
  - derive the next semver bump from those subjects:
    ``major`` if any commit has a ``!`` marker or a ``BREAKING CHANGE:``
    trailer, else ``minor`` if any ``feat`` exists, else ``patch``;
  - run :mod:`scripts.lib.bump_version` on the derived next version,
    which is the **single funnel** that mutates version sources
    (CHANGELOG.md, plugin/marketplace JSONs, bootstrap-request.sh,
    release-tags.md);
  - patch the empty ``- `` bullet that ``bump_version`` inserts under
    the new ``## <version> - <date>`` heading with a draft changelog
    body derived from the commits.

The helper **never** calls ``git tag``, ``git push``, ``git commit``, or
``git fetch``. Tag creation and push remain a human-triggered step per
``core/release-process.md``. The default mode is dry-run: only ``--apply``
mutates files (and even then only via ``bump_version`` and a CHANGELOG
patch — no refs are touched).

Stage 3.4 release-process invariants (cross-reference):

  - ``core/release-process.md`` Tag Rules: tag creation and ``git push
    origin <tag>`` are always human-triggered. This module embodies
    that rule by construction.
  - ``core/release-process.md`` Conventional Commits: this helper
    refuses to ``--apply`` when commits in the range fail the
    Conventional Commits gate (unless ``--allow-violations`` is passed
    for an explicit override). The same gate runs in CI on every PR.

Usage:

    # Dry-run plan (default; no writes, no git mutations)
    python3 scripts/lib/release_prepare.py

    # Apply the bump (calls bump_version.bump + patches CHANGELOG)
    python3 scripts/lib/release_prepare.py --apply

    # Override the bump derivation
    python3 scripts/lib/release_prepare.py --bump minor

    # Machine-readable plan for tooling/CI
    python3 scripts/lib/release_prepare.py --json
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import re
import subprocess
import sys
from typing import Iterable, NamedTuple

_REPO_LIB = pathlib.Path(__file__).resolve().parent
if str(_REPO_LIB) not in sys.path:
    sys.path.insert(0, str(_REPO_LIB))

import bump_version  # noqa: E402
import check_conventional_commits as ccc  # noqa: E402
import check_version_consistency as vercheck  # noqa: E402

# ---------------------------------------------------------------------------
# Pure helpers (no git, no I/O).
# ---------------------------------------------------------------------------

# Conventional-commits subject grammar shared with the CI gate.
_SUBJECT_RE = ccc._build_subject_re(ccc.DEFAULT_TYPES)

# ``BREAKING CHANGE:`` / ``BREAKING-CHANGE:`` trailer. Spec allows either
# spelling; we accept both. The trailer must start a line within the
# body so an off-hand mention in prose does not flip the bump.
_BREAKING_TRAILER_RE = re.compile(
    r"^BREAKING[ -]CHANGE:\s*\S",
    re.MULTILINE,
)

# Display priority for the changelog draft. Types not in this list are
# bucketed under "Other" so a release author cannot lose information by
# adding a custom type that the helper has not learned yet.
_TYPE_PRIORITY = (
    "feat",
    "fix",
    "perf",
    "refactor",
    "docs",
    "test",
    "build",
    "ci",
    "chore",
    "style",
    "revert",
)


class Commit(NamedTuple):
    sha: str
    parents: int
    subject: str
    body: str

    @property
    def short_sha(self) -> str:
        return self.sha[:7]


class ParsedSubject(NamedTuple):
    type: str | None
    scope: str | None
    breaking: bool
    description: str
    ok: bool


def parse_subject(subject: str) -> ParsedSubject:
    """Parse a subject into typed fields. ``ok=False`` for non-conformant."""

    match = _SUBJECT_RE.match(subject)
    if not match:
        return ParsedSubject(None, None, False, subject, False)
    scope = match.group("scope")
    if scope is not None:
        scope = scope[1:-1]  # strip parens
    return ParsedSubject(
        type=match.group("type"),
        scope=scope,
        breaking=bool(match.group("breaking")),
        description=match.group("description").strip(),
        ok=True,
    )


def commit_is_breaking(commit: Commit, parsed: ParsedSubject) -> bool:
    """``True`` if ``commit`` carries a breaking-change marker."""

    if parsed.breaking:
        return True
    if commit.body and _BREAKING_TRAILER_RE.search(commit.body):
        return True
    return False


def commit_is_release_relevant(commit: Commit, parsed: ParsedSubject) -> bool:
    """Auto-generated commits do not influence the bump / changelog.

    Mirrors the exemptions in :mod:`scripts.lib.check_conventional_commits`:
    GitHub merge commits (``Merge `` subject + >=2 parents) and
    ``git revert`` defaults (``Revert "..."``) are skipped.
    """

    if commit.parents >= 2 and commit.subject.startswith("Merge "):
        return False
    if commit.subject.startswith('Revert "'):
        return False
    return True


def derive_bump(commits: Iterable[Commit]) -> str | None:
    """Return ``"major"`` / ``"minor"`` / ``"patch"`` / ``None``.

    ``None`` when no release-relevant commits exist in the range. The
    caller treats that as a no-op (nothing to release).
    """

    saw_relevant = False
    saw_feat = False
    saw_breaking = False
    for commit in commits:
        parsed = parse_subject(commit.subject)
        if not commit_is_release_relevant(commit, parsed):
            continue
        saw_relevant = True
        if not parsed.ok:
            # Unknown shape still counts as relevant — release authors
            # should not be allowed to ship a release with parse-violating
            # commits silently. The bump derivation conservatively treats
            # these as ``patch`` (lowest impact) so the gate, not this
            # module, decides whether to refuse.
            continue
        if commit_is_breaking(commit, parsed):
            saw_breaking = True
        if parsed.type == "feat":
            saw_feat = True
    if not saw_relevant:
        return None
    if saw_breaking:
        return "major"
    if saw_feat:
        return "minor"
    return "patch"


def compute_next_version(current: str, bump: str) -> str:
    """Apply ``bump`` to ``current``. Both must be plain X.Y.Z semver.

    Pre-release / build suffixes are intentionally rejected: this
    template's version sources are always plain ``X.Y.Z`` (see
    :mod:`scripts.lib.check_version_consistency`) and inheriting an
    ``rc``/``alpha`` from upstream would change semver math (which
    "patch" should produce: ``1.0.0-rc.2`` or ``1.0.1``?). Defer until
    a real need exists rather than guess.
    """

    if not vercheck.SEMVER_RE.fullmatch(current):
        raise ValueError(f"current version is not semver: {current!r}")
    if "-" in current or "+" in current:
        raise ValueError(
            f"pre-release/build suffix not supported: {current!r}; "
            "release_prepare expects plain X.Y.Z"
        )
    parts = current.split(".")
    if len(parts) != 3 or not all(p.isdigit() for p in parts):
        raise ValueError(f"current version is not X.Y.Z: {current!r}")
    major, minor, patch = (int(p) for p in parts)
    if bump == "major":
        return f"{major + 1}.0.0"
    if bump == "minor":
        return f"{major}.{minor + 1}.0"
    if bump == "patch":
        return f"{major}.{minor}.{patch + 1}"
    raise ValueError(f"unknown bump: {bump!r}")


def build_changelog_draft(commits: list[Commit]) -> str:
    """Build a grouped bullet list for the new CHANGELOG entry.

    The draft is a *starting point*: release authors are expected to
    rewrite into prose matching the repo's editorial style. We keep the
    structure boring and predictable so the diff is easy to review.
    """

    buckets: dict[str, list[tuple[Commit, ParsedSubject]]] = {}
    other: list[tuple[Commit, ParsedSubject]] = []
    for commit in commits:
        parsed = parse_subject(commit.subject)
        if not commit_is_release_relevant(commit, parsed):
            continue
        if not parsed.ok:
            other.append((commit, parsed))
            continue
        key = parsed.type if parsed.type in _TYPE_PRIORITY else "other"
        buckets.setdefault(key, []).append((commit, parsed))

    lines: list[str] = []
    for type_name in _TYPE_PRIORITY:
        rows = buckets.get(type_name)
        if not rows:
            continue
        lines.append(f"- **{_section_label(type_name)}**")
        for commit, parsed in rows:
            scope = f"({parsed.scope})" if parsed.scope else ""
            marker = "!" if commit_is_breaking(commit, parsed) else ""
            lines.append(
                f"  - {parsed.type}{scope}{marker}: {parsed.description} "
                f"({commit.short_sha})"
            )
    leftover = [*buckets.get("other", []), *other]
    if leftover:
        lines.append("- **Other**")
        for commit, parsed in leftover:
            if parsed.ok:
                scope = f"({parsed.scope})" if parsed.scope else ""
                marker = "!" if commit_is_breaking(commit, parsed) else ""
                lines.append(
                    f"  - {parsed.type}{scope}{marker}: {parsed.description} "
                    f"({commit.short_sha})"
                )
            else:
                lines.append(f"  - {commit.subject} ({commit.short_sha})")
    if not lines:
        return "- (no release-relevant commits)"
    return "\n".join(lines)


def _section_label(type_name: str) -> str:
    return {
        "feat": "Features",
        "fix": "Fixes",
        "perf": "Performance",
        "refactor": "Refactor",
        "docs": "Docs",
        "test": "Tests",
        "build": "Build",
        "ci": "CI",
        "chore": "Chores",
        "style": "Style",
        "revert": "Reverts",
    }.get(type_name, type_name.capitalize())


# ---------------------------------------------------------------------------
# Git wrappers (read-only).
# ---------------------------------------------------------------------------


def _quiet_current_version(root: pathlib.Path) -> str | None:
    """Return the unified template version, or ``None`` on skew/missing.

    Mirrors :func:`check_version_consistency.report` semantics but silent
    on stdout so dry-run output stays focused on the release plan. Errors
    still go to stderr so the caller can act on them.
    """

    rows = list(vercheck.collect(root))
    missing = [name for name, value in rows if value is None]
    if missing:
        sys.stderr.write(
            "release_prepare: missing version in:\n  - "
            + "\n  - ".join(missing)
            + "\nFix sources first (run scripts/lib/check_version_consistency.py).\n"
        )
        return None
    bad = [(n, v) for n, v in rows if not vercheck.SEMVER_RE.fullmatch(v or "")]
    if bad:
        sys.stderr.write(
            "release_prepare: non-semver values:\n  - "
            + "\n  - ".join(f"{n}: {v!r}" for n, v in bad)
            + "\n"
        )
        return None
    distinct = {v for _, v in rows}
    if len(distinct) != 1:
        sys.stderr.write(
            "release_prepare: version skew across sources:\n  - "
            + "\n  - ".join(f"{n}: {v!r}" for n, v in rows)
            + "\nRun scripts/lib/check_version_consistency.py for details.\n"
        )
        return None
    return next(iter(distinct))


def _run_git(repo: pathlib.Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise SystemExit(
            f"git {' '.join(args)} failed: "
            f"{proc.stderr.strip() or proc.stdout.strip()}"
        )
    return proc.stdout


def latest_release_tag(repo: pathlib.Path) -> str | None:
    """Return the highest semver release tag (``v0.11.0`` etc.) or ``None``."""

    out = _run_git(repo, "tag", "--list", "v[0-9]*", "--sort=-v:refname")
    for line in out.splitlines():
        line = line.strip()
        if line.startswith("v"):
            return line
    return None


def parse_commits(repo: pathlib.Path, range_spec: str) -> list[Commit]:
    """Return ``[Commit, ...]`` for ``range_spec`` in chronological order.

    Uses ``--reverse`` so the changelog draft lists the oldest commit
    first, matching how a human reviewing the diff would scan it.
    """

    # NUL-delimited so commit bodies with newlines are unambiguous.
    sep = "\x1e"  # record separator
    fmt = f"%H{sep}%P{sep}%s{sep}%b%x00"
    out = _run_git(
        repo,
        "log",
        "--reverse",
        f"--format={fmt}",
        "--no-color",
        range_spec,
    )
    commits: list[Commit] = []
    for record in out.split("\x00"):
        record = record.strip("\n")
        if not record:
            continue
        parts = record.split(sep, 3)
        if len(parts) < 4:
            continue
        sha, parents, subject, body = parts
        parent_count = len(parents.split()) if parents.strip() else 0
        commits.append(
            Commit(
                sha=sha,
                parents=parent_count,
                subject=subject,
                body=body.rstrip("\n"),
            )
        )
    return commits


# ---------------------------------------------------------------------------
# Plan + apply.
# ---------------------------------------------------------------------------


class Plan(NamedTuple):
    range_spec: str
    current_version: str
    next_version: str | None  # ``None`` when nothing to release
    bump: str | None  # same condition
    bump_source: str  # ``"derived"`` or ``"override"``
    commits: list[Commit]
    violations: list[dict]
    changelog_draft: str

    def to_dict(self) -> dict:
        return {
            "range": self.range_spec,
            "current_version": self.current_version,
            "next_version": self.next_version,
            "bump": self.bump,
            "bump_source": self.bump_source,
            "commits": [
                {
                    "sha": c.sha,
                    "short_sha": c.short_sha,
                    "subject": c.subject,
                    "parents": c.parents,
                }
                for c in self.commits
            ],
            "violations": list(self.violations),
            "changelog_draft": self.changelog_draft,
        }


def prepare_plan(
    *,
    repo: pathlib.Path,
    range_spec: str,
    current_version: str,
    override_bump: str | None,
) -> Plan:
    """Compute the dry-run plan for ``range_spec``."""

    commits = parse_commits(repo, range_spec)
    if override_bump and override_bump != "auto":
        bump = override_bump
        bump_source = "override"
    else:
        bump = derive_bump(commits)
        bump_source = "derived"
    next_version = compute_next_version(current_version, bump) if bump else None
    violations = ccc.check_range(str(repo), range_spec)
    draft = build_changelog_draft(commits)
    return Plan(
        range_spec=range_spec,
        current_version=current_version,
        next_version=next_version,
        bump=bump,
        bump_source=bump_source,
        commits=commits,
        violations=violations,
        changelog_draft=draft,
    )


def patch_changelog_with_draft(
    root: pathlib.Path, new_version: str, date: str, draft: str
) -> bool:
    """Replace the placeholder ``- \\n`` bullet ``bump_version`` inserts.

    Returns ``True`` if a substitution happened. ``bump_version`` writes
    a heading ``## <ver> - <date>\\n\\n- \\n\\n`` immediately above the
    previous top entry; we locate that exact block and rewrite the
    single empty bullet line. If the placeholder was already replaced
    (e.g. by a re-run after a manual edit) we leave the file alone.
    """

    path = root / "CHANGELOG.md"
    text = path.read_text(encoding="utf-8")
    placeholder = re.compile(
        r"(##\s+" + re.escape(new_version) + r"\s+-\s+" + re.escape(date) + r"\n\n)- \n",
        re.MULTILINE,
    )
    new_text, n = placeholder.subn(rf"\g<1>{draft}\n", text, count=1)
    if n == 0:
        return False
    path.write_text(new_text, encoding="utf-8")
    return True


def apply_plan(
    *,
    root: pathlib.Path,
    plan: Plan,
    date: str,
    allow_violations: bool,
) -> dict:
    """Execute the bump and CHANGELOG patch. Returns a status dict.

    Refuses on parse violations unless ``allow_violations`` is set, so
    the existing Conventional Commits gate remains the single source of
    truth for "are these commits releasable".

    Never runs ``git tag``, ``git push``, ``git commit``, or
    ``git fetch``. Mutating I/O is limited to the files
    :func:`bump_version.bump` writes plus a single CHANGELOG patch.
    """

    if plan.next_version is None:
        raise SystemExit("nothing to release: no relevant commits in range")
    if plan.violations and not allow_violations:
        raise SystemExit(
            f"refusing to apply: {len(plan.violations)} commit(s) violate "
            "Conventional Commits. Pass --allow-violations to override "
            "(rare; prefer rebasing)."
        )
    # Detect the keepachangelog "## Unreleased" promotion path before
    # bump_version mutates the file, so we can report it accurately.
    changelog_path = root / "CHANGELOG.md"
    pre_text = (
        changelog_path.read_text(encoding="utf-8")
        if changelog_path.is_file()
        else ""
    )
    unreleased_promoted = bool(
        re.search(r"^##\s+Unreleased\s*$", pre_text, re.MULTILINE | re.IGNORECASE)
    )

    changed = bump_version.bump(root, plan.next_version, date)
    if not changed:
        # ``bump_version`` returned ``False`` when current already == next;
        # we treat that as a no-op so re-runs are safe.
        return {
            "applied": False,
            "version": plan.next_version,
            "reason": "already-at-version",
            "changelog_patched": False,
            "unreleased_promoted": False,
        }
    if unreleased_promoted:
        # Unreleased prose became the new release body; do not overwrite
        # human-authored content with the auto-draft.
        patched = False
    else:
        patched = patch_changelog_with_draft(
            root, plan.next_version, date, plan.changelog_draft
        )
    return {
        "applied": True,
        "version": plan.next_version,
        "changelog_patched": patched,
        "unreleased_promoted": unreleased_promoted,
    }


# ---------------------------------------------------------------------------
# CLI rendering.
# ---------------------------------------------------------------------------


def _detect_unreleased(root: pathlib.Path) -> bool:
    """Return True when CHANGELOG.md has a ``## Unreleased`` heading."""

    path = root / "CHANGELOG.md"
    if not path.is_file():
        return False
    return bool(
        re.search(
            r"^##\s+Unreleased\s*$",
            path.read_text(encoding="utf-8"),
            re.MULTILINE | re.IGNORECASE,
        )
    )


def _render_human_plan(
    plan: Plan, *, applied: dict | None = None, unreleased_present: bool = False
) -> str:
    lines: list[str] = []
    lines.append("Release plan")
    lines.append(f"  Repo range:        {plan.range_spec}")
    lines.append(f"  Current version:   {plan.current_version}")
    if plan.next_version:
        lines.append(
            f"  Suggested bump:    {plan.bump} ({plan.bump_source})"
        )
        lines.append(f"  Next version:      {plan.next_version}")
    else:
        lines.append("  Suggested bump:    none (no release-relevant commits)")
    lines.append(f"  Commits in range:  {len(plan.commits)}")
    lines.append(f"  CC violations:     {len(plan.violations)}")
    if unreleased_present:
        lines.append(
            "  CHANGELOG mode:    promote ## Unreleased "
            "(prose preserved; auto-draft NOT applied)"
        )
    else:
        lines.append(
            "  CHANGELOG mode:    insert new heading "
            "(auto-draft replaces empty bullet placeholder)"
        )
    if plan.violations:
        for v in plan.violations:
            lines.append(f"    - {v['sha'][:12]} {v['subject']!r} -> {v['reason']}")
    lines.append("")
    lines.append("Changelog draft:")
    for line in plan.changelog_draft.splitlines():
        lines.append(f"  {line}")
    lines.append("")
    if applied is None:
        lines.append("Mode: dry-run (no files modified, no git mutations).")
        lines.append("Pass --apply to bump version sources and patch CHANGELOG.")
    else:
        if applied["applied"]:
            promoted = applied.get("unreleased_promoted", False)
            tail = (
                " (promoted ## Unreleased section; auto-draft not applied)"
                if promoted
                else f"; CHANGELOG patched={applied['changelog_patched']}"
            )
            lines.append(f"Applied: bumped to {applied['version']}{tail}.")
        else:
            lines.append(
                f"No-op: already at {applied['version']} ({applied.get('reason', '')})."
            )
    if plan.next_version:
        lines.append("")
        lines.append("Next steps (HUMAN-TRIGGERED — this tool will not do them):")
        lines.append(
            f"  1. Review the bumped sources and CHANGELOG draft for {plan.next_version}."
        )
        lines.append(
            f"  2. (optional) Generate a migration skeleton: "
            f"scripts/scaffold-migration.sh {plan.current_version} {plan.next_version} --write"
        )
        lines.append("  3. Commit the bump and CHANGELOG edits.")
        lines.append(
            f"  4. Tag the release commit: git tag -a v{plan.next_version} -m "
            f"'agent-bootstrap-template {plan.next_version}'"
        )
        lines.append(
            "  5. Replace <PENDING> in core/release-tags.md with the tag commit SHA."
        )
        lines.append(
            f"  6. Push the tag: git push origin v{plan.next_version}"
        )
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# CLI entry.
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="release-prepare",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--root",
        default=str(pathlib.Path(__file__).resolve().parents[2]),
        help="Repository root (default: this template's root).",
    )
    parser.add_argument(
        "--from",
        dest="from_ref",
        default=None,
        help=(
            "Range start ref (default: latest tag matching v[0-9]*; "
            "first-parent root commit if no tags exist)."
        ),
    )
    parser.add_argument(
        "--to",
        dest="to_ref",
        default="HEAD",
        help="Range end ref (default: HEAD).",
    )
    parser.add_argument(
        "--bump",
        choices=("auto", "major", "minor", "patch"),
        default="auto",
        help="Override bump derivation (default: auto from commits).",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help=(
            "Run bump_version + patch CHANGELOG. Default is dry-run "
            "(plan only, no writes, no git mutations)."
        ),
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit the plan as JSON (machine-readable).",
    )
    parser.add_argument(
        "--date",
        default=None,
        help="Release date for CHANGELOG (default: today UTC, ISO format).",
    )
    parser.add_argument(
        "--allow-violations",
        action="store_true",
        help=(
            "Allow --apply even when Conventional Commits violations exist. "
            "Rare; prefer rebasing."
        ),
    )
    args = parser.parse_args(argv)

    root = pathlib.Path(args.root).resolve()
    current_version = _quiet_current_version(root)
    if current_version is None:
        return 1

    if args.from_ref is None:
        tag = latest_release_tag(root)
        if tag is None:
            # Walk back to the root commit. ``--reverse`` ordering makes
            # this an N-pass over the whole history; small repos only.
            args.from_ref = _run_git(
                root, "rev-list", "--max-parents=0", "HEAD"
            ).splitlines()[0].strip()
        else:
            args.from_ref = tag
    range_spec = f"{args.from_ref}..{args.to_ref}"

    plan = prepare_plan(
        repo=root,
        range_spec=range_spec,
        current_version=current_version,
        override_bump=args.bump,
    )

    date = args.date or dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")

    # Capture state BEFORE apply so the rendered plan accurately reports
    # the CHANGELOG mode (Unreleased section is consumed by apply).
    unreleased_present = _detect_unreleased(root)

    applied: dict | None = None
    if args.apply:
        applied = apply_plan(
            root=root,
            plan=plan,
            date=date,
            allow_violations=args.allow_violations,
        )

    if args.json:
        out = plan.to_dict()
        out["applied"] = applied
        out["date"] = date
        out["unreleased_present"] = unreleased_present
        sys.stdout.write(json.dumps(out, indent=2) + "\n")
    else:
        sys.stdout.write(
            _render_human_plan(
                plan, applied=applied, unreleased_present=unreleased_present
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
