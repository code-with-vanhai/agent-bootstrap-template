"""Tests for scripts/lib/gate_modes.py."""

from __future__ import annotations

import json
import pathlib
import tempfile
import unittest

from scripts.lib import gate_modes


class LoadGateModesTemplateTests(unittest.TestCase):
    def _write_manifest(self, root: pathlib.Path, payload: dict) -> None:
        core = root / "core"
        core.mkdir(parents=True, exist_ok=True)
        (core / "gate-modes.json").write_text(
            json.dumps(payload), encoding="utf-8"
        )

    def test_happy_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            self._write_manifest(
                root,
                {
                    "schema_version": 1,
                    "modes": ["fast", "full"],
                    "default_gate": "fast",
                    "full_gate": "full",
                },
            )
            modes = gate_modes.load_gate_modes(root, mode="template")
            self.assertEqual(modes, ("fast", "full"))

    def test_template_missing_manifest_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            with self.assertRaises(gate_modes.GateModesError):
                gate_modes.load_gate_modes(root, mode="template")

    def test_rejects_bad_schema_version(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            self._write_manifest(
                root,
                {
                    "schema_version": 3,
                    "modes": ["fast", "full"],
                    "default_gate": "fast",
                    "full_gate": "full",
                },
            )
            with self.assertRaises(gate_modes.GateModesError):
                gate_modes.load_gate_modes(root, mode="template")

    def test_rejects_default_gate_not_in_modes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            self._write_manifest(
                root,
                {
                    "schema_version": 1,
                    "modes": ["fast", "full"],
                    "default_gate": "missing",
                    "full_gate": "full",
                },
            )
            with self.assertRaises(gate_modes.GateModesError):
                gate_modes.load_gate_modes(root, mode="template")

    def test_rejects_duplicate_modes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            self._write_manifest(
                root,
                {
                    "schema_version": 1,
                    "modes": ["fast", "fast"],
                    "default_gate": "fast",
                    "full_gate": "fast",
                },
            )
            with self.assertRaises(gate_modes.GateModesError):
                gate_modes.load_gate_modes(root, mode="template")


class LoadGateModesGeneratedTests(unittest.TestCase):
    def test_generated_falls_back_to_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            modes = gate_modes.load_gate_modes(root, mode="generated")
            self.assertEqual(modes, gate_modes.DEFAULT_GATE_MODES)

    def test_generated_honors_present_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            (root / ".agent").mkdir()
            (root / ".agent" / "gate-modes.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "modes": ["fast", "release"],
                        "default_gate": "fast",
                        "full_gate": "release",
                    }
                ),
                encoding="utf-8",
            )
            modes = gate_modes.load_gate_modes(root, mode="generated")
            self.assertEqual(modes, ("fast", "release"))


class LoadGateModesSchemaV2Tests(unittest.TestCase):
    def _write_manifest(self, root: pathlib.Path, payload: dict) -> pathlib.Path:
        agent = root / ".agent"
        agent.mkdir(parents=True, exist_ok=True)
        path = agent / "gate-modes.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def base_payload(self) -> dict:
        return {
            "schema_version": 2,
            "modes": ["fast", "frontend", "backend", "full"],
            "default_gate": "fast",
            "full_gate": "full",
        }

    def test_v2_without_composites_behaves_like_v1(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            self._write_manifest(root, self.base_payload())

            self.assertEqual(
                gate_modes.load_gate_modes(root, mode="generated"),
                ("fast", "frontend", "backend", "full"),
            )
            self.assertIsNone(gate_modes.load_composite_gates(root, mode="generated"))

    def test_v2_valid_composite_gates_load(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            payload = self.base_payload()
            payload["composite_gates"] = {
                "full": {
                    "stages": [
                        {"parallel": ["frontend", "backend"]},
                        {"serial": ["fast"]},
                    ]
                }
            }
            self._write_manifest(root, payload)

            composites = gate_modes.load_composite_gates(root, mode="generated")
            self.assertIsNotNone(composites)
            assert composites is not None
            self.assertIn("full", composites)

    def assert_invalid_composite(self, composite_gates: object) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            payload = self.base_payload()
            payload["composite_gates"] = composite_gates
            self._write_manifest(root, payload)
            with self.assertRaises(gate_modes.GateModesError):
                gate_modes.load_gate_modes(root, mode="generated")

    def test_rejects_unknown_mode_reference(self) -> None:
        self.assert_invalid_composite(
            {"full": {"stages": [{"parallel": ["missing"]}]}}
        )

    def test_rejects_self_reference(self) -> None:
        self.assert_invalid_composite(
            {"full": {"stages": [{"serial": ["full"]}]}}
        )

    def test_rejects_composite_to_composite_reference(self) -> None:
        self.assert_invalid_composite(
            {
                "full": {"stages": [{"parallel": ["frontend"]}]},
                "fast": {"stages": [{"serial": ["full"]}]},
            }
        )

    def test_rejects_empty_stages(self) -> None:
        self.assert_invalid_composite({"full": {"stages": []}})

    def test_rejects_unknown_stage_key(self) -> None:
        self.assert_invalid_composite(
            {"full": {"stages": [{"parallel": ["fast"], "after": ["backend"]}]}}
        )

    def test_rejects_stage_with_neither_parallel_nor_serial(self) -> None:
        self.assert_invalid_composite({"full": {"stages": [{"name": "bad"}]}})

    def test_rejects_v1_with_composite_block(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            payload = self.base_payload()
            payload["schema_version"] = 1
            payload["composite_gates"] = {
                "full": {"stages": [{"parallel": ["fast"]}]}
            }
            self._write_manifest(root, payload)

            with self.assertRaises(gate_modes.GateModesError):
                gate_modes.load_gate_modes(root, mode="generated")


class TemplateRepoConsistencyTests(unittest.TestCase):
    def test_repo_manifest_matches_default(self) -> None:
        # Sanity: the checked-in manifest in this repo must agree with the
        # compatibility fallback so generated 0.9.0 repos do not see a
        # mismatched mode set when migrating later.
        repo_root = pathlib.Path(__file__).resolve().parents[2]
        modes = gate_modes.load_gate_modes(repo_root, mode="template")
        self.assertEqual(modes, gate_modes.DEFAULT_GATE_MODES)


class ValidatorDriftTests(unittest.TestCase):
    """End-to-end drift checks via validate_agent_system."""

    def test_validator_fails_when_schema_enum_diverges(self) -> None:
        import shutil
        from scripts.lib import validate_agent_system

        repo_root = pathlib.Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as tmp:
            target = pathlib.Path(tmp) / "repo"
            shutil.copytree(repo_root, target, symlinks=True, ignore=shutil.ignore_patterns(".git"))
            schema = target / "core" / "manifest.schema.json"
            text = schema.read_text(encoding="utf-8")
            mutated = text.replace('"release"', '"release_mutated"', 1)
            self.assertNotEqual(text, mutated)
            schema.write_text(mutated, encoding="utf-8")

            validator = validate_agent_system.AgentSystemValidator(
                target, mode="template"
            )
            validator.validate_gate_modes_manifest_template()
            statuses = [check.status for check in validator.results]
            self.assertIn("FAIL", statuses)


class GeneratedGateModesValidationTests(unittest.TestCase):
    """Generated mode must distinguish absent (skip) from malformed (fail)."""

    def _validator(self, root: pathlib.Path):
        from scripts.lib import validate_agent_system

        return validate_agent_system.AgentSystemValidator(root, mode="generated")

    def test_absent_manifest_skips(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            (root / ".agent").mkdir()
            validator = self._validator(root)
            validator.validate_gate_modes_manifest_generated()
            statuses = [check.status for check in validator.results]
            self.assertIn("SKIP", statuses)
            self.assertNotIn("FAIL", statuses)

    def test_malformed_manifest_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            (root / ".agent").mkdir()
            (root / ".agent" / "gate-modes.json").write_text(
                json.dumps(
                    {
                        "schema_version": 3,
                        "modes": ["fast", "full"],
                        "default_gate": "fast",
                        "full_gate": "full",
                    }
                ),
                encoding="utf-8",
            )
            validator = self._validator(root)
            validator.validate_gate_modes_manifest_generated()
            statuses = [check.status for check in validator.results]
            self.assertIn("FAIL", statuses)
            messages = "\n".join(check.message for check in validator.results)
            self.assertIn("present but invalid", messages)

    def test_well_formed_manifest_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            (root / ".agent").mkdir()
            (root / ".agent" / "gate-modes.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "modes": ["fast", "full"],
                        "default_gate": "fast",
                        "full_gate": "full",
                    }
                ),
                encoding="utf-8",
            )
            validator = self._validator(root)
            validator.validate_gate_modes_manifest_generated()
            statuses = [check.status for check in validator.results]
            self.assertIn("PASS", statuses)
            self.assertNotIn("FAIL", statuses)


if __name__ == "__main__":
    unittest.main()
