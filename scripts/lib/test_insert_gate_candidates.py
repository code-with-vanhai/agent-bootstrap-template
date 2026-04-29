"""Tests for scripts/lib/insert_gate_candidates.py."""

from __future__ import annotations

import json
import re
import shutil
import tempfile
import unittest
from pathlib import Path

from scripts.lib.insert_gate_candidates import (
    EXPECTED_GATE_MODES,
    insert,
    marker_close,
    marker_open,
)


ROOT = Path(__file__).resolve().parents[2]
TEMPLATE_EVAL = ROOT / "scripts" / "agent-eval.template.sh"


def _gate_block(text: str, gate: str) -> str:
    open_m = marker_open(gate)
    close_m = marker_close(gate)
    pattern = re.compile(
        rf"{re.escape(open_m)}\n(.*?)[^\n]*{re.escape(close_m)}",
        re.DOTALL,
    )
    match = pattern.search(text)
    if not match:
        raise AssertionError(f"missing markers for gate={gate} in eval text")
    return match.group(1).rstrip("\n")


def _make_target(test: unittest.TestCase) -> Path:
    target = Path(tempfile.mkdtemp(prefix="agent-insert-gate-"))
    test.addCleanup(lambda: shutil.rmtree(target, ignore_errors=True))
    (target / "scripts").mkdir(parents=True)
    shutil.copy(TEMPLATE_EVAL, target / "scripts" / "agent-eval.sh")
    return target


class InsertGateCandidatesTest(unittest.TestCase):
    def test_empty_target_keeps_markers_with_empty_bodies(self):
        target = _make_target(self)
        counts = insert(target)
        self.assertEqual(counts, {gate: 0 for gate in EXPECTED_GATE_MODES})

        text = (target / "scripts" / "agent-eval.sh").read_text(encoding="utf-8")
        for gate in EXPECTED_GATE_MODES:
            block = _gate_block(text, gate)
            self.assertEqual(block, "", f"gate={gate} body should be empty, got: {block!r}")
            self.assertIn(marker_open(gate), text)
            self.assertIn(marker_close(gate), text)

    def test_node_fixture_populates_fast_block_with_evidence(self):
        target = _make_target(self)
        (target / "package.json").write_text(
            json.dumps(
                {
                    "scripts": {
                        "test": "vitest run",
                        "typecheck": "tsc --noEmit",
                        "lint": "eslint .",
                    }
                }
            ),
            encoding="utf-8",
        )

        counts = insert(target)
        text = (target / "scripts" / "agent-eval.sh").read_text(encoding="utf-8")

        self.assertGreaterEqual(counts["fast"], 2)
        self.assertEqual(counts["shared"], 1)
        self.assertEqual(counts["security"], 0)

        fast_body = _gate_block(text, "fast")
        for command in ("npm run test", "npm run lint"):
            self.assertIn(f"#   run {command}", fast_body)
        self.assertIn("#   run npm run typecheck", _gate_block(text, "shared"))
        self.assertRegex(fast_body, r"# source: package\.json::scripts\.test \(confidence=high\)")

    def test_python_fixture_populates_fast_and_security_blocks(self):
        target = _make_target(self)
        (target / "pyproject.toml").write_text(
            "[tool.pytest.ini_options]\ntestpaths = ['tests']\n"
            "[tool.bandit]\ntargets = ['src']\n",
            encoding="utf-8",
        )

        counts = insert(target)
        text = (target / "scripts" / "agent-eval.sh").read_text(encoding="utf-8")

        self.assertEqual(counts["fast"], 1)
        self.assertEqual(counts["security"], 1)

        self.assertIn("#   run python -m pytest", _gate_block(text, "fast"))
        self.assertIn("#   run python -m bandit -r .", _gate_block(text, "security"))

    def test_idempotent_rerun_byte_identical(self):
        target = _make_target(self)
        (target / "package.json").write_text(
            json.dumps({"scripts": {"test": "node --test"}}),
            encoding="utf-8",
        )

        insert(target)
        first = (target / "scripts" / "agent-eval.sh").read_text(encoding="utf-8")

        insert(target)
        second = (target / "scripts" / "agent-eval.sh").read_text(encoding="utf-8")

        self.assertEqual(first, second)

    def test_missing_open_marker_raises_systemexit(self):
        target = _make_target(self)
        eval_path = target / "scripts" / "agent-eval.sh"
        text = eval_path.read_text(encoding="utf-8")
        text = text.replace(marker_open("fast"), "# (open marker removed)")
        eval_path.write_text(text, encoding="utf-8")

        with self.assertRaises(SystemExit) as ctx:
            insert(target)
        message = str(ctx.exception.code)
        self.assertIn("missing open marker for gate=fast", message)

    def test_missing_close_marker_raises_systemexit(self):
        target = _make_target(self)
        eval_path = target / "scripts" / "agent-eval.sh"
        text = eval_path.read_text(encoding="utf-8")
        text = text.replace(marker_close("full"), "# (close marker removed)")
        eval_path.write_text(text, encoding="utf-8")

        with self.assertRaises(SystemExit) as ctx:
            insert(target)
        message = str(ctx.exception.code)
        self.assertIn("missing or misplaced close marker for gate=full", message)

    def test_runtime_default_remains_not_configured_after_insert(self):
        target = _make_target(self)
        (target / "package.json").write_text(
            json.dumps({"scripts": {"test": "node --test"}}),
            encoding="utf-8",
        )

        insert(target)
        text = (target / "scripts" / "agent-eval.sh").read_text(encoding="utf-8")

        for gate in EXPECTED_GATE_MODES:
            if gate == "security":
                continue
            arm_pattern = re.compile(
                rf"^\s*{re.escape(gate)}\)\n.*?not_configured",
                re.DOTALL | re.MULTILINE,
            )
            self.assertRegex(text, arm_pattern, f"gate={gate} lost not_configured fallback")


if __name__ == "__main__":
    unittest.main()
