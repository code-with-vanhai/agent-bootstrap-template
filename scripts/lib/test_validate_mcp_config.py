"""Tests for ``scripts/lib/validate_mcp_config.py``.

The MCP layer is opt-in. These tests cover both the catalog schema check
and the inline-credential linter, plus the no-op behavior when nothing is
present (the default bootstrap case).
"""

from __future__ import annotations

import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "lib" / "validate_mcp_config.py"

sys.path.insert(0, str(REPO_ROOT / "scripts" / "lib"))
import validate_mcp_config as validator  # noqa: E402


class CatalogTests(unittest.TestCase):
    def test_template_catalog_passes(self) -> None:
        catalog = REPO_ROOT / "core" / "mcp" / "catalog.json"
        self.assertTrue(catalog.is_file(), "core/mcp/catalog.json must exist")
        findings = validator.validate_catalog(catalog)
        self.assertEqual(findings, [], msg=[f.message for f in findings])

    def test_catalog_required_fields(self) -> None:
        catalog = json.loads(
            (REPO_ROOT / "core" / "mcp" / "catalog.json").read_text(encoding="utf-8")
        )
        self.assertEqual(catalog.get("schema_version"), 1)
        servers = catalog.get("servers")
        self.assertIsInstance(servers, dict)
        self.assertGreater(len(servers), 0)
        for name, entry in servers.items():
            self.assertIn("purpose", entry, msg=name)
            self.assertIn("applies_when", entry, msg=name)
            self.assertIn("auth_env", entry, msg=name)
            self.assertIsInstance(entry["applies_when"], list, msg=name)

    def test_catalog_schema_version_must_be_one(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "catalog.json"
            path.write_text(
                json.dumps({"schema_version": 2, "servers": {}}),
                encoding="utf-8",
            )
            findings = validator.validate_catalog(path)
            messages = [f.message for f in findings]
            self.assertTrue(
                any("schema_version must be 1" in m for m in messages),
                msg=messages,
            )

    def test_catalog_servers_must_be_non_empty_object(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "catalog.json"
            path.write_text(
                json.dumps({"schema_version": 1, "servers": []}),
                encoding="utf-8",
            )
            findings = validator.validate_catalog(path)
            messages = [f.message for f in findings]
            self.assertTrue(
                any("servers must be a non-empty object" in m for m in messages),
                msg=messages,
            )

    def test_catalog_entry_requires_auth_env_field(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "catalog.json"
            path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "servers": {
                            "demo": {
                                "purpose": "demo",
                                "applies_when": ["x"],
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )
            findings = validator.validate_catalog(path)
            messages = [f.message for f in findings]
            self.assertTrue(
                any("auth_env must be declared" in m for m in messages),
                msg=messages,
            )


class InlineCredentialTests(unittest.TestCase):
    def _write(self, root: pathlib.Path, content: dict) -> pathlib.Path:
        path = root / ".mcp.json"
        path.write_text(json.dumps(content, indent=2), encoding="utf-8")
        return path

    def test_env_reference_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            self._write(
                root,
                {
                    "mcpServers": {
                        "github": {
                            "command": "npx",
                            "args": ["-y", "@modelcontextprotocol/server-github"],
                            "env": {"GITHUB_TOKEN": "${GITHUB_TOKEN}"},
                        }
                    }
                },
            )
            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--root", str(root)],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, msg=result.stderr)
            self.assertIn("PASS", result.stdout)

    def test_inline_github_pat_classic_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            self._write(
                root,
                {
                    "mcpServers": {
                        "github": {
                            "env": {"GITHUB_TOKEN": "ghp_" + "a" * 36},
                        }
                    }
                },
            )
            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--root", str(root)],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 1, msg=result.stdout + result.stderr)
            self.assertIn("inline credential", result.stderr)

    def test_inline_openai_key_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            self._write(
                root,
                {
                    "mcpServers": {
                        "openai": {
                            "env": {"OPENAI_API_KEY": "sk-" + "a" * 40},
                        }
                    }
                },
            )
            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--root", str(root)],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 1, msg=result.stdout + result.stderr)
            self.assertIn("inline credential", result.stderr)

    def test_high_entropy_in_auth_field_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            self._write(
                root,
                {
                    "mcpServers": {
                        "demo": {
                            "env": {
                                "API_KEY": "z9X7q2P1m5R3t8V6w4Y0s2C8b1N4u6L0",
                            }
                        }
                    }
                },
            )
            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--root", str(root)],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 1, msg=result.stdout + result.stderr)
            self.assertIn("high-entropy", result.stderr)

    def test_non_auth_field_with_high_entropy_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            self._write(
                root,
                {
                    "mcpServers": {
                        "demo": {
                            "_comment": "z9X7q2P1m5R3t8V6w4Y0s2C8b1N4u6L0 — note id, not a secret",
                        }
                    }
                },
            )
            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--root", str(root)],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, msg=result.stderr)

    def test_suggested_file_is_linted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            (root / ".mcp.json.suggested").write_text(
                json.dumps(
                    {
                        "mcpServers": {
                            "github": {
                                "env": {"GITHUB_TOKEN": "ghp_" + "b" * 36},
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--root", str(root)],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 1, msg=result.stdout + result.stderr)
            self.assertIn(".mcp.json.suggested", result.stderr)

    def test_invalid_json_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            (root / ".mcp.json").write_text("{ not json", encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--root", str(root)],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 1)
            self.assertIn("invalid JSON", result.stderr)


class NoConfigPresentTests(unittest.TestCase):
    def test_empty_root_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--root", tmp],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, msg=result.stderr)
            self.assertIn("PASS", result.stdout)
            self.assertIn("no MCP catalog", result.stdout)

    def test_template_root_passes(self) -> None:
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--root", str(REPO_ROOT)],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("PASS", result.stdout)


class BootstrapDefaultDoesNotCreateMcpFiles(unittest.TestCase):
    """Regression: the default bootstrap must not generate any .mcp.* files.

    Stage 5 ships MCP behind ``--with-mcp-discovery`` so existing downstream
    repos and CI pipelines stay byte-for-byte unchanged when they re-run
    bootstrap without the flag.
    """

    def test_default_bootstrap_has_no_mcp_files(self) -> None:
        target = pathlib.Path(tempfile.mkdtemp(prefix="bootstrap-mcp-default-"))
        self.addCleanup(lambda: shutil.rmtree(target, ignore_errors=True))
        subprocess.run(
            [
                str(REPO_ROOT / "scripts" / "bootstrap-request.sh"),
                "--target",
                str(target),
                "--features",
                "standard",
                "--harness",
                "generic",
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self.assertFalse((target / ".mcp.json").exists())
        self.assertFalse((target / ".mcp.json.suggested").exists())
        self.assertFalse((target / ".agent" / "commands" / "mcp-discover.md").exists())

    def test_with_mcp_discovery_creates_suggested_only(self) -> None:
        target = pathlib.Path(tempfile.mkdtemp(prefix="bootstrap-mcp-optin-"))
        self.addCleanup(lambda: shutil.rmtree(target, ignore_errors=True))
        subprocess.run(
            [
                str(REPO_ROOT / "scripts" / "bootstrap-request.sh"),
                "--target",
                str(target),
                "--features",
                "standard",
                "--harness",
                "generic",
                "--with-mcp-discovery",
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self.assertTrue(
            (target / ".mcp.json.suggested").is_file(),
            msg="--with-mcp-discovery must create .mcp.json.suggested",
        )
        self.assertFalse(
            (target / ".mcp.json").exists(),
            msg="--with-mcp-discovery must NOT create active .mcp.json",
        )
        self.assertTrue(
            (target / ".agent" / "commands" / "mcp-discover.md").is_file(),
            msg="--with-mcp-discovery must render the mcp-discover command",
        )
        manifest = json.loads(
            (target / ".agent" / "manifest.json").read_text(encoding="utf-8")
        )
        self.assertIn("mcp-discovery-suggested", manifest.get("features_enabled", []))

        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--root", str(target)],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr + result.stdout)
        self.assertIn("PASS", result.stdout)


if __name__ == "__main__":
    unittest.main()
