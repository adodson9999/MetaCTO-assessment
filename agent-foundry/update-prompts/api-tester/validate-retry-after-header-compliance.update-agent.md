# update-agent: api-tester-validate-retry-after-header-compliance

## Invocation
```
update-agent api-tester-validate-retry-after-header-compliance "<CHANGE PROMPT below>"
```

## Change prompt (verbatim, exhaustive)

Expand this agent's lane to the COMPLETE Retry-After contract it SOLELY owns per RFC 9110 §10.2.3 (Retry-After) — presence on BOTH 429 and 503 throttle/overload responses, both wire forms (integer-seconds AND RFC 7231/9110 IMF-fixdate HTTP-date), deadline-anchored honoring, a sane upper bound, and correct handling of the degenerate values (zero, negative, past-date) — while keeping it a pure Retry-After bug-finder that emits ONE JSON object whose `cases` array holds Retry-After cases only, feature-agnostic (refer to every input only by role: the rate-limited endpoint, the maintenance/overload endpoint, the documented Retry-After header forms, the documented limit and window, the documented reasonable-maximum bound; never assume, hardcode, name, or mention any URL/path/host/resource/feature), with `expected_class` taken ONLY from `references/contract-oracle.md` ("Headers" row — Retry-After present & correct; "Status semantics" row — documented code exactly), and preserving all existing invariants below.

Mirror this agent's own golden.json case schema EXACTLY for every new case: each case object has `label` (string from the closed label set), `endpoint_role` (string, `rate_limited_endpoint` or `maintenance_endpoint`), `method` (string), `recipe` (object `{ "kind": "<KIND from closed vocab>", ... }`), `expected_class` (string), `also_accept` (array), and a maximally granular `steps` array (array of observable-substep strings). Keep the top-level object shape identical: `agent`, `lane`, `cases`, `out_of_scope` (null when in-lane), `baseline` (`{ "metric": "retry_after_accuracy", "value": 1.0 }`).

KEEP the 7 existing cases unchanged (over-limit-429-carries-retry-after, probe-one-second-before-deadline-still-limited, probe-one-second-after-deadline-succeeds, retry-after-seconds-integer-form-honored, retry-after-http-date-form-honored, maintenance-503-advertises-retry-after, retry-after-within-reasonable-maximum).

ADD the following NEW cases, grouped by class, each with ALL golden-schema fields spelled out:

Class presence-required-on-throttle (RFC 9110 §10.2.3 SHOULD; a throttle without Retry-After is a client-blind deviation):
- label `throttle-without-retry-after-is-deviation`, endpoint_role `rate_limited_endpoint`, method `GET`, recipe `{ "kind": "over_limit_burst" }`, expected_class `429`, also_accept `[]`, steps: `["send an at-limit burst up to the documented limit","send one more over-limit request","assert the over-limit request returns 429","assert a Retry-After header is present on the 429 (its absence on a throttle is a deviation)"]`.

Class 503 wire-form parity (a maintenance/overload 503 must carry Retry-After in a parseable form — both seconds and HTTP-date):
- label `maintenance-503-retry-after-seconds-form`, endpoint_role `maintenance_endpoint`, method `GET`, recipe `{ "kind": "maintenance_state" }`, expected_class `503`, also_accept `[]`, steps: `["drive the endpoint into a documented maintenance/overload state","assert it returns 503","assert the 503 Retry-After, when in seconds form, parses as a non-negative integer"]`.
- label `maintenance-503-retry-after-http-date-form`, endpoint_role `maintenance_endpoint`, method `GET`, recipe `{ "kind": "http_date_form" }`, expected_class `503`, also_accept `[]`, steps: `["drive the endpoint into a documented maintenance/overload state advertising an HTTP-date Retry-After","assert it returns 503","assert the Retry-After parses as a valid RFC 7231 IMF-fixdate in the future"]`.

Class degenerate-value handling (RFC 9110 §10.2.3 — Retry-After is a delay-seconds non-negative integer or a future HTTP-date; zero / negative / past-date are malformed or immediate-retry, and must not mislead the client):
- label `retry-after-zero-means-retry-now`, endpoint_role `rate_limited_endpoint`, method `GET`, recipe `{ "kind": "degenerate_retry_after_value", "value_form": "zero_seconds" }`, expected_class `429`, also_accept `[]`, steps: `["trigger a 429 whose Retry-After is 0","assert 0 is a valid non-negative integer (retry immediately)","send a probe immediately after","assert the probe outcome is consistent with an immediate-retry semantics (not still-limited far beyond the window)"]`.
- label `retry-after-negative-is-malformed`, endpoint_role `rate_limited_endpoint`, method `GET`, recipe `{ "kind": "degenerate_retry_after_value", "value_form": "negative_seconds" }`, expected_class `429`, also_accept `[]`, steps: `["capture a 429 Retry-After value","assert the advertised delay is NOT a negative integer (a negative Retry-After is a malformed-header deviation)"]`.
- label `retry-after-past-date-is-malformed`, endpoint_role `rate_limited_endpoint`, method `GET`, recipe `{ "kind": "degenerate_retry_after_value", "value_form": "past_http_date" }`, expected_class `429`, also_accept `[]`, steps: `["capture a 429 Retry-After in HTTP-date form","assert the advertised date is NOT in the past relative to the response Date (a past Retry-After date is a malformed/misleading-header deviation)"]`.

Class monotonic-honoring across forms (both wire forms must anchor to the SAME real deadline — a seconds value and an equivalent HTTP-date honor identically):
- label `both-forms-anchor-same-deadline`, endpoint_role `rate_limited_endpoint`, method `GET`, recipe `{ "kind": "deadline_anchored_probe", "offset_seconds": 1 }`, expected_class `2xx`, also_accept `["201","202","204"]`, steps: `["trigger a 429 and read the advertised Retry-After in whichever form is documented","compute the absolute deadline from that form (seconds added to response Date, or the HTTP-date directly)","wait until one second after the computed deadline","send a probe","assert the probe now succeeds, confirming the form was honored to the correct absolute instant"]`.

New recipe KINDs added to the CLOSED recipe vocabulary (in addition to the existing over_limit_burst, deadline_anchored_probe, seconds_integer_form, http_date_form, maintenance_state, reasonable_maximum_bound): `degenerate_retry_after_value` (carrying `value_form` ∈ {`zero_seconds`, `negative_seconds`, `past_http_date`}). No recipe kind or value_form outside these closed lists may ever be emitted; echo runtime-provided endpoint role names, header names, and field names byte-for-byte.

REMOVE / never emit (route to sibling owner, cite it): LIMIT COUNTING — at-limit vs over-limit tallying as a rate-count assertion, WINDOW RESET timing as a limit-window property, PER-KEY / per-scope isolation, and the RateLimit-Limit / RateLimit-Remaining / RateLimit-Reset header MATH (all owned by api-tester-test-rate-limit-enforcement — this agent uses the burst only to PROVOKE a 429 that must carry Retry-After, never to assert the count/window/isolation itself); the bare 429/503 STATUS-CODE-value conformance divorced from the Retry-After header (owned by api-tester-verify-response-status-codes — this agent asserts the Retry-After HEADER on those codes, the status-code agent asserts the residual 503 CODE only); the 503 error-body wording / internal-leak (owned by api-tester-verify-error-message-clarity). On out-of-lane input emit a single out-of-lane error sentinel naming api-tester-test-rate-limit-enforcement (or the relevant sibling) in `out_of_scope` and nothing else.

PRESERVE all invariants: emit exactly ONE JSON object and nothing else (no prose, no extra/renamed keys); emit probe recipes only — never a real request, header value, retry-seconds duration, HTTP-date, or network call (a separate deterministic harness drives each probe at real wall-clock timing, reads the real Retry-After header, computes the deadline, and records the real response); feature-agnostic role-only references with fail-closed out-of-scope when no Retry-After surface is provided; echo runtime-provided endpoint/header/field names byte-for-byte with no normalization/substitution; `expected_class` sourced ONLY from contract-oracle.md; never carry an `also_accept` that swallows a standard code the contract fixes (429/503 stay primary); confine all file access to FORGE_WORKSPACE / FORGE_SANDBOX_ROOT and send no HTTP request or side effect; comply with Articles G1–G11; retain the self-awareness/code-review clause (all produced code is reviewed by every agent in agents/code-review/ and must score ≥85, looping until it does).

New total case count: 14 (7 existing + 7 new).

## Research basis
- RFC 9110 §10.2.3 (Retry-After): a response MAY send Retry-After on 503 (Service Unavailable) or any 3xx/429; value is either a non-negative delay-seconds integer or an RFC 7231 IMF-fixdate HTTP-date in the future; used by the client to decide how long to wait before retrying. Source: rfc-editor.org/rfc/rfc9110.html.
- RFC 7231 §7.1.1.1 / RFC 9110 §5.6.7 (HTTP-date IMF-fixdate form). Retry-After SHOULD accompany a throttle/overload so clients back off correctly; degenerate values (negative, past-date) are malformed; zero means retry immediately.
- contract-oracle.md "Headers" row (Retry-After present & correct) and "Status semantics" row (documented 429/503 exactly).

## Gap summary
Original 7 cases covered 429-carries-Retry-After, before/after-deadline probes, seconds & HTTP-date forms honored, 503-advertises-Retry-After, and reasonable-maximum bound. Missing: presence-REQUIRED-on-throttle (absence-is-deviation), 503 wire-form PARITY (seconds AND HTTP-date on the 503), degenerate-value handling (zero=retry-now, negative=malformed, past-date=malformed), and cross-form same-deadline honoring. 7 new cases close the Retry-After compliance gap.

## De-dup notes
- Sole owner of Retry-After per §Boundary map and coverage-manifest; every new case stays strictly on the Retry-After header's presence/form/value/honoring.
- Limit COUNTING, WINDOW reset, per-key isolation, and RateLimit-* header math explicitly routed to test-rate-limit-enforcement (the burst here only PROVOKES the 429).
- Bare 429/503 code-value conformance stays with verify-response-status-codes; 503 body wording with verify-error-message-clarity.
- No rate-count, no window-reset, no RateLimit-* header, and no error-wording cases added.

## ADDENDUM (v2 — exhaustive test-case + reporting standard)

When running update-agent for this agent, pass the Change prompt above AND this ADDENDUM together as a single change prompt.

**No-verdict role.** This agent is now a pure, exhaustive test-case generator in its lane. It authors every case and fills the Expected Result (the definition of correct behavior, sourced from the contract oracle and the given spec). It does NOT execute, does NOT judge, and emits NO deviations, verdicts, or pass/fail. For every case it sets `actual_result` = "TO BE FILLED DURING EXECUTION" and `status` = `Not Executed`; a separate judge agent later executes the case, fills the actual result, and decides whether it is a bug. This section is governed by `00-AUTHORING-STANDARD-exhaustive-testcases.md`.

**Test Case ID prefix:** `TC-RETRYAFTER-NNN` (zero-padded, sequential, stable across runs).

**Render every case in the human-readable schema.** In addition to the machine `cases` above, emit each test case with ALL of these human fields, in plain language, maximum detail: `test_case_id`, `title`, `description`, `category` (`happy`|`negative`|`boundary`|`edge`|`broad`), `feature_under_test`, `preconditions`, `test_data`, `test_steps`, `expected_result`, `actual_result` (="TO BE FILLED DURING EXECUTION"), `status` (=`Not Executed`), `postconditions`, `severity_hint`, `references`, `tags`. Keep this agent's existing machine fields (`label`, `endpoint_role`, `method`, `recipe`, `expected_class`, `also_accept`, `steps`) under a `machine` key on each case. Emit ONE JSON object with a `test_cases[]` array carrying every case.

**Lane-specific exhaustive coverage checklist (ASPECT = Retry-After value/format/honoring only; rate-limit counting and the bare 429/503 code value are siblings').**
- Happy: an over-limit 429 carries a Retry-After header; a maintenance/overload 503 advertises Retry-After; Retry-After in integer-seconds form is honored; Retry-After in RFC 7231 IMF-fixdate HTTP-date form is honored.
- Negative: a throttle 429 WITHOUT any Retry-After is a client-blind deviation; a negative-seconds Retry-After is malformed; a past-dated HTTP-date Retry-After is malformed/misleading.
- Boundary: a probe one second BEFORE the advertised deadline is still limited; a probe one second AFTER the deadline succeeds; Retry-After is within the documented reasonable-maximum bound; Retry-After = 0 means retry-now (valid non-negative integer) with a consistent immediate-retry probe outcome.
- Edge: both wire forms anchor to the SAME absolute deadline — a seconds value and an equivalent HTTP-date honor identically (compute the deadline, wait one second past it, probe succeeds); the exact deadline instant edge.
- Broad: 503 wire-form PARITY — the 503 carries Retry-After parseable in seconds form AND in future-HTTP-date form; each degenerate value_form (zero_seconds, negative_seconds, past_http_date) enumerated as its own case; presence asserted on BOTH 429 and 503.
- Sibling owners for adjacent concerns: LIMIT COUNTING (at-limit vs over-limit tally), WINDOW reset timing, per-key/scope isolation, and RateLimit-Limit/Remaining/Reset header MATH → test-rate-limit-enforcement (the burst here only PROVOKES the 429); the bare 429/503 STATUS-CODE-value conformance divorced from the Retry-After header → verify-response-status-codes; the 503 error-body wording / internal-leak → verify-error-message-clarity.

Coverage exhaustive in-lane, MECE across agents — no duplicate cases.
