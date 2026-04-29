---
name: data-safety
description: Use when touching production data, PII, customer records, audit logs, analytics events, database migrations, ETL/ingestion code, exports, integrations, or any path that reads or writes user-owned or operator-owned data.
---

# Data Safety

Agents must not silently expose, modify, delete, or normalize data that belongs to users, customers, operators, or auditors.

## Hard Gate

```text
NO PRODUCTION DATA EXPOSURE, PII LEAKAGE, OR DESTRUCTIVE DATA OPERATIONS
WITHOUT EXPLICIT HUMAN APPROVAL
```

Before touching data-adjacent files or behavior:

1. Re-read `.agent/project-profile.md` (Data Surface section) and `.agent/rulebase.md`.
2. Confirm whether the touched path is listed under PII, audit, analytics, exports, or destructive operations; if it is not, stop and ask whether the inventory is incomplete before editing.
3. Do not invent fixtures with realistic-looking PII. Use clearly synthetic data and document the source.
4. For migrations and exports, state the rollback or revoke path in the run plan before editing.
5. Run the configured data/security gates or report `not configured` honestly.

## Red Flags

- "I'll just log the request body to debug this."
- "This script needs the real customer ids; tests can use prod for now."
- "I will drop this column; we can recreate it from backups."
- "The export is internal-only, so it doesn't need PII redaction."
- "The audit log is append-only, so this delete doesn't matter."

## Canonical Sources

- `.agent/project-profile.md` (Data Surface)
- `.agent/rulebase.md`
- `.agent/ownership.md`
