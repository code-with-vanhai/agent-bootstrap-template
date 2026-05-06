#!/usr/bin/env python3
"""Unit tests for the Stage 3.2 checksum fast-path in ``merge.py``.

Locks down two contracts:

1. **Tracked + unmodified ⇒ ``v<from>`` is never consulted.** When the
   manifest's ``tracked_files`` map records a checksum that matches the
   on-disk bytes, ``plan_safe_overwrites`` only fetches ``v<to>`` for
   theirs. Neither ``tag_exists(template_root, from)`` nor
   ``git_show(template_root, from, ...)`` may run. This is the AC-6
   guarantee that lets an ephemeral mirror missing ``v<from>`` complete
   the hop.
2. **Tracked + modified ⇒ lazy tag check fires on fall-through.** When
   the on-disk sha differs from the tracked baseline, the fast-path is
   skipped and the entry takes the 3-way merge branch, which performs
   the lazy ``tag_exists`` validation and surfaces the existing
   ``git fetch --tags`` hint when ``v<from>`` is missing.

The tests substitute the module-level ``tag_exists`` / ``git_show`` /
``try_git_show`` helpers so the assertions are exact: a hidden git call
would show up as a missing-mock failure, not a silent shell-out.
"""

from __future__ import annotations

import hashlib
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts" / "lib"))

from agent_sync import merge as merge_module  # noqa: E402
from agent_sync.errors import UsageError  # noqa: E402
from agent_sync.merge import (  # noqa: E402
    REASON_FAST_PATH,
    plan_safe_overwrites,
)


def _sha(data):
    return hashlib.sha256(data).hexdigest()


class _GitStub:
    """Records every call so tests can assert what was (not) fetched."""

    def __init__(self, *, tag_exists=None, git_show=None, try_git_show=None):
        self.tag_exists_calls = []
        self.git_show_calls = []
        self.try_git_show_calls = []
        self._tag_exists = tag_exists or (lambda repo, version: True)
        self._git_show = git_show or (lambda repo, v, p, required=False: None)
        self._try_git_show = try_git_show or (lambda repo, v, p: None)

    def tag_exists(self, repo, version):
        self.tag_exists_calls.append(version)
        return self._tag_exists(repo, version)

    def git_show(self, repo, version, source, required=False):
        self.git_show_calls.append((version, source, required))
        return self._git_show(repo, version, source, required=required)

    def try_git_show(self, repo, version, source):
        self.try_git_show_calls.append((version, source))
        return self._try_git_show(repo, version, source)


class FastPathTests(unittest.TestCase):
    def setUp(self):
        self.tmp = self.enterContext_compat(__import__("tempfile").TemporaryDirectory())
        self.target = Path(self.tmp)
        (self.target / ".agent").mkdir()

        self._original = {
            "tag_exists": merge_module.tag_exists,
            "git_show": merge_module.git_show,
            "try_git_show": merge_module.try_git_show,
        }

    def enterContext_compat(self, ctx):
        # 3.10-compatible analogue of unittest.TestCase.enterContext.
        result = ctx.__enter__()
        self.addCleanup(ctx.__exit__, None, None, None)
        return result

    def tearDown(self):
        merge_module.tag_exists = self._original["tag_exists"]
        merge_module.git_show = self._original["git_show"]
        merge_module.try_git_show = self._original["try_git_show"]

    def _install_stub(self, stub):
        merge_module.tag_exists = stub.tag_exists
        merge_module.git_show = stub.git_show
        merge_module.try_git_show = stub.try_git_show

    def _migration(self):
        return {
            "schema_version": 1,
            "version": "1.0.0",
            "from": "0.11.0",
            "to": "1.0.0",
        }

    def _entry(self, *, source=".agent/rulebase.md", target=".agent/rulebase.md"):
        return {"source": source, "target": target, "kind": "safe_overwrite"}

    def _write_target(self, rel, body):
        path = self.target / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)
        return body

    # --- Fast-path: matched checksum ------------------------------------

    def test_fast_path_skips_v_from_entirely(self):
        ours = self._write_target(".agent/rulebase.md", b"# rulebase v11\n")
        theirs = b"# rulebase v100\n"

        stub = _GitStub(
            tag_exists=lambda repo, v: self.fail(
                f"tag_exists must not be called on fast-path; got v={v}"
            ),
            git_show=lambda repo, v, p, required=False: self.fail(
                f"git_show must not be called on fast-path; got v={v}, p={p}"
            ),
            try_git_show=lambda repo, v, p: theirs if v == "1.0.0" else None,
        )
        self._install_stub(stub)

        tracked = {
            ".agent/rulebase.md": {
                "synced_at_version": "0.11.0",
                "synced_checksum_sha256": _sha(ours),
            }
        }

        writes, updated, accepted = {}, [], []
        plan_safe_overwrites(
            template_root=Path("/nonexistent"),
            target=self.target,
            migration=self._migration(),
            entries=[self._entry()],
            accept_theirs=set(),
            writes=writes,
            updated=updated,
            accepted=accepted,
            tracked_files=tracked,
        )

        self.assertEqual(writes[".agent/rulebase.md"], theirs)
        self.assertEqual(updated, [".agent/rulebase.md"])
        self.assertEqual(len(accepted), 1)
        self.assertEqual(accepted[0].path, ".agent/rulebase.md")
        self.assertEqual(accepted[0].reason, REASON_FAST_PATH)
        self.assertEqual(stub.try_git_show_calls, [("1.0.0", ".agent/rulebase.md")])
        self.assertEqual(stub.tag_exists_calls, [])
        self.assertEqual(stub.git_show_calls, [])

    def test_fast_path_noop_when_theirs_equals_ours(self):
        ours = self._write_target(".agent/rulebase.md", b"# unchanged\n")

        stub = _GitStub(
            try_git_show=lambda repo, v, p: ours,
            tag_exists=lambda repo, v: self.fail("tag_exists must not run"),
            git_show=lambda repo, v, p, required=False: self.fail(
                "git_show must not run"
            ),
        )
        self._install_stub(stub)

        tracked = {
            ".agent/rulebase.md": {
                "synced_at_version": "0.11.0",
                "synced_checksum_sha256": _sha(ours),
            }
        }

        writes, updated, accepted = {}, [], []
        plan_safe_overwrites(
            template_root=Path("/nonexistent"),
            target=self.target,
            migration=self._migration(),
            entries=[self._entry()],
            accept_theirs=set(),
            writes=writes,
            updated=updated,
            accepted=accepted,
            tracked_files=tracked,
        )

        self.assertEqual(writes, {})
        self.assertEqual(updated, [])
        self.assertEqual(accepted, [])

    def test_fast_path_falls_through_when_v_to_missing(self):
        ours = self._write_target(".agent/rulebase.md", b"# unchanged\n")

        stub = _GitStub(
            try_git_show=lambda repo, v, p: None,
            tag_exists=lambda repo, v: False,
            git_show=lambda repo, v, p, required=False: self.fail(
                "git_show must not run before tag_exists rejects"
            ),
        )
        self._install_stub(stub)

        tracked = {
            ".agent/rulebase.md": {
                "synced_at_version": "0.11.0",
                "synced_checksum_sha256": _sha(ours),
            }
        }

        writes, updated, accepted = {}, [], []
        with self.assertRaises(UsageError) as ctx:
            plan_safe_overwrites(
                template_root=Path("/nonexistent"),
                target=self.target,
                migration=self._migration(),
                entries=[self._entry()],
                accept_theirs=set(),
                writes=writes,
                updated=updated,
                accepted=accepted,
                tracked_files=tracked,
            )
        self.assertIn("git fetch --tags", str(ctx.exception))

    # --- Fall-through to 3-way merge ------------------------------------

    def test_modified_file_falls_through_to_three_way_merge(self):
        ours = self._write_target(".agent/rulebase.md", b"# user edit\n")
        base = b"# baseline\n"
        theirs = b"# upgraded\n"

        # Recorded checksum points at the *baseline* bytes; current
        # bytes diverged because user edited the file.
        tracked = {
            ".agent/rulebase.md": {
                "synced_at_version": "0.11.0",
                "synced_checksum_sha256": _sha(base),
            }
        }

        def git_show(repo, v, p, required=False):
            if v == "0.11.0":
                return base
            if v == "1.0.0":
                return theirs
            raise AssertionError(f"unexpected version {v}")

        stub = _GitStub(
            tag_exists=lambda repo, v: True,
            git_show=git_show,
            try_git_show=lambda repo, v, p: self.fail(
                "fast-path must not fire when ours sha differs from tracked"
            ),
        )
        self._install_stub(stub)

        writes, updated, accepted = {}, [], []
        # ours != base AND ours != theirs AND base != ours → conflict
        with self.assertRaises(merge_module.ConflictError):
            plan_safe_overwrites(
                template_root=Path("/nonexistent"),
                target=self.target,
                migration=self._migration(),
                entries=[self._entry()],
                accept_theirs=set(),
                writes=writes,
                updated=updated,
                accepted=accepted,
                tracked_files=tracked,
            )

        # Lazy tag check fires once on the first fall-through.
        self.assertEqual(stub.tag_exists_calls, ["0.11.0", "1.0.0"])
        self.assertEqual(
            stub.git_show_calls,
            [
                ("0.11.0", ".agent/rulebase.md", False),
                ("1.0.0", ".agent/rulebase.md", True),
            ],
        )

    def test_lazy_tag_check_fires_when_v_from_missing_on_three_way(self):
        ours = self._write_target(".agent/rulebase.md", b"# user edit\n")

        # No tracked_files for this path → entry takes 3-way path.
        stub = _GitStub(
            tag_exists=lambda repo, v: v == "1.0.0",  # v<from> missing
            git_show=lambda repo, v, p, required=False: self.fail(
                "git_show must not run after tag_exists rejects"
            ),
        )
        self._install_stub(stub)

        writes, updated, accepted = {}, [], []
        with self.assertRaises(UsageError) as ctx:
            plan_safe_overwrites(
                template_root=Path("/nonexistent"),
                target=self.target,
                migration=self._migration(),
                entries=[self._entry()],
                accept_theirs=set(),
                writes=writes,
                updated=updated,
                accepted=accepted,
                tracked_files={},
            )
        self.assertIn("0.11.0", str(ctx.exception))
        self.assertIn("git fetch --tags", str(ctx.exception))
        self.assertEqual(stub.tag_exists_calls, ["0.11.0"])

    def test_lazy_tag_check_validates_only_once_per_hop(self):
        # Two entries, both fall through to 3-way merge. tag_exists must
        # be called exactly twice (once per version, on the FIRST entry's
        # fall-through), not 2*N times.
        body = b"# placeholder\n"
        self._write_target(".agent/a.md", body)
        self._write_target(".agent/b.md", body)
        theirs = b"# upgraded\n"

        def git_show(repo, v, p, required=False):
            if v == "0.11.0":
                return body
            return theirs

        stub = _GitStub(
            tag_exists=lambda repo, v: True,
            git_show=git_show,
            try_git_show=lambda repo, v, p: None,
        )
        self._install_stub(stub)

        writes, updated, accepted = {}, [], []
        plan_safe_overwrites(
            template_root=Path("/nonexistent"),
            target=self.target,
            migration=self._migration(),
            entries=[
                {"source": ".agent/a.md", "target": ".agent/a.md"},
                {"source": ".agent/b.md", "target": ".agent/b.md"},
            ],
            accept_theirs=set(),
            writes=writes,
            updated=updated,
            accepted=accepted,
            tracked_files={},
        )
        # Both files: ours == base (body) → write theirs.
        self.assertEqual(writes[".agent/a.md"], theirs)
        self.assertEqual(writes[".agent/b.md"], theirs)
        # tag_exists called exactly twice (once per version) across two entries.
        self.assertEqual(stub.tag_exists_calls, ["0.11.0", "1.0.0"])

    def test_absent_tracked_files_preserves_legacy_behavior(self):
        # No tracked_files → identical to pre-Stage-3.2 path. ours == base
        # → write theirs.
        body = b"# baseline\n"
        self._write_target(".agent/rulebase.md", body)
        theirs = b"# upgraded\n"

        def git_show(repo, v, p, required=False):
            if v == "0.11.0":
                return body
            return theirs

        stub = _GitStub(
            tag_exists=lambda repo, v: True,
            git_show=git_show,
            try_git_show=lambda repo, v, p: self.fail(
                "try_git_show must not fire when tracked_files is empty"
            ),
        )
        self._install_stub(stub)

        writes, updated, accepted = {}, [], []
        plan_safe_overwrites(
            template_root=Path("/nonexistent"),
            target=self.target,
            migration=self._migration(),
            entries=[self._entry()],
            accept_theirs=set(),
            writes=writes,
            updated=updated,
            accepted=accepted,
            # tracked_files omitted → defaults to {}
        )
        self.assertEqual(writes[".agent/rulebase.md"], theirs)
        self.assertEqual(accepted, [])  # not a fast-path write


if __name__ == "__main__":
    unittest.main()
