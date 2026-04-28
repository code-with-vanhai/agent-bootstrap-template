---
name: no-secret-leakage
description: Use when touching .env files, credentials, tokens, private keys, auth config, logging, CI secrets, or any code path that may expose secrets.
---

# No Secret Leakage

Agents must not expose, edit, invent, or normalize secrets.

## Hard Gate

```text
NO SECRET, TOKEN, CREDENTIAL, PRIVATE KEY, OR .ENV VALUE LEAKAGE
```

Before touching secret-adjacent files or behavior:

1. Re-read `.agent/rulebase.md` and `.agent/gates.md`.
2. Do not edit secret values or `.env` values without explicit human approval.
3. Prefer placeholders or documented secret names over real values.
4. Run the configured security gate or report that secret scanning is `not configured`.
5. Report any skipped scanner and residual risk.

## Red Flags

- "I will paste the token temporarily."
- "The .env value looks harmless."
- "The scanner is missing, so this is safe."
- "I can add the real key and the user can rotate it later."
- Logging request headers, authorization values, cookies, private keys, or session tokens.

## Canonical Sources

- `.agent/rulebase.md`
- `.agent/gates.md`
- `scripts/agent-eval.sh security`
