# Shared skill — header-propagation testing (SkillClaw pool)

Collective, cross-agent skill for the api-tester / validate-header-propagation workflow.
Stored on the local filesystem (air-gapped); offered to all four agents. Adoption is the
user's call — never auto-applied.

## Distilled guidance

- Carry the correlation id **byte-for-byte**. Never trim, lowercase, re-case, or
  "regenerate" it — the whole test is whether the *exact* value survives. A UUID-looking
  id is still an opaque string; do not reformat it.
- Preserve the **exact header name casing** (`X-Correlation-ID`). HTTP headers are
  case-insensitive on the wire, but the test asserts the documented spelling.
- Emit **both** requests: a with-header request that carries `header_name: correlation_id`
  (plus `Authorization: Bearer <valid_token>` when auth is required), and a no-header
  request that carries **no** correlation header under any casing — that second request is
  what exercises auto-generation.
- Use the **literal** `<valid_token>` placeholder for auth — never a real or invented token;
  the harness substitutes a real one.
- Include the **complete, ordered** eight-item assertions array so every propagation point
  (response echo, API-log presence + unmodified, downstream count + propagation, no-header
  auto-UUID + its propagation) is covered.
- Produce **only** the JSON plan. Send no requests, grep no logs, invent no results — a
  separate deterministic harness executes the plan and records the real responses and logs.
