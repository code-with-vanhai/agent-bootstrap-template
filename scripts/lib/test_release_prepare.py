"""Unit tests for :mod:`scripts.lib.release_prepare`.

Hermetic tests: each test method that needs git history builds a fresh
repo under :func:`tempfile.TemporaryDirectory`. The pure helpers
(:func:`parse_subject`, :func:`derive_bump`,
:func:`compute_next_version`, :func:`build_changelog_draft`) are
exercised without any git side effects so they are fast and stable.

Stage 3.4 invariants asserted by these tests:

  - Default mode is dry-run (no writes, no git mutations). The CLI
    smoke test asserts the target repo is byte-identical before/after
    the dry-run plan.
  - ``--apply`` calls :func:`bump_version.bump` and patches the new
    CHANGELOG entry; it never invokes ``git tag``, ``git push``,
    ``git commit``, or ``git fetch``.
  - The Conventional Commits gate is the single source of truth for
    "are these commits releasable": ``--apply`` refuses on parse
    violations unless ``--allow-violations`` is set.
"""

from __future__ import annotations

import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[2]
LIB = REPO_ROOT / "scripts" / "lib"
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(LIB))

from scripts.lib import release_prepare as rp  # noqa: E402


def _git(cwd, *args):
    env = os.environ.copy()
    env.setdefault("GIT_AUTHOR_NAME", "RP Test")
    env.setdefault("GIT_AUTHOR_EMAIL", "rp@test.local")
    env.setdefault("GIT_COMMITTER_NAME", "RP Test")
    env.setdefault("GIT_COMMITTER_EMAIL", "rp@test.local")
    return subprocess.run(
        ["git", "-C", str(cwd), *args],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )


def _commit(repo, subject, body=""):
    Path(repo, "log.txt").write_text(subject + "\n" + body, encoding="utf-8")
    _git(repo, "add", ".")
    msg = subject if not body else f"{subject}\n\n{body}"
    _git(repo, "commit", "-q", "-m", msg)


# ---------------------------------------------------------------------------
# Pure helpers.
# ---------------------------------------------------------------------------


class ParseSubjectTests(unittest.TestCase):
    def test_simple_feat(self):
        p = rp.parse_subject("feat: hello")
        self.assertTrue(p.ok)
        self.assertEqual(p.type, "feat")
        self.assertIsNone(p.scope)
        self.assertFalse(p.breaking)
        self.assertEqual(p.description, "hello")

    def test_scoped_fix(self):
        p = rp.parse_subject("fix(sync): repair walker")
        self.assertTrue(p.ok)
        self.assertEqual(p.type, "fix")
        self.assertEqual(p.scope, "sync")
        self.assertFalse(p.breaking)

    def test_breaking_marker(self):
        p = rp.parse_subject("feat(api)!: drop legacy field")
        self.assertTrue(p.ok)
        self.assertTrue(p.breaking)

    def test_invalid_subject(self):
        p = rp.parse_subject("wip: nope")
        self.assertFalse(p.ok)
        self.assertIsNone(p.type)


class CommitIsBreakingTests(unittest.TestCase):
    def _commit(self, subject, body=""):
        return rp.Commit(sha="x" * 40, parents=1, subject=subject, body=body)

    def test_subject_marker(self):
        c = self._commit("feat!: drop")
        p = rp.parse_subject(c.subject)
        self.assertTrue(rp.commit_is_breaking(c, p))

    def test_body_trailer(self):
        c = self._commit("feat: ok", body="BREAKING CHANGE: drop foo")
        p = rp.parse_subject(c.subject)
        self.assertTrue(rp.commit_is_breaking(c, p))

    def test_body_dashed_trailer(self):
        c = self._commit("feat: ok", body="BREAKING-CHANGE: drop foo")
        p = rp.parse_subject(c.subject)
        self.assertTrue(rp.commit_is_breaking(c, p))

    def test_body_prose_mention_does_not_trip(self):
        c = self._commit(
            "feat: ok",
            body="This is not a trailer: BREAKING CHANGE: should be ignored.",
        )
        p = rp.parse_subject(c.subject)
        self.assertFalse(rp.commit_is_breaking(c, p))

    def test_clean_commit(self):
        c = self._commit("feat: ok")
        p = rp.parse_subject(c.subject)
        self.assertFalse(rp.commit_is_breaking(c, p))


class CommitReleaseRelevanceTests(unittest.TestCase):
    def test_merge_commit_skipped(self):
        c = rp.Commit(
            sha="x" * 40, parents=2, subject="Merge branch x", body=""
        )
        p = rp.parse_subject(c.subject)
        self.assertFalse(rp.commit_is_release_relevant(c, p))

    def test_revert_subject_skipped(self):
        c = rp.Commit(
            sha="x" * 40, parents=1, subject='Revert "feat: bad"', body=""
        )
        p = rp.parse_subject(c.subject)
        self.assertFalse(rp.commit_is_release_relevant(c, p))

    def test_normal_feat_relevant(self):
        c = rp.Commit(sha="x" * 40, parents=1, subject="feat: ok", body="")
        p = rp.parse_subject(c.subject)
        self.assertTrue(rp.commit_is_release_relevant(c, p))


class DeriveBumpTests(unittest.TestCase):
    @staticmethod
    def _c(subject, body="", parents=1):
        return rp.Commit(sha="x" * 40, parents=parents, subject=subject, body=body)

    def test_no_relevant_commits(self):
        # Only a merge — release-irrelevant.
        commits = [self._c("Merge branch x", parents=2)]
        self.assertIsNone(rp.derive_bump(commits))

    def test_only_fix_is_patch(self):
        commits = [self._c("fix: a"), self._c("docs: b"), self._c("chore: c")]
        self.assertEqual(rp.derive_bump(commits), "patch")

    def test_feat_is_minor(self):
        commits = [self._c("fix: a"), self._c("feat(scope): b")]
        self.assertEqual(rp.derive_bump(commits), "minor")

    def test_breaking_is_major(self):
        commits = [
            self._c("feat: a"),
            self._c("fix!: b"),
        ]
        self.assertEqual(rp.derive_bump(commits), "major")

    def test_breaking_in_body_is_major(self):
        commits = [self._c("feat: a", body="BREAKING CHANGE: drop x")]
        self.assertEqual(rp.derive_bump(commits), "major")

    def test_violations_still_count_as_relevant_patch(self):
        # A non-conformant subject is "relevant" but does not imply a
        # bigger bump than ``patch``. The violations gate (separate
        # contract) is responsible for refusing the apply.
        commits = [self._c("wip: bad")]
        self.assertEqual(rp.derive_bump(commits), "patch")


class ComputeNextVersionTests(unittest.TestCase):
    def test_patch(self):
        self.assertEqual(rp.compute_next_version("0.11.0", "patch"), "0.11.1")

    def test_minor(self):
        self.assertEqual(rp.compute_next_version("0.11.3", "minor"), "0.12.0")

    def test_major(self):
        self.assertEqual(rp.compute_next_version("0.11.3", "major"), "1.0.0")

    def test_rejects_pre_release_input(self):
        # ``0.11.0-rc.1`` is not flat X.Y.Z; refuse rather than guess.
        # Implementation keeps the rule simple: only pure ``X.Y.Z``
        # inputs are accepted. Pre-releases would change semver math
        # and require extra surface; defer until a real need exists.
        with self.assertRaises(ValueError):
            rp.compute_next_version("0.11.0-rc.1", "patch")

    def test_rejects_bad_bump(self):
        with self.assertRaises(ValueError):
            rp.compute_next_version("0.11.0", "huge")


class BuildChangelogDraftTests(unittest.TestCase):
    @staticmethod
    def _c(subject, body="", short="abcdefg"):
        return rp.Commit(
            sha=short + "0" * (40 - len(short)),
            parents=1,
            subject=subject,
            body=body,
        )

    def test_groups_by_type(self):
        commits = [
            self._c("feat: alpha", short="aaaaaaa"),
            self._c("fix(scope): beta", short="bbbbbbb"),
            self._c("docs: gamma", short="ccccccc"),
            self._c("chore: delta", short="ddddddd"),
        ]
        draft = rp.build_changelog_draft(commits)
        # Features must come before Fixes per _TYPE_PRIORITY.
        self.assertLess(draft.index("**Features**"), draft.index("**Fixes**"))
        self.assertIn("feat: alpha (aaaaaaa)", draft)
        self.assertIn("fix(scope): beta (bbbbbbb)", draft)
        self.assertIn("**Docs**", draft)
        self.assertIn("**Chores**", draft)

    def test_breaking_marker_preserved(self):
        commits = [self._c("feat!: drop legacy", short="1234567")]
        draft = rp.build_changelog_draft(commits)
        self.assertIn("feat!: drop legacy (1234567)", draft)

    def test_violations_routed_to_other(self):
        commits = [self._c("wip: bad", short="9999999")]
        draft = rp.build_changelog_draft(commits)
        self.assertIn("**Other**", draft)
        self.assertIn("wip: bad (9999999)", draft)

    def test_merge_and_revert_skipped(self):
        merge = rp.Commit(
            sha="m" * 40, parents=2, subject="Merge branch x", body=""
        )
        revert = rp.Commit(
            sha="r" * 40, parents=1, subject='Revert "feat: bad"', body=""
        )
        feat = rp.Commit(
            sha="f" * 40, parents=1, subject="feat: ok", body=""
        )
        draft = rp.build_changelog_draft([merge, revert, feat])
        self.assertIn("**Features**", draft)
        self.assertNotIn("Merge branch", draft)
        self.assertNotIn("Revert", draft)

    def test_empty_input(self):
        self.assertIn("no release-relevant commits", rp.build_changelog_draft([]))


# ---------------------------------------------------------------------------
# CHANGELOG patcher.
# ---------------------------------------------------------------------------


class PatchChangelogTests(unittest.TestCase):
    def test_replaces_placeholder(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "CHANGELOG.md").write_text(
                "# Changelog\n\n## 0.12.0 - 2026-05-06\n\n- \n\n"
                "## 0.11.0 - 2026-05-04\n\n- old entry\n",
                encoding="utf-8",
            )
            ok = rp.patch_changelog_with_draft(
                root, "0.12.0", "2026-05-06", "- **Features**\n  - feat: x"
            )
            self.assertTrue(ok)
            text = (root / "CHANGELOG.md").read_text(encoding="utf-8")
            self.assertIn("- **Features**", text)
            self.assertIn("  - feat: x", text)
            # Old entry preserved verbatim.
            self.assertIn("## 0.11.0 - 2026-05-04", text)
            self.assertIn("- old entry", text)

    def test_idempotent_when_already_patched(self):
        # Re-running patch on a CHANGELOG that no longer has the
        # placeholder must not silently corrupt the file.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            content = (
                "# Changelog\n\n## 0.12.0 - 2026-05-06\n\n"
                "- **Features**\n  - feat: x\n\n## 0.11.0 - 2026-05-04\n\n- old\n"
            )
            (root / "CHANGELOG.md").write_text(content, encoding="utf-8")
            ok = rp.patch_changelog_with_draft(
                root, "0.12.0", "2026-05-06", "- something else"
            )
            self.assertFalse(ok)
            self.assertEqual(
                (root / "CHANGELOG.md").read_text(encoding="utf-8"), content
            )


# ---------------------------------------------------------------------------
# End-to-end CLI / apply.
# ---------------------------------------------------------------------------


class _Fixture:
    """Builds a hermetic git repo with the five version sources + tag."""

    def __init__(self, root: Path, version: str = "1.0.0"):
        self.root = root
        self.version = version
        (root / "scripts").mkdir(parents=True)
        (root / "scripts" / "bootstrap-request.sh").write_text(
            f'#!/usr/bin/env bash\ntemplate_version="{version}"\n',
            encoding="utf-8",
        )
        (root / ".claude-plugin").mkdir(parents=True)
        (root / ".claude-plugin" / "plugin.json").write_text(
            json.dumps({"version": version}), encoding="utf-8"
        )
        (root / ".claude-plugin" / "marketplace.json").write_text(
            json.dumps(
                {
                    "metadata": {"version": version},
                    "plugins": [
                        {"name": "agent-bootstrap", "version": version},
                    ],
                }
            ),
            encoding="utf-8",
        )
        (root / "CHANGELOG.md").write_text(
            f"# Changelog\n\n## {version} - 2026-01-01\n\n- entry\n",
            encoding="utf-8",
        )
        (root / "core").mkdir()
        # Borrow real release-tags.md so semver-row insertion has a base.
        shutil.copyfile(
            REPO_ROOT / "core" / "release-tags.md",
            root / "core" / "release-tags.md",
        )
        _git(root, "init", "-q", "-b", "main")
        _git(root, "add", ".")
        _git(root, "commit", "-q", "-m", f"chore: init at {version}")
        # Tag the initial commit so latest_release_tag() finds it.
        _git(root, "tag", "-a", f"v{version}", "-m", f"v{version}")


class CliDryRunTests(unittest.TestCase):
    def test_dry_run_does_not_mutate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _Fixture(root, version="1.0.0")
            _commit(root, "feat: alpha")
            _commit(root, "fix(scope): beta")

            before = subprocess.run(
                ["git", "-C", str(root), "status", "--porcelain"],
                capture_output=True,
                text=True,
                check=True,
            ).stdout
            head_before = subprocess.run(
                ["git", "-C", str(root), "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
                check=True,
            ).stdout

            buf = io.StringIO()
            with mock.patch("sys.stdout", buf):
                rc = rp.main(["--root", str(root)])
            self.assertEqual(rc, 0)
            output = buf.getvalue()
            self.assertIn("Suggested bump:    minor", output)
            self.assertIn("Next version:      1.1.0", output)
            self.assertIn("dry-run", output)

            after = subprocess.run(
                ["git", "-C", str(root), "status", "--porcelain"],
                capture_output=True,
                text=True,
                check=True,
            ).stdout
            head_after = subprocess.run(
                ["git", "-C", str(root), "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
                check=True,
            ).stdout
            self.assertEqual(before, after)
            self.assertEqual(head_before, head_after)

    def test_json_emits_machine_readable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _Fixture(root, version="1.0.0")
            _commit(root, "feat: alpha")

            buf = io.StringIO()
            with mock.patch("sys.stdout", buf):
                rc = rp.main(["--root", str(root), "--json"])
            self.assertEqual(rc, 0)
            data = json.loads(buf.getvalue())
            self.assertEqual(data["next_version"], "1.1.0")
            self.assertEqual(data["bump"], "minor")
            self.assertEqual(len(data["commits"]), 1)
            self.assertEqual(data["violations"], [])
            self.assertIsNone(data["applied"])

    def test_bump_override(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _Fixture(root, version="1.0.0")
            _commit(root, "fix: only fix")

            buf = io.StringIO()
            with mock.patch("sys.stdout", buf):
                rc = rp.main(["--root", str(root), "--bump", "major", "--json"])
            self.assertEqual(rc, 0)
            data = json.loads(buf.getvalue())
            self.assertEqual(data["bump"], "major")
            self.assertEqual(data["bump_source"], "override")
            self.assertEqual(data["next_version"], "2.0.0")


class CliApplyTests(unittest.TestCase):
    def test_apply_bumps_and_patches_changelog(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _Fixture(root, version="1.0.0")
            _commit(root, "feat: alpha")
            _commit(root, "fix(scope): beta")
            head_before = subprocess.run(
                ["git", "-C", str(root), "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
                check=True,
            ).stdout
            tags_before = subprocess.run(
                ["git", "-C", str(root), "tag", "--list"],
                capture_output=True,
                text=True,
                check=True,
            ).stdout

            buf = io.StringIO()
            with mock.patch("sys.stdout", buf):
                rc = rp.main(
                    [
                        "--root",
                        str(root),
                        "--apply",
                        "--date",
                        "2026-05-06",
                    ]
                )
            self.assertEqual(rc, 0)

            # Version sources updated.
            text = (root / "CHANGELOG.md").read_text(encoding="utf-8")
            self.assertIn("## 1.1.0 - 2026-05-06", text)
            self.assertIn("**Features**", text)
            self.assertIn("feat: alpha", text)
            self.assertIn("fix(scope): beta", text)
            # Empty placeholder is gone.
            self.assertNotIn("\n## 1.1.0 - 2026-05-06\n\n- \n", text)
            self.assertIn(
                '"version": "1.1.0"',
                (root / ".claude-plugin" / "plugin.json").read_text(
                    encoding="utf-8"
                ),
            )
            # No git mutations: HEAD unchanged, no new tags.
            head_after = subprocess.run(
                ["git", "-C", str(root), "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
                check=True,
            ).stdout
            tags_after = subprocess.run(
                ["git", "-C", str(root), "tag", "--list"],
                capture_output=True,
                text=True,
                check=True,
            ).stdout
            self.assertEqual(head_before, head_after)
            self.assertEqual(tags_before, tags_after)

    def test_apply_refuses_on_violations(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _Fixture(root, version="1.0.0")
            _commit(root, "wip: bad subject")

            with self.assertRaises(SystemExit) as ctx:
                with mock.patch("sys.stdout", io.StringIO()):
                    rp.main(["--root", str(root), "--apply"])
            self.assertIn("violate", str(ctx.exception))

            # Sources unchanged.
            self.assertIn(
                '"version": "1.0.0"',
                (root / ".claude-plugin" / "plugin.json").read_text(
                    encoding="utf-8"
                ),
            )

    def test_apply_allow_violations(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _Fixture(root, version="1.0.0")
            _commit(root, "wip: bad subject")

            buf = io.StringIO()
            with mock.patch("sys.stdout", buf):
                rc = rp.main(
                    [
                        "--root",
                        str(root),
                        "--apply",
                        "--allow-violations",
                        "--date",
                        "2026-05-06",
                    ]
                )
            self.assertEqual(rc, 0)
            # Even an out-of-shape commit yields a patch bump (lowest impact).
            self.assertIn(
                '"version": "1.0.1"',
                (root / ".claude-plugin" / "plugin.json").read_text(
                    encoding="utf-8"
                ),
            )

    def test_apply_promotes_unreleased_section(self):
        """When CHANGELOG.md has ``## Unreleased``, --apply promotes it
        to ``## <next> - <date>`` and does NOT overwrite the prose with
        the auto-generated draft.

        Asserts the keepachangelog/semantic-release contract: hand-
        written prose accumulated under Unreleased is preserved as the
        body of the new release; the auto-draft (terse subject lines)
        is only used when no Unreleased section exists.
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _Fixture(root, version="1.0.0")
            # Replace the fixture's CHANGELOG with one that has Unreleased prose.
            (root / "CHANGELOG.md").write_text(
                "# Changelog\n\n"
                "## Unreleased\n\n"
                "- Hand-written prose for the upcoming release.\n"
                "- A second carefully-edited bullet.\n\n"
                "## 1.0.0 - 2026-01-01\n\n- entry\n",
                encoding="utf-8",
            )
            _git(root, "add", "CHANGELOG.md")
            _git(root, "commit", "-q", "-m", "docs: write unreleased prose")
            _commit(root, "feat: alpha")

            buf = io.StringIO()
            with mock.patch("sys.stdout", buf):
                rc = rp.main(
                    [
                        "--root",
                        str(root),
                        "--apply",
                        "--date",
                        "2026-05-06",
                    ]
                )
            self.assertEqual(rc, 0)
            text = (root / "CHANGELOG.md").read_text(encoding="utf-8")
            # Unreleased was promoted, not duplicated.
            self.assertIn("## 1.1.0 - 2026-05-06", text)
            self.assertNotIn("## Unreleased", text)
            self.assertEqual(text.count("## 1.1.0 - 2026-05-06"), 1)
            # Hand-written prose preserved as the new release body.
            self.assertIn("Hand-written prose for the upcoming release.", text)
            self.assertIn("A second carefully-edited bullet.", text)
            # Auto-draft bullet from `feat: alpha` was NOT injected.
            self.assertNotIn("feat: alpha (", text)
            # Reported in human output.
            output = buf.getvalue()
            self.assertIn("promoted ## Unreleased", output)

    def test_apply_promotion_reported_in_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _Fixture(root, version="1.0.0")
            (root / "CHANGELOG.md").write_text(
                "# Changelog\n\n## Unreleased\n\n- prose\n\n"
                "## 1.0.0 - 2026-01-01\n\n- entry\n",
                encoding="utf-8",
            )
            _git(root, "add", "CHANGELOG.md")
            _git(root, "commit", "-q", "-m", "docs: prose")
            _commit(root, "feat: alpha")

            buf = io.StringIO()
            with mock.patch("sys.stdout", buf):
                rc = rp.main(
                    [
                        "--root",
                        str(root),
                        "--apply",
                        "--json",
                        "--date",
                        "2026-05-06",
                    ]
                )
            self.assertEqual(rc, 0)
            # ``bump_version`` triggers ``vercheck.report`` which prints a
            # pretty-table prefix to stdout. Slice from the JSON object
            # that ``release_prepare`` emits at the end.
            output = buf.getvalue()
            # Locate the top-level JSON object (line starting with ``{``).
            lines = output.splitlines(keepends=True)
            json_starts = [
                i for i, ln in enumerate(lines) if ln.rstrip("\n") == "{"
            ]
            self.assertTrue(json_starts, msg=f"no JSON in output: {output!r}")
            data = json.loads("".join(lines[json_starts[0]:]))
            self.assertTrue(data["unreleased_present"])
            self.assertTrue(data["applied"]["unreleased_promoted"])
            self.assertFalse(data["applied"]["changelog_patched"])

    def test_dry_run_reports_unreleased_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _Fixture(root, version="1.0.0")
            (root / "CHANGELOG.md").write_text(
                "# Changelog\n\n## Unreleased\n\n- prose\n\n"
                "## 1.0.0 - 2026-01-01\n\n- entry\n",
                encoding="utf-8",
            )
            _git(root, "add", "CHANGELOG.md")
            _git(root, "commit", "-q", "-m", "docs: prose")
            _commit(root, "feat: alpha")

            buf = io.StringIO()
            with mock.patch("sys.stdout", buf):
                rc = rp.main(["--root", str(root)])
            self.assertEqual(rc, 0)
            output = buf.getvalue()
            self.assertIn("promote ## Unreleased", output)
            self.assertIn("auto-draft NOT applied", output)

    def test_apply_no_relevant_commits_exits_with_message(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _Fixture(root, version="1.0.0")
            # Only a merge-shaped commit (which is irrelevant when its
            # parent count is >=2). A single fake parent count must come
            # from a real merge; instead of forging one, we just don't
            # add any commits past the tag.

            with self.assertRaises(SystemExit) as ctx:
                with mock.patch("sys.stdout", io.StringIO()):
                    rp.main(["--root", str(root), "--apply"])
            self.assertIn("nothing to release", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
