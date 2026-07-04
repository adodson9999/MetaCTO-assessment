# update-agent: api-tester-verify-response-status-codes

## Invocation
```
update-agent api-tester-verify-response-status-codes "<CHANGE PROMPT below>"
```

## Change prompt (verbatim, exhaustive)

Expand this agent's lane to the complete RFC 9110 residual status-code universe it solely owns — every documented status code and method-level status semantic for which NO sibling agent is the reserved owner — while keeping it a pure status-CODE-value conformance bug-finder that emits ONE JSON object whose `descriptors` array holds exactly one request descriptor per OWNED status/semantic, each descriptor deterministically TRIGGERING that code from the runtime-supplied documented surface (never asserting the actual returned status — the deterministic harness records `observed`), feature-agnostic (refer to every input only by role: target_endpoint, item_endpoint, create_endpoint, search_endpoint, update_endpoint, redirect_endpoint, precondition_endpoint; never assume, hardcode, name, or mention any URL/path/host/resource/feature), with `expected_by_contract` taken ONLY from `references/contract-oracle.md` (the "Status semantics" and "Validation" rows — documented code returned exactly, success != error, 2xx bodies are not error envelopes), and preserving all existing invariants below.

Mirror this agent's own golden.json descriptor schema EXACTLY for every new case: each descriptor object has `role` (string), `endpoint_role` (string), `method` (string), `status` (integer — the documented OWNED code it deterministically triggers), `trigger` (object `{ "kind": "<KIND from closed vocab>" }`), `also_accept` (array of integers), and `assert_header` (string, present ONLY on descriptors that mandate a response header). Keep the top-level object shape identical: `agent`, `lane`, `descriptors`, `out_of_scope` (null when in-lane), `baseline` (`{ "metric": "status_code_conformance_fidelity", "value": 1.0 }`).

KEEP the 8 existing descriptors unchanged (success_read/200/valid_read, created/201/valid_create/also_accept:[200], bad_request/400/malformed_body, not_found/404/nonexistent_item_id, method_not_allowed/405/unsupported_method/assert_header:"Allow", conflict/409/duplicate_conflict, unprocessable/422/unprocessable_body, server_error/500/induce_server_error).

ADD the following NEW descriptors, grouped by class, each with ALL golden-schema fields spelled out:

Class 2xx-non-201 success (success != error envelope; 2xx body is not an error shape):
- role `accepted`, endpoint_role `create_endpoint`, method `POST`, status `202`, trigger `{ "kind": "async_accepted" }`, also_accept `[]` — async-accepted work; assert body is not an error envelope.
- role `no_content`, endpoint_role `item_endpoint`, method `DELETE`, status `204`, trigger `{ "kind": "valid_delete" }`, also_accept `[200]` — assert empty body (no payload on 204).
- role `created_location`, endpoint_role `create_endpoint`, method `POST`, status `201`, trigger `{ "kind": "valid_create" }`, also_accept `[]`, assert_header `Location` — 201 MUST carry a Location for the new resource (distinct from the existing `created` which asserts the code alone).

Class 3xx redirection (Location present; method preservation):
- role `moved_permanently`, endpoint_role `redirect_endpoint`, method `GET`, status `301`, trigger `{ "kind": "moved_resource" }`, also_accept `[308]`, assert_header `Location`.
- role `found`, endpoint_role `redirect_endpoint`, method `GET`, status `302`, trigger `{ "kind": "temporary_redirect" }`, also_accept `[307]`, assert_header `Location`.
- role `see_other`, endpoint_role `create_endpoint`, method `POST`, status `303`, trigger `{ "kind": "post_redirect_get" }`, also_accept `[]`, assert_header `Location` — POST-redirect-GET; method changes to GET.
- role `temporary_redirect`, endpoint_role `redirect_endpoint`, method `POST`, status `307`, trigger `{ "kind": "temporary_redirect_preserve_method" }`, also_accept `[]`, assert_header `Location` — method + body MUST be preserved on redirect.
- role `permanent_redirect`, endpoint_role `redirect_endpoint`, method `POST`, status `308`, trigger `{ "kind": "permanent_redirect_preserve_method" }`, also_accept `[]`, assert_header `Location` — method + body MUST be preserved.

Class 4xx residual (codes no sibling owns):
- role `gone`, endpoint_role `item_endpoint`, method `GET`, status `410`, trigger `{ "kind": "gone_resource" }`, also_accept `[404]` — permanently removed resource.
- role `precondition_failed`, endpoint_role `precondition_endpoint`, method `PUT`, status `412`, trigger `{ "kind": "failed_precondition" }`, also_accept `[]` — unmet If-Match/If-Unmodified-Since (code semantics only; caching-header mechanics are verify-caching-headers').
- role `precondition_required`, endpoint_role `precondition_endpoint`, method `PUT`, status `428`, trigger `{ "kind": "missing_precondition" }`, also_accept `[]` — conditional-request-required unconditional write.
- role `request_header_fields_too_large`, endpoint_role `target_endpoint`, method `GET`, status `431`, trigger `{ "kind": "oversize_request_headers" }`, also_accept `[400]`.

Class 5xx residual:
- role `service_unavailable`, endpoint_role `target_endpoint`, method `GET`, status `503`, trigger `{ "kind": "induce_service_unavailable" }`, also_accept `[]` — assert 503 body does not leak internal detail (code-level presence only; message-wording/leak wording is verify-error-message-clarity's, Retry-After header is validate-retry-after-header-compliance's).

Class method semantics (status + method-shape, no code sibling owns):
- role `head_no_body`, endpoint_role `item_endpoint`, method `HEAD`, status `200`, trigger `{ "kind": "head_request" }`, also_accept `[]` — HEAD returns the same status/headers as GET but MUST have an empty body.
- role `options_allow`, endpoint_role `target_endpoint`, method `OPTIONS`, status `200`, trigger `{ "kind": "options_request" }`, also_accept `[204]`, assert_header `Allow` — OPTIONS MUST enumerate supported methods in Allow.

New recipe/trigger KINDs added to the CLOSED trigger vocabulary (in addition to the existing valid_read, valid_create, malformed_body, nonexistent_item_id, unsupported_method, duplicate_conflict, unprocessable_body, induce_server_error): `async_accepted`, `valid_delete`, `moved_resource`, `temporary_redirect`, `post_redirect_get`, `temporary_redirect_preserve_method`, `permanent_redirect_preserve_method`, `gone_resource`, `failed_precondition`, `missing_precondition`, `oversize_request_headers`, `induce_service_unavailable`, `head_request`, `options_request`. No trigger kind outside this closed list may ever be emitted.

New assert_header values added to the closed header-assertion set: `Location` (on 201/301/302/303/307/308) and `Allow` (on 405 and OPTIONS/200), in addition to the existing `Allow` on 405.

REMOVE / never emit (route to sibling owner, cite it): 401 missing/invalid-auth (owned by api-tester-test-authentication-flows); 403 insufficient-permission (owned by api-tester-check-authorization-rules); 406 not-acceptable and 415 unsupported-media-type (owned by api-tester-verify-content-type-negotiation); 429 throttled (owned by api-tester-test-rate-limit-enforcement); the Retry-After header on 429/503 (owned by api-tester-validate-retry-after-header-compliance — this agent asserts the 503 CODE only, never its Retry-After header); ETag/If-None-Match/304/If-Match caching-header mechanics (owned by api-tester-verify-caching-headers — this agent asserts the 412 CODE only, never the conditional-header math); error-MESSAGE wording, envelope shape, and internal-detail-leak checks on any 4xx/5xx body (owned by api-tester-verify-error-message-clarity); response-BODY schema/typing/additionalProperties validation of any 2xx/4xx/5xx body (owned by api-tester-validate-json-schema-responses). On out-of-lane input emit a single out-of-lane error sentinel naming the owning sibling in `out_of_scope` and nothing else.

PRESERVE all invariants: emit exactly ONE JSON object and nothing else (no prose, no extra/renamed keys); emit request descriptors only — never a real response, status, body, header value, timing, count, or verdict, and never a network call (a separate deterministic harness builds, sends, and records `observed`); never assert the actual returned status; feature-agnostic role-only references with fail-closed out-of-scope when no surface is provided; echo runtime-supplied endpoint paths, header names, and field names byte-for-byte with no normalization/substitution; `expected_by_contract` sourced ONLY from contract-oracle.md, never from the target's docs or observed behaviour; never carry an `also_accept` that swallows a standard code the contract fixes (e.g. never admit 200 for a creation the contract fixes at 201 as the primary — 201 stays primary); confine all file access to FORGE_WORKSPACE; comply with Articles G1–G11 of the authoring standard; retain the self-awareness/code-review clause (all produced code is reviewed by every agent in agents/code-review/ and must score ≥85, looping until it does).

New total descriptor count: 25 (8 existing + 17 new).

## Research basis
- RFC 9110 (HTTP Semantics, Jun 2022) §15: 2xx (202 Accepted, 204 No Content — no body), 3xx (301/302/303/307/308; Location required; 307/308 MUST preserve method + body, 303 forces GET, 301/302 historically method-changing), 4xx residual (410 Gone, 412 Precondition Failed, 428 Precondition Required, 431 Request Header Fields Too Large), 5xx (503 Service Unavailable). Source: datatracker.ietf.org/doc/html/rfc9110, rfc-editor.org/info/rfc9110.
- RFC 9110 §15.5.6 / MDN 405: a 405 response MUST include Allow enumerating supported methods; OPTIONS returns Allow; HEAD returns identical status/headers to GET with an empty body. Sources: developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Status/405, blog.postman.com/http-error-405.
- Contract-oracle.md "Status semantics" and "Validation" rows: documented code returned exactly; success != error; 2xx bodies are not error envelopes; never 5xx on a well-formed request.

## Gap summary
Current agent covered only 8 codes (200/201/400/404/405/409/422/500). Missing from its owned residual universe: 202, 204, 201-Location assertion, 301/302/303/307/308 (+Location, +method preservation), 410, 412, 428, 431, 503, and the HEAD/OPTIONS method-shape semantics. 17 new descriptors close the gap.

## De-dup notes
- Split by ASPECT per §Boundary map: this agent owns the status CODE VALUE + mandated status-line headers (Location/Allow) only.
- 401/403/406/415/429 explicitly excluded and routed to their reserved owners (auth-flows, authorization-rules, content-type-negotiation, rate-limit-enforcement).
- 412 CODE kept here, but If-Match/If-None-Match/304 conditional-header MATH handed to verify-caching-headers.
- 503 CODE kept here, but its Retry-After header handed to validate-retry-after-header-compliance and its message/leak wording to verify-error-message-clarity.
- No error-message wording or response-body schema cases added (siblings own those aspects). No unassigned classes surfaced — all new cases fall inside the residual-status lane.

## ADDENDUM (v2 — exhaustive test-case + reporting standard)

When running update-agent for this agent, pass the Change prompt above AND this ADDENDUM together as a single change prompt.

**No-verdict role.** This agent is now a pure, exhaustive test-case generator in its lane. It authors every case and fills the Expected Result (the definition of correct behavior, sourced from the contract oracle and the given spec). It does NOT execute, does NOT judge, and emits NO deviations, verdicts, or pass/fail. For every case it sets `actual_result` = "TO BE FILLED DURING EXECUTION" and `status` = `Not Executed`; a separate judge agent later executes the case, fills the actual result, and decides whether it is a bug. This section is governed by `00-AUTHORING-STANDARD-exhaustive-testcases.md`.

**Test Case ID prefix:** `TC-STATUS-NNN` (zero-padded, sequential, stable across runs).

**Render every case in the human-readable schema.** In addition to the machine descriptors above, emit each test case with ALL of these human fields, in plain language, maximum detail: `test_case_id`, `title`, `description`, `category` (`happy`|`negative`|`boundary`|`edge`|`broad`), `feature_under_test`, `preconditions`, `test_data`, `test_steps`, `expected_result`, `actual_result` (="TO BE FILLED DURING EXECUTION"), `status` (=`Not Executed`), `postconditions`, `severity_hint`, `references`, `tags`. Keep this agent's existing machine fields (`role`, `endpoint_role`, `method`, `status`, `trigger`, `also_accept`, `assert_header`, `expected_by_contract`) under a `machine` key on each case. Emit ONE JSON object with a `test_cases[]` array carrying every case.

**Lane-specific exhaustive coverage checklist (ASPECT = status CODE VALUE + mandated status-line headers Location/Allow only; 401/403/406/415/429 are siblings').**
- Happy: 200 valid read; 201 create carrying Location; 202 async-accepted (body not an error envelope); 204 delete/no-content with empty body; HEAD returns GET's status/headers with empty body; OPTIONS 200/204 enumerating Allow.
- Negative: 400 malformed body; 404 nonexistent id; 405 unsupported method (+Allow header enumerating supported methods); 409 duplicate conflict; 410 gone resource; 422 unprocessable body; 500 induced server error (code presence only).
- Boundary: 431 oversize request headers (also_accept 400); 412 unmet precondition vs 428 precondition-required (conditional-write with/without the precondition); the exact 201-vs-200 primary line where the contract fixes creation at 201; 405 exactly on the one unsupported method while siblings stay allowed.
- Edge: 301/302/303/307/308 redirect family — Location present, 307/308 preserve method+body, 303 forces GET, 301/302 historically method-changing; 503 body must not leak internal detail (code-level presence only); HEAD-vs-GET header parity with empty body.
- Broad: one descriptor per OWNED residual code across the documented method surface; each redirect code × its method-preservation rule; every status-line header assertion (Location on 201/301/302/303/307/308, Allow on 405 + OPTIONS) enumerated as a distinct case.
- Sibling owners for adjacent concerns: 401 → test-authentication-flows; 403 → check-authorization-rules; 406/415 → verify-content-type-negotiation; 429 → test-rate-limit-enforcement; Retry-After on 429/503 → validate-retry-after-header-compliance; error-message wording/leak → verify-error-message-clarity; response-body schema → validate-json-schema-responses; 412 conditional-header math → verify-caching-headers.

Coverage exhaustive in-lane, MECE across agents — no duplicate cases.
