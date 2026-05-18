"""Tests for scripts/lib/gate_runner.py."""

from __future__ import annotations

import contextlib
import io
import json
import os
import shutil
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from scripts.lib import gate_runner


class GateRunnerTests(unittest.TestCase):
    def make_root(self) -> Path:
        root = Path(tempfile.mkdtemp(prefix="gate-runner-"))
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))
        return root

    def write_gate_modes(self, root: Path) -> Path:
        path = root / "gate-modes.json"
        path.write_text(
            json.dumps(
                {
                    "schema_version": 2,
                    "modes": ["fast", "frontend", "backend", "full"],
                    "default_gate": "fast",
                    "full_gate": "full",
                    "composite_gates": {
                        "full": {
                            "stages": [
                                {"parallel": ["frontend", "backend"]},
                                {"serial": ["fast"]},
                            ]
                        }
                    },
                }
            ),
            encoding="utf-8",
        )
        return path

    def test_load_composite_and_cli_detection(self) -> None:
        root = self.make_root()
        path = self.write_gate_modes(root)

        composite = gate_runner.load_composite("full", path)
        self.assertIsNotNone(composite)
        assert composite is not None
        self.assertEqual(composite.name, "full")

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            rc = gate_runner.main(
                ["is-composite", "--gate", "full", "--gate-modes", str(path)]
            )
        self.assertEqual(rc, 0)
        self.assertEqual(stdout.getvalue().strip(), "yes")

    def test_aggregate_exit_codes(self) -> None:
        self.assertEqual(gate_runner.aggregate_exit_codes([0, 0]), 0)
        self.assertEqual(gate_runner.aggregate_exit_codes([0, 2]), 0)
        self.assertEqual(gate_runner.aggregate_exit_codes([2, 2]), 2)
        self.assertEqual(gate_runner.aggregate_exit_codes([1, 2]), 1)
        self.assertEqual(gate_runner.aggregate_exit_codes([1, 3, 2]), 3)

    def test_children_use_popen_with_suppressed_audit(self) -> None:
        root = self.make_root()
        eval_script = root / "agent-eval.sh"
        eval_script.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
        launched: list[tuple[list[str], dict[str, str]]] = []

        class FakePopen:
            def __init__(self, argv, cwd=None, env=None, stdout=None, stderr=None):
                launched.append((list(argv), dict(env or {})))
                self.returncode = 0

            def wait(self, timeout=None):
                return self.returncode

            def poll(self):
                return self.returncode

            def terminate(self):
                self.returncode = -15

            def kill(self):
                self.returncode = -9

        with mock.patch("scripts.lib.gate_runner.subprocess.Popen", FakePopen):
            results = gate_runner.run_stage(
                {"parallel": ("frontend", "backend"), "serial": ("fast",)},
                eval_script,
                root,
            )

        self.assertEqual([result.gate for result in results], ["fast", "frontend", "backend"])
        self.assertEqual(len(launched), 3)
        self.assertTrue(
            all(env.get("AGENT_EVAL_SUPPRESS_AUDIT") == "1" for _, env in launched)
        )
        self.assertTrue(all(argv[0] == "bash" for argv, _ in launched))

    def test_live_child_signal_cleanup_terminates_registered_handles(self) -> None:
        class FakeChild:
            def __init__(self):
                self.terminated = False

            def poll(self):
                return None if not self.terminated else -15

            def terminate(self):
                self.terminated = True

            def wait(self, timeout=None):
                return -15

        child = FakeChild()
        gate_runner._register_child(child)  # type: ignore[arg-type]
        try:
            gate_runner.terminate_live_children()
            self.assertTrue(child.terminated)
        finally:
            gate_runner._unregister_child(child)  # type: ignore[arg-type]

    def test_composite_run_emits_single_audit_event(self) -> None:
        root = self.make_root()
        (root / ".agent").mkdir()
        eval_script = root / "agent-eval.sh"
        eval_script.write_text(
            "#!/usr/bin/env bash\n"
            "printf '%s\\n' \"$1\"\n"
            "exit 0\n",
            encoding="utf-8",
        )
        os.chmod(eval_script, 0o755)
        composite = gate_runner.CompositeGate(
            "full", ({"parallel": ("frontend", "backend")},)
        )

        rc = gate_runner.run_composite(composite, eval_script, root)

        self.assertEqual(rc, 0)
        lines = (root / ".agent" / "audit-log.jsonl").read_text(
            encoding="utf-8"
        ).splitlines()
        self.assertEqual(len(lines), 1)
        record = json.loads(lines[0])
        self.assertEqual(record["kind"], "gate_run")
        self.assertEqual(record["gate"], "full")
        self.assertEqual(len(record["sub_gates"]), 2)
        self.assertTrue(
            all(item["duration_ms"] >= 0 for item in record["sub_gates"])
        )


if __name__ == "__main__":
    unittest.main()
