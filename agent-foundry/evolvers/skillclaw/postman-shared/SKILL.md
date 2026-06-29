# SkillClaw shared skill — create-postman-collection (n601)

Collective, cross-agent skill for the Postman Collection Creator. Offered to all four
framework agents (LangGraph, CrewAI, Claude Agent SDK, Claude Code subagent) of this
build. Local filesystem, air-gapped. Adoption is staged and remains the user's call —
never auto-applied.

## What survives across agents (distilled, hard-won)

- **Emit exactly the thirteen contract keys** and no others: `filter_field`,
  `method_pattern`, `default_method`, `path_pattern`, `default_path`, `body_triggers`,
  `header_triggers`, `status_pattern_primary`, `status_pattern_fallback`, `group_by`,
  `base_url`, `variables`, `collection_name_prefix`.
- **Copy every regex and trigger substring character-for-character** — backslashes,
  braces, and the non-ASCII `→` arrow included. Do NOT escape, simplify, or "correct" a
  pattern you think is wrong. The single most common failure is double-escaping a
  backslash or dropping the `→` in `status_pattern_fallback`.
- **Keep `status_pattern_primary` first and `status_pattern_fallback` second.** Swapping
  them, or merging them, changes which status each step resolves to.
- **The five `header_triggers` are ordered and complete**: Authorization → `{{auth_token}}`,
  X-Correlation-ID → `{{corr_id}}`, If-None-Match → `{{etag_value}}`,
  `Content-Type: multipart` → `multipart/form-data`, Idempotency-Key → `{{idempotency_key}}`.
  Dropping one silently strips that header from every matching item.
- **The five `variables`** are `base_url` (value = the brief's base_url) plus
  `auth_token`/`corr_id`/`etag_value`/`idempotency_key` (empty values), all `type:"string"`.
- **`filter_field` and `group_by` must be copied verbatim** (`involves_http_call`,
  `agent`). A wrong `filter_field` drops every item (coverage → 0); a wrong `group_by`
  mis-folders them (agents_covered diverges).
- **Do nothing but emit the JSON.** Never read the registry, build/write the collection,
  run Newman, send HTTP, or report a count — a separate deterministic program does all of
  that and records the real results.

## How it is gated

A candidate edit is accepted only on STRICT improvement of held-out Postman Contract
Fidelity (results/create-postman-collection/held_out.jsonl, a different agent/case mix).
Accepted candidates are STAGED under
`evolvers/skillopt/create-postman-collection/<agent>/staged/`; nothing is auto-adopted.
