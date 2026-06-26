# Shared skill — GraphQL query-depth-limit test-plan construction

Collective (SkillClaw) pool for the api-tester / validate-graphql-depth-limits
workflow. Offered to all four agents; adoption is the user's call (never auto-adopted).
Local filesystem only — air-gapped.

## Distilled lessons (cross-agent)

A high-fidelity depth test plan reproduces every gold (endpoint × scenario) token.
The recurring ways a weaker plan loses fidelity, and the guardrail for each:

- **Dropping or collapsing a probe.** Always emit all four cases in order:
  `depth_3`, `at_limit`, `one_over`, `deep_15`.
- **Mis-deriving the boundary depths.** `at_limit` depth MUST equal `max_depth`
  exactly, and `one_over` depth MUST equal `max_depth + 1` exactly — these two
  derivations are the whole point of the test. Setting `at_limit` below the limit or
  `one_over` far above it hides off-by-one depth-limit bugs.
- **Flipping an accept to a reject (or vice versa).** `depth_3` and `at_limit` are
  `accept` (depth ≤ max → 200 + non-null data, no errors); `one_over` and `deep_15`
  are rejects (depth > max → 400 + an `errors` array whose message mentions "depth" or
  "complexity").
- **Mis-measuring "depth".** Depth is the count of nested field selection sets, never a
  character count or token count. Each depth is a single integer (3 / max_depth /
  max_depth+1 / 15), never a string, float, or array.
- **Turning the deep probe into the DoS.** `deep_15` is exactly depth 15 — never an
  unbounded or megabyte depth. Its `reject_timed` type asserts the rejection arrives in
  under one second (the depth check must run before any expensive resolution).
- **No fabrication.** Emit only the plan; never hand-write a GraphQL query, send a
  request, or guess a status code, accept/reject outcome, or response time — the
  harness builds each query at the requested depth, sends it read-only, and records.
