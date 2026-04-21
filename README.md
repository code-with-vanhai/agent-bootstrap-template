# Agent Bootstrap Template

Tool-agnostic template for adding an agent operating system to an existing repository.

The generated project files live under `.agent/` and are the canonical source of truth for all coding assistants. Tool-specific files such as `AGENTS.md`, `CLAUDE.md`, Cursor rules, Gemini instructions, and Copilot instructions should stay thin and point back to `.agent/`.

## Research Reference

This template is inspired by the repository-scale multi-agent evolution loop described in:

- Cunxi Yu and Haoxing Ren, "Autonomous Evolution of EDA Tools: Multi-Agent Self-Evolved ABC", arXiv:2604.15082.
- PDF: https://arxiv.org/pdf/2604.15082
- Summary of applied lessons: `core/research-basis.md`

The paper shows that agents work best when they are given strong repository knowledge, scoped ownership, correctness checks, measurable evaluation, and a controlled rulebase. This template adapts those ideas for general software repositories with human-in-the-loop operation.

## Design Principles

This template is based on a conservative adaptation of repository-scale multi-agent code evolution:

- Spend effort on repo profiling before code changes.
- Use specialized roles and non-overlapping ownership.
- Require verification gates before accepting changes.
- Keep a champion state and reject regressions.
- Treat the rulebase as evolvable, but only through controlled review.
- Prefer improvements with precedent in the codebase before introducing new architecture.

## Template Layout

```text
agent-bootstrap-template/
├── CHANGELOG.md
├── USAGE.md
├── core/
│   ├── README.md
│   ├── research-basis.md
│   ├── instantiation-prompt.md
│   ├── bootstrap-checklist.md
│   ├── manifest.template.json
│   ├── project-profile.template.md
│   ├── rulebase.template.md
│   ├── ownership.template.md
│   ├── gates.template.md
│   ├── decisions.template.md
│   ├── lessons.template.md
│   ├── hooks/
│   ├── roles/
│   └── workflows/
├── adapters/
├── examples/
└── scripts/
```

## Quickstart

1. Clone or copy this template near the target repository.
2. Ask your LLM coding tool to read `core/instantiation-prompt.md` and instantiate the template into the target repo.
3. In the target repo, run:

```bash
bash scripts/agent-validate.sh
```

4. Review the generated `.agent/` files and thin adapters.
5. Commit the generated agent system only after the repo-specific facts, gates, dangerous operations, and ownership boundaries are correct.

Suggested request:

```text
Setup Agent Bootstrap Kit for this repo.
Read core/instantiation-prompt.md from the agent-bootstrap-template repo and instantiate it here.
Scan the repo first. Do not modify business logic. Do not deploy. Do not run remote migrations.
Mark unknown gates as not configured instead of inventing commands.
```

For detailed usage, see `USAGE.md`.

## Intended Generated Layout

```text
repo/
├── .agent/
│   ├── README.md
│   ├── manifest.json
│   ├── project-profile.md
│   ├── rulebase.md
│   ├── ownership.md
│   ├── gates.md
│   ├── decisions.md
│   ├── lessons.md
│   ├── roles/
│   └── workflows/
├── scripts/
│   ├── agent-eval.sh
│   └── agent-validate.sh
├── AGENTS.md
├── CLAUDE.md
├── GEMINI.md
├── .cursor/rules/agent-system.mdc
└── .github/copilot-instructions.md
```

## Instantiation Rule

Do not copy placeholders blindly. For each target repo, scan the actual repository and replace template sections with observed facts. If a gate, test framework, deploy command, or ownership boundary is unknown, mark it as `not configured` instead of inventing it.

## Upgrade Policy

When this template changes, re-instantiate manually:

1. Read `CHANGELOG.md`.
2. Apply only relevant template changes to the target repo.
3. Review the diff.
4. Run `scripts/agent-validate.sh` in the target repo.

Do not use automatic migrations for agent rules unless a future incident proves they are necessary.
