# Shared skill — audit-log-generation verification plan construction (api-tester)

Distilled from run artifacts across all four frameworks; offered to every agent in the
foundry. Adoption is the user's call (never auto-adopted).

- Build exactly three operations in order — create {POST /<collection>/add, body
  {"title":"audit-probe"}, action_type CREATE, expect_status [201]}, update {PUT
  /<collection>/{resource_id}, body {"title":"audit-probe-updated"}, action_type UPDATE,
  expect_status [200]}, delete {DELETE /<collection>/{resource_id}, body null,
  action_type DELETE, expect_status [200,204]}. Use the LITERAL token "{resource_id}" in
  the update/delete paths — the executor substitutes the id the create returned; never
  invent or guess an id.
- Build one audit_query with all seven keys: filter_user_id = the brief's test_user_id,
  window_before_seconds 5, window_after_seconds 10, expected_entry_count 3,
  required_fields ["user_id","action_type","resource_id","timestamp","ip_address"],
  timestamp_tolerance_seconds 5, action_types ["CREATE","UPDATE","DELETE"]. The query is
  what turns three operations into a 3-entry audit assertion — never drop a required
  field or widen the window.
- The plan never sends a request, never logs in, and never guesses a status, body,
  resource id, or audit entry — the deterministic harness authenticates, executes,
  captures the target's log, and queries it. A fabricated audit entry is the
  catastrophic failure the gate forbids.
- Emit one valid JSON object per collection and nothing else — a missing or unparseable
  plan scores every scenario for that collection as 'missing' (zero fidelity there).
- Known target finding (DummyJSON): there is NO audit-log system, so Audit Log Coverage
  Rate = 0%; the winston request-log has timestamp + ip but no user_id/action_type/
  resource_id. A correct plan still scores high fidelity by faithfully reproducing that
  0% finding — the test is right even though the API fails it.
