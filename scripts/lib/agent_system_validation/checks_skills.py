"""Skill manifest, set, mapping, and skill-count drift checks."""

from __future__ import annotations

import re

from .core import AgentSystemValidator
from .runtime import parse_skill_mapping_names, read_text, skill_count_mentions


def load_skill_manifest(validator: AgentSystemValidator) -> list[str]:
    rel = "core/skills/manifest.json"
    data = validator.json_file(rel, f"{rel} is valid JSON")
    if data is None:
        return []
    if data.get("schema_version") == 1:
        validator.pass_(f"{rel} schema_version is 1", rel)
    else:
        validator.fail(f"{rel} schema_version must be 1", rel)

    skills = data.get("skills")
    if (
        not isinstance(skills, list)
        or not skills
        or not all(isinstance(item, str) for item in skills)
    ):
        validator.fail(f"{rel} skills must be a non-empty array of strings", rel)
        return []

    duplicates = sorted({item for item in skills if skills.count(item) > 1})
    if duplicates:
        validator.fail(
            f"{rel} contains duplicate skill names: {', '.join(duplicates)}", rel
        )
    else:
        validator.pass_(f"{rel} lists {len(skills)} skills", rel)
    return skills


def validate_skill_set(validator: AgentSystemValidator, skills: list[str]) -> None:
    expected = set(skills)
    actual = {
        path.parent.name
        for path in (validator.root / "core/skills").glob("*/SKILL.md")
    }
    missing = sorted(expected - actual)
    unexpected = sorted(actual - expected)
    if missing:
        validator.fail(
            "core/skills missing manifest skill directories: " + ", ".join(missing),
            "core/skills",
        )
    if unexpected:
        validator.fail(
            "core/skills contains skills not listed in manifest: "
            + ", ".join(unexpected),
            "core/skills",
        )
    if not missing and not unexpected:
        validator.pass_(
            f"core/skills matches manifest skill set ({len(expected)} skills)",
            "core/skills",
        )

    for skill in skills:
        skill_file = f"core/skills/{skill}/SKILL.md"
        validator.exists(skill_file)
        validator.contains(
            skill_file,
            f"^name: {re.escape(skill)}$",
            f"{skill_file} has matching skill name",
            regex=True,
        )
        validator.contains(
            skill_file,
            "^description: Use when",
            f"{skill_file} has trigger-style description",
            regex=True,
        )
        validator.contains(
            skill_file, "Canonical Sources", f"{skill_file} lists canonical sources"
        )


def validate_skill_mapping(validator: AgentSystemValidator, skills: list[str]) -> None:
    rel = "core/skills/README.md"
    path = validator.root / rel
    if not path.is_file():
        validator.fail(
            f"{rel} Skill Mapping cannot be checked because file is missing", rel
        )
        return
    mapped = parse_skill_mapping_names(read_text(path))
    expected = set(skills)
    missing = sorted(expected - mapped)
    unexpected = sorted(mapped - expected)
    if missing:
        validator.fail(
            f"{rel} Skill Mapping is missing skills: {', '.join(missing)}", rel
        )
    if unexpected:
        validator.fail(
            f"{rel} Skill Mapping lists unexpected skills: {', '.join(unexpected)}",
            rel,
        )
    if not missing and not unexpected:
        validator.pass_(f"{rel} Skill Mapping matches manifest skill set", rel)


def validate_skill_count_docs(
    validator: AgentSystemValidator, skills: list[str]
) -> None:
    expected_count = len(skills)
    for rel in ("README.md", "USAGE.md", "core/skills/README.md"):
        path = validator.root / rel
        if not path.is_file():
            validator.skip(f"{rel} not present for skill count drift check", rel)
            continue
        mismatches = [
            phrase
            for phrase, count in skill_count_mentions(read_text(path))
            if count != expected_count
        ]
        if mismatches:
            validator.fail(
                f"{rel} has stale skill count mention(s): {', '.join(mismatches)}; "
                f"expected {expected_count} skills from core/skills/manifest.json",
                rel,
            )
        else:
            validator.pass_(f"{rel} skill count mentions match manifest", rel)
