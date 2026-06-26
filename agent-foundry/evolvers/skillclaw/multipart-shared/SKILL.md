# Shared skill — multipart/form-data handling test-plan construction

Collective (SkillClaw) pool for the api-tester / test-multipart-form-data-handling
workflow. Local filesystem, air-gapped. Offered to all four agents; adoption is the
user's call (never auto-adopted).

Distilled, framework-neutral guidance that survived the debate gate and held-out
evaluation:

- Emit ONE JSON object with exactly seven keys: `endpoint`, `method`, `text_fields`,
  `file_field`, `max_allowed_file_bytes`, `readback_path`, `cases`.
- `text_fields` is exactly two `{name, value}` objects in the briefed order, values
  copied verbatim. Never merge them, reorder them, or invent a value.
- `file_field` is a single descriptor `{name, media_type, size_bytes}` — a description
  of the part, never the file bytes themselves. The harness builds the exact-sized PNG
  and computes the MD5; the agent does not.
- `cases` is exactly nine `{label}` objects in the fixed order:
  `create_status`, `text_field_a_exact`, `text_field_b_exact`, `document_url_present`,
  `file_md5_roundtrip`, `persisted_readback`, `oversized_rejected`,
  `missing_required_field`, `wrong_content_type`. Never drop, add, reorder, or rename one.
- Copy every media type, name, value, number, and path exactly from the named brief
  field. Do not normalize (`image/png` stays `image/png`; paths keep their slashes).
- Never send a request, build a body, or assert a status/MD5. The deterministic harness
  owns all I/O; the agent owns only the plan.
