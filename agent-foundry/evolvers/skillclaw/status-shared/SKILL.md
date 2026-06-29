# Shared skill pool — verify-response-status-codes (SkillClaw, local, air-gapped)

Distilled, cross-agent guidance offered to all four agents. Adoption is the user's call.

- Emit a descriptor for EVERY documented code (coverage beats cleverness).
- 400 = exactly one required field removed; never empty the whole body.
- 401 = no Authorization header; 500 = the named 'malformed' auth mode.
- 404 = replace only {id} with the literal nonexistent id; keep the path shape.
- Status-hook ops (/http/<n>) are sent verbatim, no auth, no body.
