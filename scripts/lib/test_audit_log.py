"""Tests for scripts/lib/audit_log.py."""

from __future__ import annotations

import contextlib
import io
import json
import os
import shutil
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path

from . import audit_log


ROOT = Path(__file__).resolve().parents[2]


class AuditLogTest(unittest.TestCase):
    def make_root(self, *, with_agent: bool = True) -> Path:
        root = Path(tempfile.mkdtemp(prefix="agent-audit-log-"))
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))
        if with_agent:
            (root / ".agent").mkdir()
        return root

    def read_lines(self, root: Path) -> list[dict]:
        log_path = root / ".agent" / "audit-log.jsonl"
        return [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]

    def test_audit_log_appends_schema_v1(self):
        root = self.make_root()
        rc = audit_log.append(
            {
                "kind": "gate_run",
                "actor": "scripts/agent-eval.sh",
                "gate": "fast",
                "exit_code": 2,
                "duration_ms": 10,
            },
            root=root,
        )

        self.assertEqual(rc, 0)
        [record] = self.read_lines(root)
        self.assertEqual(record["v"], 1)
        self.assertRegex(record["ts"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
        self.assertEqual(record["kind"], "gate_run")
        self.assertEqual(record["gate"], "fast")
        self.assertEqual(record["exit_code"], 2)
        self.assertEqual(record["duration_ms"], 10)

    def test_audit_log_missing_agent_dir_noop(self):
        root = self.make_root(with_agent=False)
        rc = audit_log.append(
            {
                "kind": "gate_run",
                "actor": "scripts/agent-eval.sh",
                "gate": "fast",
                "exit_code": 2,
                "duration_ms": 10,
            },
            root=root,
        )

        self.assertEqual(rc, 0)
        self.assertFalse((root / ".agent").exists())

    def test_audit_log_disabled_sentinel(self):
        root = self.make_root()
        (root / ".agent" / "audit-log.disabled").write_text("disabled\n", encoding="utf-8")
        payload = {
            "kind": "gate_run",
            "actor": "scripts/agent-eval.sh",
            "gate": "fast",
            "exit_code": 2,
            "duration_ms": 10,
        }

        self.assertEqual(audit_log.append(payload, root=root), 0)
        self.assertFalse((root / ".agent" / "audit-log.jsonl").exists())

        (root / ".agent" / "audit-log.disabled").unlink()
        self.assertEqual(audit_log.append(payload, root=root), 0)
        self.assertEqual(len(self.read_lines(root)), 1)

    def test_audit_log_invalid_payload_warns_default_strict_fails(self):
        root = self.make_root()
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            default_rc = audit_log.main(["append", "--kind", "gate_run", "--actor", "scripts/agent-eval.sh"])
        self.assertEqual(default_rc, 0)
        self.assertIn("audit-log: warning:", stderr.getvalue())

        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            strict_rc = audit_log.main(
                ["append", "--kind", "gate_run", "--actor", "scripts/agent-eval.sh", "--strict"]
            )
        self.assertEqual(strict_rc, 2)
        self.assertIn("audit-log: warning:", stderr.getvalue())
        self.assertFalse((root / ".agent" / "audit-log.jsonl").exists())

    def test_writer_failure_does_not_alter_caller_exit(self):
        wrapper_root = Path(tempfile.mkdtemp(prefix="agent-audit-wrapper-"))
        self.addCleanup(lambda: shutil.rmtree(wrapper_root, ignore_errors=True))
        scripts_dir = wrapper_root / "scripts"
        lib_dir = scripts_dir / "lib"
        bin_dir = wrapper_root / "bin"
        lib_dir.mkdir(parents=True)
        bin_dir.mkdir()
        shutil.copy2(ROOT / "scripts" / "agent-audit-log.sh", scripts_dir / "agent-audit-log.sh")
        shutil.copy2(ROOT / "scripts" / "lib" / "audit_log.py", lib_dir / "audit_log.py")
        os.chmod(scripts_dir / "agent-audit-log.sh", 0o755)
        (bin_dir / "python3").write_text("#!/usr/bin/env bash\nexit 23\n", encoding="utf-8")
        os.chmod(bin_dir / "python3", 0o755)

        result = subprocess.run(
            [
                "bash",
                str(scripts_dir / "agent-audit-log.sh"),
                "--kind",
                "gate_run",
                "--actor",
                "scripts/agent-eval.sh",
                "--field",
                "gate=fast",
                "--field",
                "exit_code=2",
                "--field",
                "duration_ms=10",
            ],
            env={**os.environ, "PATH": f"{bin_dir}:{os.environ.get('PATH', '')}"},
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self.assertEqual(result.returncode, 0)

    def test_concurrent_appends_atomic(self):
        root = self.make_root()

        def write_one(index: int) -> None:
            audit_log.append(
                {
                    "kind": "gate_run",
                    "actor": "scripts/agent-eval.sh",
                    "gate": f"fast-{index}",
                    "exit_code": index % 3,
                    "duration_ms": index,
                },
                root=root,
            )

        threads = [threading.Thread(target=write_one, args=(index,)) for index in range(30)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        lines = (root / ".agent" / "audit-log.jsonl").read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 30)
        records = [json.loads(line) for line in lines]
        self.assertEqual({record["gate"] for record in records}, {f"fast-{index}" for index in range(30)})

    def test_audit_log_plan_validation_payload(self):
        root = self.make_root()
        rc = audit_log.append(
            {
                "kind": "plan_validation",
                "actor": "scripts/agent-validate-plan.sh",
                "target": "docs/plans/example",
                "exit_code": 1,
                "strict": True,
                "high": 1,
                "medium": 2,
            },
            root=root,
        )
        self.assertEqual(rc, 0)
        [record] = self.read_lines(root)
        self.assertEqual(record["kind"], "plan_validation")
        self.assertEqual(record["high"], 1)
        self.assertEqual(record["medium"], 2)

        rc = audit_log.append(
            {
                "kind": "plan_validation",
                "actor": "scripts/agent-validate-plan.sh",
                "target": "docs/plans/example",
                "exit_code": 1,
                "strict": True,
            },
            root=root,
        )
        self.assertEqual(rc, 0)
        record = self.read_lines(root)[1]
        self.assertNotIn("high", record)
        self.assertNotIn("medium", record)

    def test_gate_run_accepts_sub_gates(self):
        root = self.make_root()
        rc = audit_log.append(
            {
                "kind": "gate_run",
                "actor": "scripts/lib/gate_runner.py",
                "gate": "full",
                "exit_code": 0,
                "duration_ms": 12,
                "sub_gates": [
                    {"gate": "frontend", "exit_code": 0, "duration_ms": 3},
                    {"gate": "backend", "exit_code": 0, "duration_ms": 4},
                ],
            },
            root=root,
        )

        self.assertEqual(rc, 0)
        [record] = self.read_lines(root)
        self.assertEqual(record["sub_gates"][0]["gate"], "frontend")

    def test_gate_run_rejects_bad_sub_gates_shape_in_strict_mode(self):
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            rc = audit_log.main(
                [
                    "append",
                    "--kind",
                    "gate_run",
                    "--actor",
                    "scripts/lib/gate_runner.py",
                    "--field",
                    "gate=full",
                    "--field",
                    "exit_code=1",
                    "--field",
                    "duration_ms=10",
                    "--field",
                    'sub_gates=[{"gate":"fast","exit_code":"bad","duration_ms":1}]',
                    "--strict",
                ]
            )
        self.assertEqual(rc, 2)
        self.assertIn("sub_gates[0].exit_code", stderr.getvalue())

    def test_audit_log_empty_payload_warns(self):
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            rc = audit_log.main(["append", "--kind", "gate_run", "--actor", "scripts/agent-eval.sh", "--field", "badfield"])
        self.assertEqual(rc, 0)
        self.assertIn("audit-log: warning:", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
