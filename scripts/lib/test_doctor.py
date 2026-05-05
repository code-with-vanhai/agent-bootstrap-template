"""Tests for Stage 2.2 ``doctor`` read-only diagnostics."""

from __future__ import annotations

import contextlib
import io
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts" / "lib"))
from agent_sync.doctor import run_doctor  # noqa: E402


class DoctorTests(unittest.TestCase):
    def test_json_output_has_expected_keys(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = pathlib.Path(tmp) / "t"
            shutil.copytree(REPO_ROOT / "tests/migrations/0.3.0/after", target)
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rc = run_doctor(
                    template_root=REPO_ROOT, target=target, as_json=True
                )
            self.assertEqual(rc, 0)
            doc = json.loads(out.getvalue())
            self.assertEqual(doc["current_version"], "0.3.0")
            self.assertIn("latest_migratable", doc)
            self.assertIn("diagnostic_migration", doc)
            self.assertIn("managed_files", doc)
            self.assertIsInstance(doc["orphans"], list)

    def test_human_output_mentions_current_version(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = pathlib.Path(tmp) / "t"
            shutil.copytree(REPO_ROOT / "tests/migrations/0.3.0/after", target)
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rc = run_doctor(
                    template_root=REPO_ROOT, target=target, as_json=False
                )
            self.assertEqual(rc, 0)
            self.assertIn("0.3.0", out.getvalue())

    def test_doctor_does_not_write_to_target(self) -> None:
        """Plan M1 / D-9 contract: ``doctor`` must be strictly read-only.

        Snapshot ``git status --porcelain`` and ``.agent/manifest.json``
        mtime before and after both the JSON and human-formatted runs;
        any regression that starts writing caches/logs/state under the
        target repo will flip one of these assertions.
        """

        with tempfile.TemporaryDirectory() as tmp:
            target = pathlib.Path(tmp) / "t"
            shutil.copytree(REPO_ROOT / "tests/migrations/0.3.0/after", target)
            subprocess.check_call(
                ["git", "init", "-q", str(target)],
            )
            subprocess.check_call(
                [
                    "git",
                    "-C",
                    str(target),
                    "-c",
                    "user.email=t@t",
                    "-c",
                    "user.name=t",
                    "commit",
                    "--allow-empty",
                    "-q",
                    "-m",
                    "seed",
                ],
            )
            subprocess.check_call(
                ["git", "-C", str(target), "add", "-A"],
            )
            subprocess.check_call(
                [
                    "git",
                    "-C",
                    str(target),
                    "-c",
                    "user.email=t@t",
                    "-c",
                    "user.name=t",
                    "commit",
                    "-q",
                    "-m",
                    "fixture",
                ],
            )

            manifest = target / ".agent" / "manifest.json"
            mtime_before = os.stat(manifest).st_mtime_ns
            status_before = subprocess.check_output(
                ["git", "-C", str(target), "status", "--porcelain"]
            )

            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(
                    run_doctor(
                        template_root=REPO_ROOT, target=target, as_json=True
                    ),
                    0,
                )
                self.assertEqual(
                    run_doctor(
                        template_root=REPO_ROOT, target=target, as_json=False
                    ),
                    0,
                )

            status_after = subprocess.check_output(
                ["git", "-C", str(target), "status", "--porcelain"]
            )
            mtime_after = os.stat(manifest).st_mtime_ns

            self.assertEqual(
                status_before,
                status_after,
                "doctor must not modify the target worktree",
            )
            self.assertEqual(
                mtime_before,
                mtime_after,
                ".agent/manifest.json mtime changed; doctor wrote to it",
            )


    def test_rejects_non_semver_current_version(self) -> None:
        """Plan lines 494-495: doctor must refuse ``bad-version`` manifests.

        Silently reporting ``manifest_ok=true`` on a corrupted
        ``synced_to_template_version`` was the failure mode flagged in
        the Stage 1+2 review — downstream fields (latest migratable,
        hops-behind, managed-file scan) become meaningless without this
        guard.
        """

        from agent_sync.errors import UsageError  # noqa: WPS433

        with tempfile.TemporaryDirectory() as tmp:
            target = pathlib.Path(tmp) / "t"
            shutil.copytree(REPO_ROOT / "tests/migrations/0.3.0/after", target)
            manifest_path = target / ".agent" / "manifest.json"
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
            data["synced_to_template_version"] = "bad-version"
            manifest_path.write_text(json.dumps(data), encoding="utf-8")

            with contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaises(UsageError) as ctx:
                    run_doctor(
                        template_root=REPO_ROOT, target=target, as_json=True
                    )
            self.assertIn("bad-version", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
