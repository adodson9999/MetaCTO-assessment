# Shared skill — search-and-filter-query test-plan construction

Collective (SkillClaw) pool for the api-tester / validate-search-and-filter-queries
workflow. Offered to all four agents; adoption is the user's call (never auto-adopted).
Local filesystem only — air-gapped.

## Distilled lessons (cross-agent)

A high-fidelity filter test plan reproduces every gold (collection × scenario) token.
The recurring ways a weaker plan loses fidelity, and the guardrail for each:

- **Collapsing or dropping a case.** Always emit all five cases in order:
  `single_filter`, `multi_filter`, `invalid_value`, `unknown_param`, `empty_result`.
- **Degrading the multi-filter to one filter.** `multi_filter` must carry BOTH
  `status=active` and `category=A` so the AND-of-two-filters path is exercised and the
  category-B records are verifiably excluded.
- **"Fixing" the invalid value.** `invalid_value` must keep `status` exactly
  `unknown_value` (out of the documented enum) so the 400-referencing-"status" path is
  triggered — never substitute a valid value.
- **Swapping the unknown parameter.** `unknown_param` must keep the name exactly
  `bogus_filter` (value `x`) — never a server-control key — so the documented strict
  unknown-parameter policy is exercised.
- **Expecting 404 for the empty result.** `empty_result` is `status=active` +
  `category=C`; the contract returns 200 with an empty list, not a 404.
- **Literal string values.** Every params value is a JSON string with double quotes,
  never a number/boolean/null.
- **No fabrication.** Emit only the plan; never send a request or guess a status
  code, count, or which records match — the harness executes and records.
