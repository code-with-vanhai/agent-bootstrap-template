# Research Basis

This template adapts lessons from:

- Cunxi Yu and Haoxing Ren, "Autonomous Evolution of EDA Tools: Multi-Agent Self-Evolved ABC", arXiv:2604.15082, submitted April 16, 2026.
- Source: https://arxiv.org/abs/2604.15082
- PDF: https://arxiv.org/pdf/2604.15082

## Short Description

The paper presents a multi-agent system that evolves the ABC logic synthesis tool at repository scale. Instead of letting one broad agent edit everything, it uses specialized agents for different subsystems, a planning agent for coordination, formal correctness checks before evaluation, benchmark-driven QoR measurement, and a rulebase that can be refined under safety constraints.

The key transferable idea is not fully autonomous coding. The useful pattern is a controlled loop:

```text
profile repo -> assign scoped owner -> create candidate patch -> verify correctness -> evaluate metrics -> accept/reject -> update lessons/rules
```

This template adapts that loop for normal software repositories. It replaces EDA-specific formal equivalence and QoR benchmarks with repo-specific gates such as typecheck, tests, builds, contract checks, security review, e2e flows, and explicit acceptance criteria.

## Applicable Lessons

### 1. Knowledge Bootstrapping First

The paper's system spends a large share of effort on pre-evolution repository profiling and structured Markdown tutorials before allowing agents to edit code. This template mirrors that with `project-profile.md`, `ownership.md`, `decisions.md`, and explicit bootstrap workflow.

Practical rule:

- Do not start implementation until the agent has identified the stack, module boundaries, build/test commands, public contracts, and dangerous operations.

### 2. Specialized Agents Beat One Broad Agent

The paper avoids one monolithic coding agent. Instead, coding agents are scoped to non-overlapping subsystems. This template mirrors that with ownership mapping and role-specific instructions.

Practical rule:

- Assign each task to the narrowest capable role.
- Require coordination when a task crosses boundaries.

### 3. Verification Must Precede Evaluation

The paper compiles first, then runs correctness checking, then evaluates quality metrics. For normal software repositories, the equivalent is:

- Build/typecheck before broader evaluation.
- Unit/integration/e2e tests before claiming behavior works.
- Contract, migration, security, and performance checks when the touched subsystem requires them.

Practical rule:

- No improvement claim is valid without the relevant gate.

### 4. Use Champion and Rollback Semantics

The paper keeps beneficial changes and rejects regressions. In application repositories, this means a patch should be treated as a candidate until verified.

Practical rule:

- Preserve the current working baseline.
- If a candidate fails gates or violates rulebase constraints, fix forward if scoped; otherwise stop and report the rejection reason.

### 5. Metrics Need Primary and Auxiliary Signals

The paper evaluates primary QoR metrics and intermediate structural metrics. Software repos need the same distinction.

Examples:

- Primary: tests pass, build passes, endpoint behavior correct, latency budget met, accessibility requirement met.
- Auxiliary: bundle size, coverage delta, type errors, lint trend, query count, migration risk, error logs.

Practical rule:

- Do not optimize auxiliary metrics at the expense of primary correctness.

### 6. Rulebases Can Evolve, But Not Silently

The paper includes a self-evolving rulebase with controlled relaxation when rules block beneficial changes. For production software, rule changes must be explicit and human-reviewable.

Practical rule:

- Agents may propose rule changes.
- Agents must not silently weaken security, deployment, data, migration, or contract rules.

### 7. Agents Work Best With Structural Precedent

The paper reports better results when agents refine existing algorithms and conventions, while fully novel constructs fail more often.

Practical rule:

- Prefer local patterns, existing abstractions, and repo conventions.
- If a new architecture is needed, create an explicit design decision before broad implementation.

## Non-Goals

This template does not attempt fully autonomous self-evolution. It is designed for human-in-the-loop engineering where agents produce patches, run gates, explain risk, and preserve repo-specific rules.
