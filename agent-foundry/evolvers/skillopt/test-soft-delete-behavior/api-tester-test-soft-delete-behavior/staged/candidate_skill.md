# best_skill — soft-delete-behavior test-plan generation

Seed skill (debate-gated APPROVED_PROMPT is the source of truth). SkillOpt may stage
bounded edits here behind the held-out Soft-Delete-Test Fidelity gate; never auto-adopted.

Operating rules distilled from the gated prompt:
- Emit ONE JSON object with exactly seven keys: "case_count", "create", "delete",
  "get_deleted", "collection", "db_query", "include_deleted".
- "create" (3 keys): method "POST", endpoint=resource_endpoint, fields=create_fields (copied).
- "delete" (3 keys): method "DELETE", path_template=resource_endpoint+"/{RESOURCE_ID}",
  expected_status=the delete_expected_status array (e.g. [200,204]).
- "get_deleted" (4 keys): method "GET", path_template=resource_endpoint+"/{RESOURCE_ID}",
  expected_status=get_deleted_expected_status (404), assert_no_field_values=true.
- "collection" (4 keys): method "GET", endpoint=resource_endpoint, expected_status=200,
  assert_absent=true.
- "db_query" (8 keys): table + id_column + deleted_at_column + is_deleted_column (copied),
  assert_row_exists=true, assert_deleted_at_not_null=true, assert_is_deleted_true=true,
  deleted_at_within_seconds=deleted_at_tolerance_s. These are READ EXPECTATIONS, never DB mutations.
- "include_deleted" (5 keys): method "GET", endpoint=resource_endpoint,
  query=include_deleted_param, expected_status=200, assert_present_with_deleted_at=true.
- Keep {RESOURCE_ID} VERBATIM in every path_template; never substitute an id — the harness does.
- Every numeric field is a bare JSON number (never quoted), equal to the brief value.
- Output only the JSON object. Never send a request, contact a host, query a DB, time a
  delete, or state/guess any status code, body, count, deleted_at, or DB result — the harness executes the plan.
Always keep {RESOURCE_ID} a literal token inside each path_template (never substitute an id), always emit all seven top-level keys with create=3 / delete=3 / get_deleted=4 / collection=4 / db_query=8 / include_deleted=5 keys, treat every db_query assert_* key as an inert read expectation (never a DB mutation), and write every numeric field as a bare JSON number.
