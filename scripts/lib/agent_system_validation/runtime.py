"""Runtime helpers for the agent-system validator.

Things that have nothing to do with a particular check group: subprocess
runner, root resolution, file IO, semver parsing, and the small text
parsers shared between checks (skill mapping table, skill-count phrases,
generated-text walker).
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

from .constants import (
    GENERATED_SCAN_EXCLUDED_DIRS,
    GENERATED_SCAN_EXCLUDED_SUFFIXES,
    GENERATED_TEXT_ROOTS,
    NUMERIC_SKILL_COUNT_RE,
    SEMVER_CORE_RE,
    SKILL_COUNT_WORDS,
    WORD_SKILL_COUNT_RE,
)


def run_subprocess(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def resolve_root(start: Path) -> tuple[Path, str]:
    env_root = os.environ.get("AGENT_ROOT")
    if env_root:
        return Path(env_root).resolve(), "env"
    if (start / ".agent").is_dir():
        return start.resolve(), "pwd"
    git = run_subprocess(["git", "rev-parse", "--show-toplevel"], start)
    if git.returncode == 0 and git.stdout.strip():
        return Path(git.stdout.strip()).resolve(), "git"
    return start.resolve(), "pwd"


def detect_mode(root: Path, requested: str) -> str:
    if requested != "auto":
        return requested
    if not (root / ".agent").is_dir() and (root / "core/skills").is_dir():
        return "template"
    return "generated"


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def semver_core_tuple(version: str) -> tuple[int, int, int] | None:
    match = SEMVER_CORE_RE.match(version.strip())
    if not match:
        return None
    return int(match.group(1)), int(match.group(2)), int(match.group(3))


def version_at_least(version: str | None, minimum: str) -> bool:
    if not version or not isinstance(version, str):
        return False
    v = semver_core_tuple(version)
    m = semver_core_tuple(minimum)
    if v is None or m is None:
        return False
    return v >= m


def parse_skill_mapping_names(text: str) -> set[str]:
    names: set[str] = set()
    in_mapping = False
    for line in text.splitlines():
        if line.strip() == "## Skill Mapping":
            in_mapping = True
            continue
        if in_mapping and line.startswith("## "):
            break
        if not in_mapping or not line.lstrip().startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if not cells or cells[0].lower() in {"skill", "---"}:
            continue
        if set(cells[0]) <= {"-", " "}:
            continue
        match = re.fullmatch(r"`([^`]+)`", cells[0])
        if match:
            names.add(match.group(1))
    return names


def skill_count_mentions(text: str) -> list[tuple[str, int]]:
    mentions: list[tuple[str, int]] = []
    for match in WORD_SKILL_COUNT_RE.finditer(text):
        mentions.append((match.group(0), SKILL_COUNT_WORDS[match.group(1).lower()]))
    for match in NUMERIC_SKILL_COUNT_RE.finditer(text):
        mentions.append((match.group(0), int(match.group(1))))
    return mentions


def generated_text_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for rel in GENERATED_TEXT_ROOTS:
        path = root / rel
        if path.is_file():
            files.append(path)
        elif path.is_dir():
            files.extend(
                item
                for item in path.rglob("*")
                if item.is_file()
                and not GENERATED_SCAN_EXCLUDED_DIRS.intersection(item.parts)
                and item.suffix not in GENERATED_SCAN_EXCLUDED_SUFFIXES
            )
    return files
