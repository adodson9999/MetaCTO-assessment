# Shared skill — response-schema validation (SkillClaw pool, schema task)

Distilled from run artifacts and shared across all four agents in this folder for
the `validate-json-schema-responses` workflow. Local filesystem backend only
(air-gapped). Staged for review; never auto-adopted.

## Distilled guidance

- Emit exactly the two-key object `{ "request", "documented_response_schemas" }`
  as one JSON object; force JSON output mode so the harness can parse it.
- `request.body` is the known-valid example copied verbatim for POST/PUT/PATCH,
  else null. `request.path` substitutes `{id}` with the literal `"1"`.
  `request.auth` is `"valid"` only when the endpoint requires auth.
- In `documented_response_schemas`, copy each response key as a STRING (e.g.
  `"2xx"`, `"400"`) and copy `has_json_schema` EXACTLY from the brief — never
  guess `true`. Hallucinating a schema where the spec documents none is the single
  most common way to lose fidelity on this task.
- Never validate, never send, never invent a conformance verdict — the harness
  runs ajv v8 and records the real outcome.

## Standing finding (carried to all agents)

The current spec documents 0 response schemas, so the Schema Conformance Rate is
N/A. The correct agent behavior is to report the gap honestly (has_json_schema =
false for every key) rather than fabricate a conformance result.
