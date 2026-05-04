"""Adapter and rulebase token-budget line-count checks."""

from __future__ import annotations

from .core import AgentSystemValidator


def validate_token_budget(validator: AgentSystemValidator) -> None:
    """Cap adapter and rulebase files at line budgets so prompts stay
    within harness context windows. Missing optional adapters are
    skipped; an existing file over budget fails with the line count.
    """

    if validator.mode == "template":
        budgets: tuple[tuple[str, int], ...] = (
            ("adapters/AGENTS.md", 200),
            ("adapters/CLAUDE.md", 200),
            ("adapters/GEMINI.md", 200),
            ("adapters/cursor-agent-system.mdc", 200),
            ("adapters/copilot-instructions.md", 200),
            ("core/rulebase.template.md", 250),
            ("core/constitution.template.md", 100),
        )
    else:
        budgets = (
            ("AGENTS.md", 200),
            ("CLAUDE.md", 200),
            ("GEMINI.md", 200),
            (".cursor/rules/agent-system.mdc", 200),
            (".github/copilot-instructions.md", 200),
            (".agent/rulebase.md", 250),
            (".agent/constitution.md", 100),
        )

    for rel, limit in budgets:
        path = validator.root / rel
        if not path.is_file():
            validator.skip(f"{rel} not present for token-budget check", rel)
            continue
        line_count = sum(
            1 for _ in path.read_text(encoding="utf-8").splitlines()
        )
        if line_count > limit:
            validator.fail(
                f"{rel} is {line_count} lines, exceeds budget of {limit}; "
                f"trim or move scope-specific guidance into nested repo "
                f"instructions",
                rel,
            )
        else:
            validator.pass_(
                f"{rel} is {line_count} lines (budget {limit})", rel
            )
