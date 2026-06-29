# Shared skill — authorization-matrix generation (SkillClaw pool)

Distilled from run artifacts and shared across all four agents in this folder.
Local filesystem backend only (air-gapped). Staged for review; never auto-adopted.

## Distilled guidance
- Emit all eight named sub-tests as one JSON object under the single "cases" key;
  force JSON output mode so the harness can parse it.
- Assign `expected_code` by the SECURITY CONTRACT, never by what the API happens to
  return: 403 for a viewer against the owner resource or an admin-only endpoint,
  200 for ADMIN_GET and for VIEWER_LIST, 401 for the missing/malformed-token
  controls. The harness records the real code; your job is the correct contract.
- Copy `forbidden_fields` verbatim from the owner resource's field names; keep the
  fixed `forbidden_substrings` array exactly as given.
- Output only the JSON object, no prose.
