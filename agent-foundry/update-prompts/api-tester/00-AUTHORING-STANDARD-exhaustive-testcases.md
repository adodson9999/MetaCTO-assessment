# Global Authoring Standard — Exhaustive Test-Case Generation (no verdict)

Applies to ALL 39 api-tester agents. Every agent's `## Change prompt` incorporates this standard via
its appended **## ADDENDUM (v2 — exhaustive test-case + reporting standard)** section. When you run an
agent through `update-agent`, pass the Change prompt AND its ADDENDUM together.

## 1. Role of the tester agent (what changes)

Each agent is a **pure, exhaustive test-case generator** in its lane. It is DIRECTED at runtime — it is
told the feature/endpoint and what to test — and it enumerates every testable angle as fully-detailed,
plain-language test cases.

**The tester makes NO bug judgement.** It authors the test case and the *Expected Result* (the definition
of correct behavior, drawn from the universal contract oracle and the feature spec it is given). It does
**not** decide pass/fail and does **not** emit deviations/findings/verdicts — a **separate judging agent**
executes the cases and determines whether an Actual Result is a bug.

Concretely:
- The tester fills every field EXCEPT `actual_result` and `status`.
- `actual_result` is left empty (placeholder: "TO BE FILLED DURING EXECUTION").
- `status` is set to `Not Executed` only. The judge/executor later sets `Pass | Fail | Blocked | Skipped`.
- The tester emits **no** `deviations[]`, `verdict`, `is_bug`, or pass/fail counts. (This supersedes the
  old contract-oracle "emit deviations" clause: the tester still SOURCES Expected Result from the
  contract oracle, but the comparison/verdict now belongs to the separate judge agent.)

Everything else is preserved: single JSON object output, feature-agnostic role-only references (never
hardcode a real URL/host/token), MECE lane ownership (only test what this lane owns per
`00-MECE-boundary-map.md`), and the code-review ≥85 self-awareness clause.

## 2. Exhaustive coverage mandate — "go wide, in lane"

For every feature/endpoint/field the agent is directed to test, it must enumerate cases across **all**
of these angles (exhaustively within the lane, still MECE across agents):

- **Happy path** — valid, typical, permitted, expected-success scenarios.
- **Negative path** — invalid, unauthorized, malformed, missing, forbidden, wrong-type, wrong-state.
- **Boundary** — min, min−1, max, max+1, empty, zero, one, first, last, just-under, just-over, exact-limit.
- **Edge cases** — nulls, unicode/homoglyph/whitespace, extreme sizes, encodings, rare-but-legal combos,
  concurrency/timing, ordering, idempotent replays, locale, precision — whatever is unusual for the lane.
- **Broad / combinatorial** — every documented field × method × relevant state; pairwise combinations
  where the input space is large; each enum value; each documented parameter.

Rule of thumb: if a competent human tester could construct a distinct, reportable case for a distinct
condition in this lane, the agent must emit it. Duplicates (within the agent or across agents) are not
allowed — coverage is exhaustive but each case is unique.

## 3. The test-case schema — every case carries ALL fields, in plain language, maximum detail

Emit ONE JSON object with a `test_cases[]` array. Each element MUST contain:

| Field | Meaning | Filled by |
|---|---|---|
| `test_case_id` | Unique, stable, prefixed per agent, e.g. `TC-AUTHZ-001` (zero-padded, sequential). | tester |
| `title` | Concise, descriptive name of the test's objective. | tester |
| `description` | Brief plain-language explanation of the scenario/angle being validated and why. | tester |
| `category` | One of: `happy` \| `negative` \| `boundary` \| `edge` \| `broad`. | tester |
| `feature_under_test` | The role of the feature/endpoint being exercised (feature-agnostic role, not a real URL). | tester |
| `preconditions` | The state/setup required before the test can run (e.g. "a resource owned by the caller exists"). | tester |
| `test_data` | The exact inputs/variables/credentials by role (e.g. "permitted_token", "field X = 256-char string"). | tester |
| `test_steps` | Sequential, detailed, reproducible steps a tester follows to execute the case. | tester |
| `expected_result` | The exact, measurable correct behavior (status, body invariants, read-back), sourced from the contract oracle / given spec. Definition of correct — NOT a verdict. | tester |
| `actual_result` | Observed behavior. **Leave empty**: `"TO BE FILLED DURING EXECUTION"`. | executor/judge |
| `status` | **Set to `Not Executed`.** Judge later sets `Pass`/`Fail`/`Blocked`/`Skipped`. | judge |
| `postconditions` | The state the system should be left in after the case completes. | tester |
| `severity_hint` | Reporting aid only (e.g. `critical`/`major`/`minor`) — the expected impact IF it failed. Not a verdict. | tester |
| `references` | The standard(s) grounding the expectation (RFC/OWASP/spec section). | tester |
| `tags` | Free tags for filtering (lane, bug-class, angle). | tester |

Preserve the agent's existing machine fields (e.g. `method`, `recipe.kind`, `endpoint_role`,
`expected_by_contract`, `leakage`) as sub-fields inside each case (e.g. under a `machine` key) so the
harness/judge still gets its structured inputs while humans get the readable case. Nothing is lost —
the human fields are additive.

Detail expectation: **the more detail the better.** Steps and Test Data must be specific enough that two
different people would execute the case identically and a reporter could cite it verbatim.

## 4. Test Case ID codes (per agent)

`TC-<CODE>-<NNN>` (zero-padded to 3+, sequential, stable across runs).

| Agent | CODE | Agent | CODE |
|---|---|---|---|
| test-authentication-flows | AUTHN | verify-caching-headers | CACHE |
| check-authorization-rules | AUTHZ | verify-content-type-negotiation | CONNEG |
| verify-third-party-oauth-integration | OAUTH | validate-api-versioning-behavior | VERSION |
| test-ip-allowlist-enforcement | IPALLOW | validate-retry-after-header-compliance | RETRYAFTER |
| verify-crud-operation-integrity | CRUD | test-rate-limit-enforcement | RATELIMIT |
| test-idempotency-of-endpoints | IDEM | test-timeout-handling | TIMEOUT |
| test-soft-delete-behavior | SOFTDEL | test-api-gateway-routing | GATEWAY |
| test-concurrent-request-handling | CONC | test-webhook-delivery | WEBHOOK |
| test-bulk-operation-endpoints | BULK | test-event-driven-api-triggers | EVENT |
| validate-search-and-filter-queries | SEARCH | test-long-polling-support | LONGPOLL |
| test-pagination-behavior | PAGE | test-file-upload-and-download | FILE |
| validate-query-parameter-handling | QPARAM | test-multipart-form-data-handling | MULTIPART |
| verify-sorting-behavior | SORT | test-ssl-tls-enforcement | TLS |
| validate-request-payloads | PAYLOAD | validate-graphql-depth-limits | GRAPHQL |
| validate-null-empty-fields | NULLEMPTY | verify-audit-log-generation | AUDIT |
| verify-enum-value-restrictions | ENUM | track-defect-density | DEFECT |
| verify-response-status-codes | STATUS | run-regression-suite | REGRESS |
| verify-error-message-clarity | ERRMSG | measure-api-consumer-satisfaction | CSAT |
| validate-json-schema-responses | SCHEMA | | |
| validate-header-propagation | HEADER | | |
| validate-correlation-id-propagation | CORRID | | |

## 5. Non-negotiables (quality bar)

- Plain, unambiguous language any tester can follow; no undefined jargon.
- Each case independently understandable and independently reportable.
- Deterministic and reproducible; feature-agnostic (roles only).
- Exhaustive in-lane coverage across all five angles; zero duplicate cases within or across agents.
- No verdict, no deviation, no pass/fail from the tester — Expected Result only; Status = `Not Executed`.
- Still a single JSON object; still passes the foundry's gates (code-review ≥85, MECE, golden regression).
