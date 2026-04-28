import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from scripts.lib import gate_discovery


class GateDiscoveryTests(unittest.TestCase):
    def make_repo(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        return Path(tmp.name)

    def by_command(self, root):
        return {item.command: item for item in gate_discovery.discover(root)}

    def test_node_package_scripts_use_lockfile_package_manager(self):
        root = self.make_repo()
        (root / "pnpm-lock.yaml").write_text("lockfileVersion: '9.0'\n", encoding="utf-8")
        (root / "package.json").write_text(
            json.dumps(
                {
                    "scripts": {
                        "test": "vitest run",
                        "typecheck": "tsc --noEmit",
                        "e2e": "playwright test",
                        "build": "vite build",
                        "start": "vite --host 0.0.0.0",
                    }
                }
            ),
            encoding="utf-8",
        )

        commands = self.by_command(root)

        self.assertEqual(commands["pnpm run test"].gate, "fast")
        self.assertEqual(commands["pnpm run typecheck"].gate, "shared")
        self.assertEqual(commands["pnpm run e2e"].gate, "e2e")
        self.assertEqual(commands["pnpm run build"].gate, "full")
        self.assertNotIn("pnpm run start", commands)
        self.assertEqual(commands["pnpm run test"].evidence_file, "package.json")
        self.assertEqual(commands["pnpm run test"].evidence_key, "scripts.test")

    def test_python_markers_and_requirements_create_candidates(self):
        root = self.make_repo()
        (root / "pyproject.toml").write_text(
            """
[tool.pytest.ini_options]
testpaths = ["tests"]

[tool.ruff]
line-length = 100

[tool.mypy]
python_version = "3.11"
""",
            encoding="utf-8",
        )
        (root / "requirements.txt").write_text("bandit==1.7.9\n", encoding="utf-8")

        commands = self.by_command(root)

        self.assertEqual(commands["python -m pytest"].gate, "fast")
        self.assertEqual(commands["python -m ruff check ."].gate, "fast")
        self.assertEqual(commands["python -m mypy ."].gate, "shared")
        self.assertEqual(commands["python -m bandit -r ."].gate, "security")

    def test_language_and_task_file_markers_create_candidates(self):
        root = self.make_repo()
        (root / "go.mod").write_text("module example.com/app\n", encoding="utf-8")
        (root / "Cargo.toml").write_text("[package]\nname = \"app\"\n", encoding="utf-8")
        (root / "Makefile").write_text(
            """
test:
\tgo test ./...
lint:
\tgolangci-lint run
deploy:
\t./deploy.sh
""",
            encoding="utf-8",
        )
        (root / "Taskfile.yml").write_text(
            """
version: '3'
tasks:
  e2e:
    cmds:
      - playwright test
""",
            encoding="utf-8",
        )

        commands = self.by_command(root)

        self.assertEqual(commands["go test ./..."].gate, "fast")
        self.assertEqual(commands["go vet ./..."].gate, "shared")
        self.assertEqual(commands["cargo test"].gate, "fast")
        self.assertEqual(commands["make test"].confidence, "high")
        self.assertEqual(commands["task e2e"].gate, "e2e")
        self.assertNotIn("make deploy", commands)

    def test_java_and_github_actions_evidence(self):
        root = self.make_repo()
        (root / "gradlew").write_text("#!/usr/bin/env bash\n", encoding="utf-8")
        (root / "build.gradle.kts").write_text("plugins { java }\n", encoding="utf-8")
        workflow_dir = root / ".github" / "workflows"
        workflow_dir.mkdir(parents=True)
        (workflow_dir / "ci.yml").write_text(
            """
name: ci
jobs:
  test:
    steps:
      - run: npm run lint
      - run: gitleaks dir .
      - run: echo hello
""",
            encoding="utf-8",
        )

        commands = self.by_command(root)

        self.assertEqual(commands["./gradlew test"].gate, "fast")
        self.assertEqual(commands["./gradlew build"].gate, "full")
        self.assertEqual(commands["npm run lint"].gate, "fast")
        self.assertEqual(commands["gitleaks dir ."].gate, "security")
        self.assertNotIn("echo hello", commands)

    def test_write_suggestions_requires_existing_agent_dir(self):
        root = self.make_repo()
        (root / "package.json").write_text(
            '{"scripts":{"test":"node --test"}}\n',
            encoding="utf-8",
        )

        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(gate_discovery.main(["--root", str(root), "--write-suggestions"]), 2)

        (root / ".agent").mkdir()
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            self.assertEqual(gate_discovery.main(["--root", str(root), "--write-suggestions"]), 0)

        written = (root / ".agent" / "gate-suggestions.json").read_text(encoding="utf-8")
        self.assertEqual(json.loads(stdout.getvalue()), json.loads(written))
        self.assertEqual(json.loads(written)[0]["status"], "candidate")


if __name__ == "__main__":
    unittest.main()
