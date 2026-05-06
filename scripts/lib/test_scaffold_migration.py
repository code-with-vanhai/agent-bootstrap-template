"""Unit tests for :mod:`scripts.lib.scaffold_migration`.

Hermetic tests over a synthetic git repo built per-test under
``tempfile.TemporaryDirectory``. The scaffolder is expected to produce
a deterministic schema-v1 skeleton from a tag pair, so the tests
exercise:

  - the pure ``classify_source_path`` mapping table (no git needed);
  - the diff-driven skeleton builder against synthetic ``v<from>`` /
    ``v<to>`` tags that include adds, modifies, deletes, and renames;
  - the CLI ``--write`` / ``--force`` invariants (refuses to clobber
    an existing migration without ``--force``);
  - the missing-tag error path matches the canonical "try git fetch
    --tags" runner hint so authors get the same UX everywhere.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from scripts.lib import scaffold_migration  # noqa: E402


def _run(cwd, *args, check=True, env=None):
    proc = subprocess.run(
        list(args),
        cwd=str(cwd),
        check=check,
        capture_output=True,
        text=True,
        env=env,
    )
    return proc


def _git(cwd, *args, env=None):
    base_env = os.environ.copy()
    # Make commits deterministic and avoid leaking the user's identity.
    base_env.setdefault("GIT_AUTHOR_NAME", "Scaffold Test")
    base_env.setdefault("GIT_AUTHOR_EMAIL", "scaffold@test.local")
    base_env.setdefault("GIT_COMMITTER_NAME", "Scaffold Test")
    base_env.setdefault("GIT_COMMITTER_EMAIL", "scaffold@test.local")
    if env:
        base_env.update(env)
    return _run(cwd, "git", *args, env=base_env)


def _write(repo, rel, body):
    path = Path(repo) / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def _init_synthetic_repo(tmp):
    repo = Path(tmp) / "tpl"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    return repo


class ClassifySourcePathTests(unittest.TestCase):
    """``classify_source_path`` is a pure function — exercise the table.

    Tuple shape: ``(kind, source, target, review, extras)``.
    """

    def test_commands_auto_maps_under_agent_commands(self):
        self.assertEqual(
            scaffold_migration.classify_source_path("core/commands/plan.md"),
            (
                "emit",
                "core/commands/plan.md",
                ".agent/commands/plan.md",
                False,
                {},
            ),
        )

    def test_workflows_auto_maps_under_agent_workflows(self):
        self.assertEqual(
            scaffold_migration.classify_source_path(
                "core/workflows/feature-workflow.md"
            ),
            (
                "emit",
                "core/workflows/feature-workflow.md",
                ".agent/workflows/feature-workflow.md",
                False,
                {},
            ),
        )

    def test_roles_nested_path_preserved(self):
        self.assertEqual(
            scaffold_migration.classify_source_path(
                "core/roles/prompts/planner-subagent.md"
            ),
            (
                "emit",
                "core/roles/prompts/planner-subagent.md",
                ".agent/roles/prompts/planner-subagent.md",
                False,
                {},
            ),
        )

    def test_template_suffix_stripped_for_top_level(self):
        self.assertEqual(
            scaffold_migration.classify_source_path("core/constitution.template.md"),
            (
                "emit",
                "core/constitution.template.md",
                ".agent/constitution.md",
                False,
                {},
            ),
        )

    def test_hooks_template_suffix_kept_under_hooks_prefix(self):
        self.assertEqual(
            scaffold_migration.classify_source_path(
                "core/hooks/pre-tool-use-secret-guard.py.template"
            ),
            (
                "emit",
                "core/hooks/pre-tool-use-secret-guard.py.template",
                ".agent/hooks/pre-tool-use-secret-guard.py.template",
                False,
                {},
            ),
        )

    def test_migrations_dir_skipped(self):
        self.assertEqual(
            scaffold_migration.classify_source_path(
                "core/migrations/0.7.0/migration.json"
            ),
            ("skip", "core/migrations/0.7.0/migration.json", None, False, {}),
        )

    def test_release_process_skipped(self):
        self.assertEqual(
            scaffold_migration.classify_source_path("core/release-process.md"),
            ("skip", "core/release-process.md", None, False, {}),
        )

    def test_manifest_schema_skipped(self):
        self.assertEqual(
            scaffold_migration.classify_source_path("core/manifest.schema.json"),
            ("skip", "core/manifest.schema.json", None, False, {}),
        )

    def test_unknown_path_under_core_flagged_for_review(self):
        self.assertEqual(
            scaffold_migration.classify_source_path("core/some-new-tree/thing.md"),
            (
                "emit",
                "core/some-new-tree/thing.md",
                "core/some-new-tree/thing.md",
                True,
                {},
            ),
        )

    def test_scripts_syncs_verbatim(self):
        self.assertEqual(
            scaffold_migration.classify_source_path(
                "scripts/lib/validate_plan.py"
            ),
            (
                "emit",
                "scripts/lib/validate_plan.py",
                "scripts/lib/validate_plan.py",
                False,
                {},
            ),
        )

    def test_adapter_claude_maps_with_skip_missing(self):
        kind, src, tgt, review, extras = scaffold_migration.classify_source_path(
            "adapters/CLAUDE.md"
        )
        self.assertEqual(kind, "emit")
        self.assertEqual(src, "adapters/CLAUDE.md")
        self.assertEqual(tgt, "CLAUDE.md")
        self.assertFalse(review)
        self.assertTrue(extras["skip_if_target_missing"])

    def test_unknown_adapter_path_review(self):
        self.assertEqual(
            scaffold_migration.classify_source_path("adapters/unknown-tool.md"),
            (
                "emit",
                "adapters/unknown-tool.md",
                "adapters/unknown-tool.md",
                True,
                {},
            ),
        )

    def test_non_core_non_adapter_review(self):
        self.assertEqual(
            scaffold_migration.classify_source_path("bin/agent-bootstrap"),
            ("emit", "bin/agent-bootstrap", "bin/agent-bootstrap", True, {}),
        )


class IsTemplateTestFileTests(unittest.TestCase):
    """Pin the ``scripts/**/test_*.py`` heuristic that drives the
    default-on test-exclusion policy. Must be conservative: only
    Python test modules under ``scripts/`` qualify so a real test-
    suite tweak (e.g. ``scripts/lib/validate_plan.py``) is never
    silently dropped.
    """

    def test_scripts_lib_test_module_is_test(self):
        self.assertTrue(
            scaffold_migration.is_template_test_file(
                "scripts/lib/test_validate_plan.py"
            )
        )

    def test_scripts_nested_test_module_is_test(self):
        self.assertTrue(
            scaffold_migration.is_template_test_file(
                "scripts/lib/agent_sync/test_merge.py"
            )
        )

    def test_production_module_under_scripts_is_not_test(self):
        self.assertFalse(
            scaffold_migration.is_template_test_file(
                "scripts/lib/validate_plan.py"
            )
        )

    def test_test_file_outside_scripts_is_not_test(self):
        # ``tests/lib/test_*.py`` lives in a different scaffold scope
        # (and outside the scaffolder's diff pathspec entirely); the
        # filter must not touch it.
        self.assertFalse(
            scaffold_migration.is_template_test_file(
                "tests/lib/test_tracked_files.py"
            )
        )

    def test_non_python_test_file_is_not_test(self):
        # Bash test scripts under scripts/ would also be exotic but the
        # filter is intentionally Python-only — bash test scripts have
        # historically shipped (none currently, but the bar is set
        # narrow on purpose).
        self.assertFalse(
            scaffold_migration.is_template_test_file(
                "scripts/lib/test_runner.sh"
            )
        )

    def test_test_underscore_python_only(self):
        # Filename must start with ``test_`` AND end with ``.py``.
        self.assertFalse(
            scaffold_migration.is_template_test_file("scripts/lib/test.py")
        )
        self.assertFalse(
            scaffold_migration.is_template_test_file(
                "scripts/lib/test_data.json"
            )
        )


class BuildSkeletonTests(unittest.TestCase):
    """End-to-end skeleton build over a synthetic tag pair."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = _init_synthetic_repo(self._tmp.name)

        # v0.1.0 baseline: a few core/ files.
        _write(self.repo, "core/commands/plan.md", "# plan v1\n")
        _write(self.repo, "core/workflows/feature-workflow.md", "# fw v1\n")
        _write(self.repo, "core/roles/planner.md", "# planner v1\n")
        _write(self.repo, "scripts/lib/tool.py", "# tool v1\n")
        _write(self.repo, "core/migrations/README.md", "# template-only\n")
        _write(self.repo, "core/release-process.md", "# template-only docs\n")
        _write(self.repo, "core/old-tree/legacy.md", "# legacy\n")
        _git(self.repo, "add", ".")
        _git(self.repo, "commit", "-q", "-m", "v0.1.0")
        _git(self.repo, "tag", "-a", "v0.1.0", "-m", "v0.1.0")

        # v0.2.0:
        #   - modify plan.md
        #   - add a new command
        #   - add a new workflow file
        #   - delete the legacy old-tree file
        #   - rename roles/planner.md -> roles/planner-v2.md
        #   - bump release-process.md (must be skipped)
        _write(self.repo, "core/commands/plan.md", "# plan v2\n")
        _write(self.repo, "core/commands/review.md", "# review new\n")
        _write(
            self.repo,
            "core/workflows/security-review-workflow.md",
            "# security review\n",
        )
        (self.repo / "core/old-tree/legacy.md").unlink()
        (self.repo / "core/old-tree").rmdir()
        # Rename via add-then-remove + git mv to keep diff renamed.
        _git(self.repo, "mv", "core/roles/planner.md", "core/roles/planner-v2.md")
        _write(self.repo, "core/roles/planner-v2.md", "# planner v2\n")
        _write(self.repo, "core/release-process.md", "# template-only docs v2\n")
        _write(self.repo, "scripts/lib/tool.py", "# tool v2\n")
        _write(self.repo, "CHANGELOG.md", "## 0.2.0 synthetic\n")
        _git(self.repo, "add", "-A")
        _git(self.repo, "commit", "-q", "-m", "v0.2.0")
        _git(self.repo, "tag", "-a", "v0.2.0", "-m", "v0.2.0")

    def tearDown(self):
        self._tmp.cleanup()

    def test_skeleton_metadata_pinned_to_to_version(self):
        skeleton, _report = scaffold_migration.build_skeleton(
            self.repo, "0.1.0", "0.2.0"
        )
        self.assertEqual(skeleton["schema_version"], 1)
        self.assertEqual(skeleton["version"], "0.2.0")
        self.assertEqual(skeleton["to"], "0.2.0")
        self.assertEqual(skeleton["from_versions"], ["0.1.0"])
        # Stage 3.4 default note placeholder is a literal that the
        # release author MUST replace; assert the marker is present so
        # CI / reviewer can grep for stale skeletons.
        self.assertIn(
            "scaffolded skeleton",
            skeleton["manifest_updates"]["append_to_array_unique"]["notes"],
        )

    def test_added_and_modified_paths_listed_in_safe_overwrite(self):
        skeleton, _ = scaffold_migration.build_skeleton(
            self.repo, "0.1.0", "0.2.0"
        )
        targets = {entry["target"] for entry in skeleton["safe_overwrite"]}
        sources = {entry["source"] for entry in skeleton["safe_overwrite"]}
        self.assertIn("scripts/lib/tool.py", sources)
        self.assertIn("scripts/lib/tool.py", targets)
        self.assertIn(".agent/commands/plan.md", targets)
        self.assertIn(".agent/commands/review.md", targets)
        self.assertIn(".agent/workflows/security-review-workflow.md", targets)
        self.assertIn(".agent/roles/planner-v2.md", targets)
        # Skipped paths must not leak into safe_overwrite.
        for entry in skeleton["safe_overwrite"]:
            self.assertFalse(
                entry["source"].startswith("core/migrations/"),
                entry,
            )
            self.assertNotEqual(entry["source"], "core/release-process.md")

    def test_rename_emits_tracked_files_remove_for_old_target(self):
        skeleton, _ = scaffold_migration.build_skeleton(
            self.repo, "0.1.0", "0.2.0"
        )
        removes = skeleton["manifest_updates"].get("tracked_files_remove", [])
        self.assertIn(".agent/roles/planner.md", removes)
        # Removal directive must implicitly enable the writer so the
        # Stage 3.3 ``apply_tracked_files_remove`` path runs.
        self.assertTrue(
            skeleton["manifest_updates"].get("update_tracked_files") is True
        )

    def test_pure_delete_emits_tracked_files_remove_only(self):
        skeleton, report = scaffold_migration.build_skeleton(
            self.repo, "0.1.0", "0.2.0"
        )
        removes = skeleton["manifest_updates"].get("tracked_files_remove", [])
        # The legacy file lives outside the auto-map prefixes, so it
        # is emitted verbatim and surfaces in the review report.
        self.assertIn("core/old-tree/legacy.md", removes)
        self.assertIn("removed: core/old-tree/legacy.md", report["review_required"])

    def test_skipped_paths_reported(self):
        _, report = scaffold_migration.build_skeleton(self.repo, "0.1.0", "0.2.0")
        self.assertIn("core/release-process.md", report["skipped"])

    def test_outside_scaffold_lists_repo_root_changes(self):
        _, report = scaffold_migration.build_skeleton(self.repo, "0.1.0", "0.2.0")
        self.assertIn("CHANGELOG.md", report["outside_scaffold"])

    def test_post_1_0_hop_defaults_update_tracked_files_on(self):
        # Build a fresh repo whose tags straddle 1.0.0 to exercise the
        # Stage 3.3 default-on rule for post-1.0 hops.
        with tempfile.TemporaryDirectory() as tmp:
            repo = _init_synthetic_repo(tmp)
            _write(repo, "core/commands/a.md", "# a\n")
            _git(repo, "add", ".")
            _git(repo, "commit", "-q", "-m", "v1.0.0")
            _git(repo, "tag", "-a", "v1.0.0", "-m", "v1.0.0")
            _write(repo, "core/commands/a.md", "# a v2\n")
            _git(repo, "commit", "-aq", "-m", "v1.0.1")
            _git(repo, "tag", "-a", "v1.0.1", "-m", "v1.0.1")

            skeleton, _ = scaffold_migration.build_skeleton(repo, "1.0.0", "1.0.1")
            self.assertTrue(
                skeleton["manifest_updates"]["update_tracked_files"] is True
            )

    def test_pre_1_0_hop_keeps_update_tracked_files_off_by_default(self):
        skeleton, _ = scaffold_migration.build_skeleton(
            self.repo, "0.1.0", "0.2.0"
        )
        # The synthetic 0.1.0 -> 0.2.0 hop has a rename which forces
        # the writer on (it is required for the removal directive).
        # That is the documented coupling. Confirm it's the rename,
        # not the version, that flipped the bit.
        self.assertTrue(
            skeleton["manifest_updates"]["update_tracked_files"] is True
        )
        self.assertIn(
            "tracked_files_remove",
            skeleton["manifest_updates"],
        )

    def test_pre_1_0_hop_with_no_renames_keeps_update_tracked_files_off(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = _init_synthetic_repo(tmp)
            _write(repo, "core/commands/a.md", "# a\n")
            _git(repo, "add", ".")
            _git(repo, "commit", "-q", "-m", "v0.1.0")
            _git(repo, "tag", "-a", "v0.1.0", "-m", "v0.1.0")
            _write(repo, "core/commands/a.md", "# a v2\n")
            _git(repo, "commit", "-aq", "-m", "v0.2.0")
            _git(repo, "tag", "-a", "v0.2.0", "-m", "v0.2.0")

            skeleton, _ = scaffold_migration.build_skeleton(repo, "0.1.0", "0.2.0")
            self.assertNotIn(
                "update_tracked_files",
                skeleton["manifest_updates"],
            )


class TestExclusionPolicyTests(unittest.TestCase):
    """End-to-end coverage for the default-on test-exclusion policy.

    Two contracts are pinned:

    1. **Default skeleton omits ``scripts/**/test_*.py``.** A diff that
       touches both ``scripts/lib/<prod>.py`` and
       ``scripts/lib/test_<prod>.py`` MUST land only the production
       module under ``safe_overwrite``. The test module is reported as
       skipped so the release author still sees the change.
    2. **``include_tests=True`` opts back in.** Same diff with the
       opt-in flag puts the test module back in ``safe_overwrite``
       verbatim (``source == target``) and removes it from the skipped
       report.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = _init_synthetic_repo(self._tmp.name)

        _write(self.repo, "scripts/lib/validate_plan.py", "# vp v1\n")
        _write(self.repo, "scripts/lib/test_validate_plan.py", "# tvp v1\n")
        _git(self.repo, "add", ".")
        _git(self.repo, "commit", "-q", "-m", "v0.6.0")
        _git(self.repo, "tag", "-a", "v0.6.0", "-m", "v0.6.0")

        _write(self.repo, "scripts/lib/validate_plan.py", "# vp v2\n")
        _write(self.repo, "scripts/lib/test_validate_plan.py", "# tvp v2\n")
        _git(self.repo, "commit", "-aq", "-m", "v0.7.0")
        _git(self.repo, "tag", "-a", "v0.7.0", "-m", "v0.7.0")

    def tearDown(self):
        self._tmp.cleanup()

    def test_default_omits_test_files(self):
        skeleton, report = scaffold_migration.build_skeleton(
            self.repo, "0.6.0", "0.7.0"
        )
        sources = {entry["source"] for entry in skeleton["safe_overwrite"]}
        self.assertIn("scripts/lib/validate_plan.py", sources)
        self.assertNotIn("scripts/lib/test_validate_plan.py", sources)
        self.assertIn("scripts/lib/test_validate_plan.py", report["skipped"])

    def test_include_tests_opts_back_in(self):
        skeleton, report = scaffold_migration.build_skeleton(
            self.repo, "0.6.0", "0.7.0", include_tests=True
        )
        sources = {entry["source"] for entry in skeleton["safe_overwrite"]}
        self.assertIn("scripts/lib/validate_plan.py", sources)
        self.assertIn("scripts/lib/test_validate_plan.py", sources)
        # When opted in, the test-filter must NOT have surfaced the
        # test module under skipped — it is a normal emit row instead.
        self.assertNotIn(
            "scripts/lib/test_validate_plan.py", report["skipped"]
        )

    def test_renamed_test_file_is_filtered_default(self):
        # Synthesize a rename of a test file under scripts/ between
        # the existing v0.7.0 and a new v0.8.0 tag and confirm the
        # default-off filter drops both ends from safe_overwrite and
        # tracked_files_remove.
        _git(
            self.repo,
            "mv",
            "scripts/lib/test_validate_plan.py",
            "scripts/lib/test_validate_plan_v2.py",
        )
        _git(self.repo, "commit", "-q", "-m", "v0.8.0")
        _git(self.repo, "tag", "-a", "v0.8.0", "-m", "v0.8.0")

        skeleton, report = scaffold_migration.build_skeleton(
            self.repo, "0.7.0", "0.8.0"
        )
        sources = {entry["source"] for entry in skeleton["safe_overwrite"]}
        self.assertNotIn("scripts/lib/test_validate_plan.py", sources)
        self.assertNotIn("scripts/lib/test_validate_plan_v2.py", sources)
        # Test files must NOT appear as a tracked_files_remove key —
        # they were never tracked so there is nothing to forget.
        removes = skeleton["manifest_updates"].get("tracked_files_remove", [])
        self.assertNotIn("scripts/lib/test_validate_plan.py", removes)
        self.assertIn("scripts/lib/test_validate_plan.py", report["skipped"])
        self.assertIn(
            "scripts/lib/test_validate_plan_v2.py", report["skipped"]
        )

    def test_deleted_test_file_is_filtered_default(self):
        (self.repo / "scripts/lib/test_validate_plan.py").unlink()
        _git(self.repo, "commit", "-aq", "-m", "v0.9.0")
        _git(self.repo, "tag", "-a", "v0.9.0", "-m", "v0.9.0")

        skeleton, report = scaffold_migration.build_skeleton(
            self.repo, "0.7.0", "0.9.0"
        )
        removes = skeleton["manifest_updates"].get("tracked_files_remove", [])
        self.assertNotIn("scripts/lib/test_validate_plan.py", removes)
        self.assertIn(
            "scripts/lib/test_validate_plan.py", report["skipped"]
        )


class CliInvariantsTests(unittest.TestCase):
    """CLI-level invariants — refusing to clobber, missing-tag UX."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = _init_synthetic_repo(self._tmp.name)
        _write(self.repo, "core/commands/a.md", "# a\n")
        _git(self.repo, "add", ".")
        _git(self.repo, "commit", "-q", "-m", "v0.1.0")
        _git(self.repo, "tag", "-a", "v0.1.0", "-m", "v0.1.0")
        _write(self.repo, "core/commands/a.md", "# a v2\n")
        _git(self.repo, "commit", "-aq", "-m", "v0.2.0")
        _git(self.repo, "tag", "-a", "v0.2.0", "-m", "v0.2.0")

    def tearDown(self):
        self._tmp.cleanup()

    def test_write_creates_skeleton_file(self):
        rc = scaffold_migration.main(
            [
                "0.1.0",
                "0.2.0",
                "--template-root",
                str(self.repo),
                "--write",
            ]
        )
        self.assertEqual(rc, 0)
        path = self.repo / "core" / "migrations" / "0.2.0" / "migration.json"
        self.assertTrue(path.is_file())
        skeleton = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(skeleton["to"], "0.2.0")

    def test_write_refuses_to_clobber_without_force(self):
        target = self.repo / "core" / "migrations" / "0.2.0" / "migration.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("hand-edited\n", encoding="utf-8")

        with self.assertRaises(SystemExit) as exc:
            scaffold_migration.main(
                [
                    "0.1.0",
                    "0.2.0",
                    "--template-root",
                    str(self.repo),
                    "--write",
                ]
            )
        self.assertIn("refusing to overwrite", str(exc.exception))
        # File contents must be untouched.
        self.assertEqual(target.read_text(encoding="utf-8"), "hand-edited\n")

    def test_write_force_overwrites(self):
        target = self.repo / "core" / "migrations" / "0.2.0" / "migration.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("hand-edited\n", encoding="utf-8")

        rc = scaffold_migration.main(
            [
                "0.1.0",
                "0.2.0",
                "--template-root",
                str(self.repo),
                "--write",
                "--force",
            ]
        )
        self.assertEqual(rc, 0)
        body = target.read_text(encoding="utf-8")
        self.assertNotEqual(body, "hand-edited\n")
        self.assertIn('"schema_version": 1', body)

    def test_missing_tag_uses_canonical_runner_hint(self):
        with self.assertRaises(SystemExit) as exc:
            scaffold_migration.build_skeleton(self.repo, "0.1.0", "9.9.9")
        msg = str(exc.exception)
        self.assertIn("requires tag v9.9.9", msg)
        self.assertIn("git fetch --tags", msg)

    def test_invalid_version_rejected(self):
        with self.assertRaises(SystemExit) as exc:
            scaffold_migration.build_skeleton(self.repo, "v0.1.0", "0.2.0")
        self.assertIn("invalid <from>", str(exc.exception))

    def test_same_from_and_to_rejected(self):
        with self.assertRaises(SystemExit) as exc:
            scaffold_migration.build_skeleton(self.repo, "0.1.0", "0.1.0")
        self.assertIn("must differ", str(exc.exception))

    def test_cli_include_tests_flag_threaded_to_builder(self):
        # Build an isolated fixture whose only between-tag delta is a
        # ``scripts/lib/test_helper.py`` add — the cleanest way to pin
        # the CLI flag's wire-up without disturbing the shared
        # ``self.repo`` fixture used by other CliInvariantsTests cases.
        with tempfile.TemporaryDirectory() as tmp:
            repo = _init_synthetic_repo(tmp)
            _write(repo, "scripts/lib/validate_plan.py", "# vp v1\n")
            _git(repo, "add", ".")
            _git(repo, "commit", "-q", "-m", "v0.1.0")
            _git(repo, "tag", "-a", "v0.1.0", "-m", "v0.1.0")

            _write(repo, "scripts/lib/validate_plan.py", "# vp v2\n")
            _write(repo, "scripts/lib/test_helper.py", "# th v1\n")
            _git(repo, "add", ".")
            _git(repo, "commit", "-q", "-m", "v0.2.0")
            _git(repo, "tag", "-a", "v0.2.0", "-m", "v0.2.0")

            target = repo / "core" / "migrations" / "0.2.0" / "migration.json"

            rc = scaffold_migration.main(
                [
                    "0.1.0",
                    "0.2.0",
                    "--template-root",
                    str(repo),
                    "--write",
                ]
            )
            self.assertEqual(rc, 0)
            body_default = target.read_text(encoding="utf-8")
            self.assertNotIn("scripts/lib/test_helper.py", body_default)
            self.assertIn("scripts/lib/validate_plan.py", body_default)

            target.unlink()
            rc = scaffold_migration.main(
                [
                    "0.1.0",
                    "0.2.0",
                    "--template-root",
                    str(repo),
                    "--write",
                    "--include-tests",
                ]
            )
            self.assertEqual(rc, 0)
            body_with_tests = target.read_text(encoding="utf-8")
            self.assertIn("scripts/lib/test_helper.py", body_with_tests)
            self.assertIn("scripts/lib/validate_plan.py", body_with_tests)


if __name__ == "__main__":
    unittest.main()
