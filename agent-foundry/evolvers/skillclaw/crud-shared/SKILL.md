# Shared skill — CRUD-integrity test plan construction

Distilled, cross-agent (SkillClaw). Local filesystem backend, air-gapped. Offered
to all four agents; adoption is the user's call.

- Always emit all six steps in the fixed order; never drop a step even if you expect
  the API to 404 it (a dropped step counts as a fidelity miss).
- Keep {RESOURCE_ID} literal in every id-bearing path; the harness substitutes the
  real id captured from the CREATE response, so chaining stays correct.
- Echo the given table name and copy the given create/update bodies unchanged.
