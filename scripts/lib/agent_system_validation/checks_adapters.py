"""Thin-adapter (AGENTS.md / CLAUDE.md / etc.) checks.

Adapters must point to `.agent/` and carry the four tier headings
(``## Always do``, ``## Ask first``, ``## Never do``, ``## Commands``).
The template-mode and generated-mode flavors differ only in the file
paths they look at.
"""

from __future__ import annotations

from .constants import THIN_ADAPTER_GENERATED_PATHS, THIN_ADAPTER_TIER_HEADINGS
from .core import AgentSystemValidator
from .runtime import read_text


def validate_thin_adapter_file_template(
    validator: AgentSystemValidator, rel: str
) -> None:
    if not (validator.root / rel).is_file():
        validator.fail(f"{rel} is missing", rel)
        return
    text = read_text(validator.root / rel)
    if ".agent/" in text:
        validator.pass_(f"{rel} points to .agent/", rel)
    else:
        validator.fail(f"{rel} exists but does not point to .agent/", rel)
    for heading in THIN_ADAPTER_TIER_HEADINGS:
        validator.contains(rel, heading, f"{rel} includes {heading}")


def validate_generated_adapters(validator: AgentSystemValidator) -> None:
    for adapter in THIN_ADAPTER_GENERATED_PATHS:
        path = validator.root / adapter
        if path.exists():
            if ".agent/" in read_text(path):
                validator.pass_(f"{adapter} points to .agent/", adapter)
            else:
                validator.fail(
                    f"{adapter} exists but does not point to .agent/", adapter
                )
            for heading in THIN_ADAPTER_TIER_HEADINGS:
                validator.contains(adapter, heading, f"{adapter} includes {heading}")
        else:
            validator.skip(f"{adapter} not generated", adapter)
