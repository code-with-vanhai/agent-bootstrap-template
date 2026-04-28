#!/usr/bin/env python3
"""Discover candidate Agent Bootstrap gates from checked-in repo evidence."""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable


GATE_BY_TASK_WORD = (
    ("security", "security"),
    ("audit", "security"),
    ("secret", "security"),
    ("gitleaks", "security"),
    ("semgrep", "security"),
    ("bandit", "security"),
    ("e2e", "e2e"),
    ("playwright", "e2e"),
    ("cypress", "e2e"),
    ("frontend", "frontend"),
    ("backend", "backend"),
    ("server", "backend"),
    ("api", "backend"),
    ("typecheck", "shared"),
    ("type-check", "shared"),
    ("types", "shared"),
    ("lint", "fast"),
    ("test", "fast"),
    ("check", "fast"),
    ("build", "full"),
    ("verify", "full"),
)


@dataclass(frozen=True)
class Candidate:
    status: str
    gate: str
    command: str
    evidence_file: str
    evidence_key: str
    confidence: str
    notes: str


def relpath(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8", errors="replace")


def task_gate(name: str, command: str = "") -> str | None:
    haystack = f"{name} {command}".lower()
    for needle, gate in GATE_BY_TASK_WORD:
        if needle in haystack:
            return gate
    return None


def package_manager(root: Path) -> str:
    if (root / "pnpm-lock.yaml").exists() or (root / "pnpm-workspace.yaml").exists():
        return "pnpm"
    if (root / "yarn.lock").exists():
        return "yarn"
    return "npm"


def candidate(
    *,
    root: Path,
    gate: str,
    command: str,
    evidence_file: Path,
    evidence_key: str,
    confidence: str,
    notes: str,
) -> Candidate:
    return Candidate(
        status="candidate",
        gate=gate,
        command=command,
        evidence_file=relpath(root, evidence_file),
        evidence_key=evidence_key,
        confidence=confidence,
        notes=notes,
    )


def discover_node(root: Path) -> list[Candidate]:
    package_json = root / "package.json"
    if not package_json.exists():
        return []
    try:
        data = json.loads(read_text(package_json))
    except json.JSONDecodeError:
        return []
    scripts = data.get("scripts")
    if not isinstance(scripts, dict):
        return []

    pm = package_manager(root)
    found: list[Candidate] = []
    for name, script in scripts.items():
        if not isinstance(name, str) or not isinstance(script, str):
            continue
        gate = task_gate(name, script)
        if gate is None:
            continue
        found.append(
            candidate(
                root=root,
                gate=gate,
                command=f"{pm} run {name}",
                evidence_file=package_json,
                evidence_key=f"scripts.{name}",
                confidence="high",
                notes=f"package.json script command: {script}",
            )
        )
    return found


def discover_python(root: Path) -> list[Candidate]:
    found: list[Candidate] = []
    pyproject = root / "pyproject.toml"
    if pyproject.exists():
        text = read_text(pyproject)
        marker_commands = (
            (r"(?m)^\[tool\.pytest", "fast", "python -m pytest", "tool.pytest", "high"),
            (r"(?m)^\[tool\.ruff", "fast", "python -m ruff check .", "tool.ruff", "high"),
            (r"(?m)^\[tool\.mypy", "shared", "python -m mypy .", "tool.mypy", "high"),
            (r"(?m)^\[tool\.pyright", "shared", "python -m pyright", "tool.pyright", "high"),
            (r"(?m)^\[tool\.bandit", "security", "python -m bandit -r .", "tool.bandit", "high"),
        )
        for pattern, gate, command, evidence_key, confidence in marker_commands:
            if re.search(pattern, text):
                found.append(
                    candidate(
                        root=root,
                        gate=gate,
                        command=command,
                        evidence_file=pyproject,
                        evidence_key=evidence_key,
                        confidence=confidence,
                        notes="Python tool configuration is present in pyproject.toml.",
                    )
                )

    requirements = root / "requirements.txt"
    if requirements.exists():
        req_text = read_text(requirements).lower()
        for package, gate, command in (
            ("pytest", "fast", "python -m pytest"),
            ("ruff", "fast", "python -m ruff check ."),
            ("mypy", "shared", "python -m mypy ."),
            ("bandit", "security", "python -m bandit -r ."),
        ):
            if re.search(rf"(?m)^\s*{re.escape(package)}(?:[<=>\[]|$)", req_text):
                found.append(
                    candidate(
                        root=root,
                        gate=gate,
                        command=command,
                        evidence_file=requirements,
                        evidence_key=f"requirement:{package}",
                        confidence="medium",
                        notes=f"{package} is listed in requirements.txt.",
                    )
                )
    return found


def discover_go(root: Path) -> list[Candidate]:
    go_mod = root / "go.mod"
    if not go_mod.exists():
        return []
    return [
        candidate(
            root=root,
            gate="fast",
            command="go test ./...",
            evidence_file=go_mod,
            evidence_key="module",
            confidence="medium",
            notes="go.mod confirms a Go module; verify package scope before promotion.",
        ),
        candidate(
            root=root,
            gate="shared",
            command="go vet ./...",
            evidence_file=go_mod,
            evidence_key="module",
            confidence="medium",
            notes="go.mod confirms a Go module; vet remains a candidate until reviewed.",
        ),
    ]


def discover_rust(root: Path) -> list[Candidate]:
    cargo_toml = root / "Cargo.toml"
    if not cargo_toml.exists():
        return []
    return [
        candidate(
            root=root,
            gate="fast",
            command="cargo test",
            evidence_file=cargo_toml,
            evidence_key="package-or-workspace",
            confidence="medium",
            notes="Cargo.toml confirms a Rust package/workspace.",
        ),
        candidate(
            root=root,
            gate="shared",
            command="cargo clippy --all-targets --all-features",
            evidence_file=cargo_toml,
            evidence_key="package-or-workspace",
            confidence="medium",
            notes="Cargo.toml confirms Rust; clippy availability must be verified before promotion.",
        ),
    ]


def discover_java(root: Path) -> list[Candidate]:
    pom = root / "pom.xml"
    if pom.exists():
        return [
            candidate(
                root=root,
                gate="fast",
                command="mvn test",
                evidence_file=pom,
                evidence_key="project",
                confidence="medium",
                notes="pom.xml confirms a Maven project.",
            ),
            candidate(
                root=root,
                gate="full",
                command="mvn verify",
                evidence_file=pom,
                evidence_key="project",
                confidence="medium",
                notes="pom.xml confirms Maven lifecycle support; verify plugins before promotion.",
            ),
        ]

    for gradle in (root / "build.gradle", root / "build.gradle.kts"):
        if gradle.exists():
            runner = "./gradlew" if (root / "gradlew").exists() else "gradle"
            return [
                candidate(
                    root=root,
                    gate="fast",
                    command=f"{runner} test",
                    evidence_file=gradle,
                    evidence_key="gradle-build",
                    confidence="medium",
                    notes="Gradle build file is present.",
                ),
                candidate(
                    root=root,
                    gate="full",
                    command=f"{runner} build",
                    evidence_file=gradle,
                    evidence_key="gradle-build",
                    confidence="medium",
                    notes="Gradle build file is present.",
                ),
            ]
    return []


def parse_simple_targets(text: str, pattern: str) -> Iterable[str]:
    for match in re.finditer(pattern, text, re.MULTILINE):
        target = match.group(1)
        if target.startswith(".") or "/" in target:
            continue
        yield target


def discover_task_files(root: Path) -> list[Candidate]:
    files = (
        ("Makefile", "make", r"^([A-Za-z0-9_.-]+)\s*:(?![=])"),
        ("makefile", "make", r"^([A-Za-z0-9_.-]+)\s*:(?![=])"),
        ("justfile", "just", r"^([A-Za-z0-9_.-]+)\s*:"),
        ("Justfile", "just", r"^([A-Za-z0-9_.-]+)\s*:"),
        ("Taskfile.yml", "task", r"^\s{2}([A-Za-z0-9_.-]+)\s*:"),
        ("Taskfile.yaml", "task", r"^\s{2}([A-Za-z0-9_.-]+)\s*:"),
    )
    found: list[Candidate] = []
    for file_name, runner, pattern in files:
        path = root / file_name
        if not path.exists():
            continue
        for target in parse_simple_targets(read_text(path), pattern):
            gate = task_gate(target)
            if gate is None:
                continue
            command = f"{runner} {target}"
            found.append(
                candidate(
                    root=root,
                    gate=gate,
                    command=command,
                    evidence_file=path,
                    evidence_key=f"target:{target}",
                    confidence="high",
                    notes=f"{file_name} defines target {target}.",
                )
            )
    return found


def discover_github_actions(root: Path) -> list[Candidate]:
    workflows = sorted((root / ".github" / "workflows").glob("*.yml"))
    workflows.extend(sorted((root / ".github" / "workflows").glob("*.yaml")))
    found: list[Candidate] = []
    for workflow in workflows:
        for line_number, line in enumerate(read_text(workflow).splitlines(), start=1):
            match = re.match(r"^\s*(?:-\s*)?run:\s*(.+?)\s*$", line)
            if not match:
                continue
            command = match.group(1).strip("'\"")
            if not command or command in {"|", ">"}:
                continue
            gate = task_gate(command, command)
            if gate is None:
                continue
            found.append(
                candidate(
                    root=root,
                    gate=gate,
                    command=command,
                    evidence_file=workflow,
                    evidence_key=f"run:{line_number}",
                    confidence="high",
                    notes="GitHub Actions run step contains this command.",
                )
            )
    return found


def dedupe(candidates: Iterable[Candidate]) -> list[Candidate]:
    by_key: dict[tuple[str, str, str, str], Candidate] = {}
    for item in candidates:
        key = (item.gate, item.command, item.evidence_file, item.evidence_key)
        by_key.setdefault(key, item)
    return sorted(by_key.values(), key=lambda item: (item.evidence_file, item.gate, item.command))


def discover(root: Path) -> list[Candidate]:
    root = root.resolve()
    candidates: list[Candidate] = []
    for parser in (
        discover_node,
        discover_python,
        discover_go,
        discover_rust,
        discover_java,
        discover_task_files,
        discover_github_actions,
    ):
        candidates.extend(parser(root))
    return dedupe(candidates)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="Repository root to scan.")
    parser.add_argument(
        "--write-suggestions",
        action="store_true",
        help="Write .agent/gate-suggestions.json in addition to stdout.",
    )
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    candidates = [asdict(item) for item in discover(root)]
    output = json.dumps(candidates, ensure_ascii=False, indent=2)

    if args.write_suggestions:
        agent_dir = root / ".agent"
        if not agent_dir.is_dir():
            print(
                "ERROR: --write-suggestions requires an existing .agent/ directory.",
                file=sys.stderr,
            )
            return 2
        (agent_dir / "gate-suggestions.json").write_text(output + "\n", encoding="utf-8")

    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
