# Shared skill — api-tester / validate-query-parameter-handling (SkillClaw pool)

Collective, cross-agent skill for the query-parameter-handling workflow. Offered to
all four agents (langgraph, crewai, claude_sdk, api-tester-validate-query-parameter-handling);
adoption is staged for the user's review — never auto-adopted.

Distilled reinforcement (the failure modes most worth guarding against):

- Always emit all nine cases in the fixed order; never drop the missing_required_q
  search probe or collapse it into a wrong-type probe — an absent required parameter
  is a distinct condition from a present-but-wrong one.
- Keep every params value and filter_value a literal JSON string (never normalise
  "5" to the number 5 or "NOT_A_VALID_VALUE" to a valid enum value).
- Pair the bad-enum order probe with sortBy="id" so the enum is actually validated
  (an order value without sortBy is silently ignored by the target).
- For each valid case, carry the matching filter/filter_value so the harness can
  verify the parameter's filter effect record-by-record (count <= limit, projected
  keys subset of {id}, ids sorted descending).
- The undocumented-parameter probe tests the documented ignore-unknown policy; emit
  it as type "undocumented" with exactly {"unexpected_param": "test123"}.
