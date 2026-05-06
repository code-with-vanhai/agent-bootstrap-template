"""Unit tests for :mod:`scripts.lib.check_conventional_commits`.

Hermetic tests: each test method builds a fresh git repo under a
temporary directory, lays down commits with controlled subjects, and
exercises the checker on a defined range. No reliance on the host
repo's history; no mutating ops.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from scripts.lib import check_conventional_commits as ccc  # noqa: E402


def _git(cwd, *args):
    env = os.environ.copy()
    env.setdefault("GIT_AUTHOR_NAME", "CC Test")
    env.setdefault("GIT_AUTHOR_EMAIL", "cc@test.local")
    env.setdefault("GIT_COMMITTER_NAME", "CC Test")
    env.setdefault("GIT_COMMITTER_EMAIL", "cc@test.local")
    return subprocess.run(
        ["git", "-C", str(cwd), *args],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )


def _commit(repo, subject, body=""):
    Path(repo, "log.txt").write_text(subject + "\n", encoding="utf-8")
    _git(repo, "add", ".")
    msg = subject if not body else f"{subject}\n\n{body}"
    _git(repo, "commit", "-q", "-m", msg)


class CheckSubjectTests(unittest.TestCase):
    """``check_subject`` is pure — exercise the matrix without git."""

    def setUp(self):
        self.subject_re = ccc._build_subject_re(ccc.DEFAULT_TYPES)
        self.max_subject = 100

    def _check(self, subject, parents=1):
        return ccc.check_subject(subject, parents, self.subject_re, self.max_subject)

    def test_simple_feat_passes(self):
        self.assertIsNone(self._check("feat: add new flag"))

    def test_scoped_feat_passes(self):
        self.assertIsNone(self._check("feat(sync): add new flag"))

    def test_breaking_marker_passes(self):
        self.assertIsNone(self._check("feat(sync)!: drop legacy schema"))

    def test_unknown_type_rejected(self):
        reason = self._check("wip: try a thing")
        self.assertIsNotNone(reason)

    def test_missing_colon_rejected(self):
        reason = self._check("feat add new flag")
        self.assertIsNotNone(reason)

    def test_missing_space_after_colon_rejected(self):
        reason = self._check("feat:add new flag")
        self.assertIsNotNone(reason)

    def test_empty_description_rejected(self):
        # Regex requires \S after ': ', so this is rejected by the
        # mismatch path. ``check_subject`` returns the regex error
        # message rather than the empty-description message; either
        # is acceptable for the contract — assert it FAILS.
        self.assertIsNotNone(self._check("feat: "))

    def test_long_subject_rejected(self):
        subject = "feat: " + ("x" * 200)
        reason = self._check(subject)
        self.assertIsNotNone(reason)
        self.assertIn("longer than", reason)

    def test_merge_commit_exempt(self):
        self.assertIsNone(
            self._check("Merge pull request #42 from foo/bar", parents=2)
        )

    def test_merge_subject_with_one_parent_rejected(self):
        # A commit that only LOOKS like a merge but has a single parent
        # is still author-controlled and must follow the spec.
        self.assertIsNotNone(self._check("Merge: stuff", parents=1))

    def test_revert_subject_exempt(self):
        self.assertIsNone(
            self._check('Revert "feat: bad thing"', parents=1)
        )

    def test_lowercased_type_required(self):
        # The conventional-commits grammar is lowercase-only on the
        # type token; uppercase ``Feat:`` should fail.
        self.assertIsNotNone(self._check("Feat: shouted change"))


class CheckRangeTests(unittest.TestCase):
    """End-to-end checker over a synthetic git history."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self._tmp.name) / "r"
        self.repo.mkdir()
        _git(self.repo, "init", "-q", "-b", "main")
        # Need an initial commit so HEAD~ is resolvable.
        _commit(self.repo, "chore: init")

    def tearDown(self):
        self._tmp.cleanup()

    def test_clean_range_returns_no_failures(self):
        _commit(self.repo, "feat: alpha")
        _commit(self.repo, "fix(scope): beta")
        _commit(self.repo, "docs: gamma")
        failures = ccc.check_range(str(self.repo), "HEAD~3..HEAD")
        self.assertEqual(failures, [])

    def test_dirty_range_reports_each_violator(self):
        _commit(self.repo, "feat: ok one")
        _commit(self.repo, "wip: bad subject")
        _commit(self.repo, "feat: ok two")
        _commit(self.repo, "Bad subject without type")
        failures = ccc.check_range(str(self.repo), "HEAD~4..HEAD")
        subjects = sorted(f["subject"] for f in failures)
        self.assertEqual(
            subjects,
            ["Bad subject without type", "wip: bad subject"],
        )
        for f in failures:
            self.assertTrue(len(f["sha"]) >= 7)
            self.assertTrue(f["reason"])

    def test_merge_commit_does_not_fail(self):
        # Build a side branch and merge it back. The repo already has
        # ``chore: init`` from setUp(), so after this block the
        # first-parent chain is init -> base -> merge (3 deep), and
        # the side branch contributes one extra commit reachable
        # only via the merge's second parent.
        _commit(self.repo, "feat: base")
        _git(self.repo, "checkout", "-q", "-b", "side")
        _commit(self.repo, "feat: side change")
        _git(self.repo, "checkout", "-q", "main")
        _git(self.repo, "merge", "--no-ff", "-q", "side", "-m", "Merge branch 'side'")
        # ``HEAD~2..HEAD`` excludes ``chore: init`` and includes
        # ``feat: base``, ``feat: side change``, and the merge
        # commit. All three must pass: two are valid feats, the
        # third is a merge subject and is exempt.
        failures = ccc.check_range(str(self.repo), "HEAD~2..HEAD")
        self.assertEqual(failures, [], failures)

    def test_main_returns_zero_on_clean_range(self):
        _commit(self.repo, "feat: alpha")
        rc = ccc.main(["--repo", str(self.repo), "--range", "HEAD~1..HEAD"])
        self.assertEqual(rc, 0)

    def test_main_returns_nonzero_on_dirty_range(self):
        _commit(self.repo, "wip: bad")
        rc = ccc.main(["--repo", str(self.repo), "--range", "HEAD~1..HEAD"])
        self.assertEqual(rc, 1)

    def test_main_allow_empty(self):
        # Empty range — same ref both sides yields no commits.
        rc = ccc.main(
            [
                "--repo",
                str(self.repo),
                "--range",
                "HEAD..HEAD",
                "--allow-empty",
            ]
        )
        self.assertEqual(rc, 0)

    def test_main_empty_range_without_allow_empty_fails(self):
        rc = ccc.main(
            [
                "--repo",
                str(self.repo),
                "--range",
                "HEAD..HEAD",
            ]
        )
        self.assertEqual(rc, 2)


if __name__ == "__main__":
    unittest.main()
