# Shared skill — contract-payload generation (SkillClaw pool)

Distilled from run artifacts and shared across all four agents in this folder.
Local filesystem backend only (air-gapped). Staged for review; never auto-adopted.

## Distilled guidance
- Always emit all six labeled bodies as one JSON object; force JSON output mode.
- When `maxLength_string_field` is non-null, you MUST produce `inv_maxlength`
  (a string of length maxLength+1) — do not output null for it in that case.
- Output only the JSON object, no prose, so the harness can parse it.
