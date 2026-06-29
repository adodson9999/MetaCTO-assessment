# best_skill — concurrent-request-handling test-plan generation

Seed skill (debate-gated APPROVED_PROMPT is the source of truth). SkillOpt may stage
bounded edits here behind the held-out Concurrency-Test Fidelity gate; never auto-adopted.

Operating rules distilled from the gated prompt:
- Emit ONE JSON object with exactly three keys: "read", "write", "assert_zero_500"=true.
- "read": exactly six keys — label "concurrent_read", method "GET", endpoint copied
  from the brief, integer concurrency, integer expected_status, assert_identical_bodies=true.
- "write": exactly twelve keys — label "concurrent_write", method "POST", endpoint
  from the brief, integer concurrency, integer expected_status, test_id_field +
  test_id_template from the brief, vu_start=1, vu_end=concurrency,
  assert_count_delta=concurrency, assert_zero_duplicates=true, assert_zero_missing=true.
- Copy test_id_template VERBATIM including the literal [VU_ID]; never expand or replace it.
- Every numeric field is a bare JSON integer (never quoted), equal to the brief value
  (or literal 1 for vu_start).
- Output only the JSON object. Never send a request, contact a host, query a DB, or
  state/guess any status code, body, count, or DB result — the harness executes the plan.
Always keep test_id_template a single literal string containing [VU_ID] (never expand or replace it), always emit exactly six read keys and exactly twelve write keys including assert_count_delta / assert_zero_duplicates / assert_zero_missing, and write every numeric field as a bare JSON integer.
