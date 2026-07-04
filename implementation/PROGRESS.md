# PROGRESS — implementation plans (one at a time)

The one-at-a-time runner (`RUN-ONE.md`) reads this ledger, completes the first pending plan, and
updates its row. Status key: `[ ]` pending · `[~] in progress` · `[x] done`.

When a plan is completed, replace its `[ ]` with `[x]` and append ` — <date> · score <before>→<after> · code-review min <n> · test pass`.
If a plan hard-halts, set it to `[~]` and append ` — HALTED <date>: <reason>`.

| # | Plan (run in this order) | Status |
|---|--------------------------|--------|
| 1 | api-tester-test-authentication-flows | [x] FUNCTIONAL DONE 2026-07-01 · 11-case prompt, golden, guardrails, standard+runtime clauses; Section-3 contract test 7/7; all unit suites pass. Code-review hardening 252/266 denoised (best-of-5) + dispatchers round-6 done; final receipt DEFERRED per user (stop code-review, do functional impl of rest). |
| 2 | api-tester-check-authorization-rules | [x] FUNCTIONAL 2026-07-01 · 12-case authz matrix, 11/11 Section-3 + update-agent authoring-gated (verify_build PASS, slop 95); code-review+execution-judge deferred |
| 3 | api-tester-verify-crud-operation-integrity | [x] FUNCTIONAL 2026-07-01 · CRUD ordered-steps plan, 8/8 Section-3 + update-agent authoring-gated (verify_build PASS, slop 95); code-review+execution-judge deferred |
| 4 | api-tester-test-idempotency-of-endpoints | [x] FUNCTIONAL 2026-07-01 · 4-case idempotency (PUT/DELETE replay + POST + key-conflict), 11/11 + update-agent authoring-gated (verify_build PASS, slop 95); code-review+execution-judge deferred |
| 5 | api-tester-test-soft-delete-behavior | [x] FUNCTIONAL 2026-07-01 · 4-case soft-delete semantics, 6/6 + update-agent authoring-gated (verify_build PASS, slop 95); code-review+execution-judge deferred |
| 6 | api-tester-validate-search-and-filter-queries | [x] FUNCTIONAL 2026-07-01 · 5-case search/filter, 5/5 + update-agent authoring-gated (verify_build PASS, slop 95); code-review+execution-judge deferred |
| 7 | api-tester-test-pagination-behavior | [x] FUNCTIONAL 2026-07-01 · 10-case pagination, 8/8 + update-agent authoring-gated (verify_build PASS, slop 95); code-review+execution-judge deferred |
| 8 | api-tester-validate-query-parameter-handling | [x] FUNCTIONAL 2026-07-01 · 8-case query-param mechanics, 5/5 + update-agent authoring-gated (verify_build PASS, slop 95); code-review+execution-judge deferred |
| 9 | api-tester-validate-request-payloads | [x] FUNCTIONAL 2026-07-01 · 32-case invalid-payload matrix, 7/7 + update-agent authoring-gated (verify_build PASS, slop 95); code-review+execution-judge deferred |
| 10 | api-tester-validate-null-empty-fields | [x] FUNCTIONAL 2026-07-01 · 6-key null/empty states, 5/5 + update-agent authoring-gated (verify_build PASS, slop 95); code-review+execution-judge deferred |
| 11 | api-tester-verify-response-status-codes | [x] FUNCTIONAL 2026-07-01 · 8-case status-code conformance, 9/9 + update-agent authoring-gated (verify_build PASS, slop 95); code-review+execution-judge deferred |
| 12 | api-tester-verify-error-message-clarity | [x] FUNCTIONAL + update-agent authoring-gated 2026-07-01 · 3-descriptor error-clarity + 7 clarity checks, Section-3 pass, verify_build PASS, slop 95; code-review+execution-judge deferred |
| 13 | api-tester-verify-enum-value-restrictions | [x] FUNCTIONAL + update-agent authoring-gated 2026-07-01 · 10-probe enum matrix, Section-3 pass, verify_build PASS, slop 95; code-review+execution-judge deferred |
| 14 | api-tester-validate-json-schema-responses | [x] FUNCTIONAL + update-agent authoring-gated 2026-07-01 · schema-conformance descriptors + flags, Section-3 pass, verify_build PASS, slop 95; code-review+execution-judge deferred |
| 15 | api-tester-validate-header-propagation | [x] FUNCTIONAL + update-agent authoring-gated 2026-07-01 · 8-case header forwarding, Section-3 pass, verify_build PASS, slop 95; code-review+execution-judge deferred |
| 16 | api-tester-test-rate-limit-enforcement | [x] FUNCTIONAL + update-agent authoring-gated 2026-07-01 · 7-case rate-limit enforcement, Section-3 pass, verify_build PASS, slop 95; code-review+execution-judge deferred |
| 17 | api-tester-verify-content-type-negotiation | [x] FUNCTIONAL + update-agent authoring-gated 2026-07-01 · Section-3 pass, verify_build PASS, slop 95, code-review+execution-judge deferred |
| 18 | api-tester-validate-api-versioning-behavior | [x] FUNCTIONAL + update-agent authoring-gated 2026-07-01 · Section-3 pass, verify_build PASS, slop 95, code-review+execution-judge deferred |
| 19 | api-tester-test-webhook-delivery | [x] FUNCTIONAL + update-agent authoring-gated 2026-07-01 · Section-3 pass, verify_build PASS, slop 95, code-review+execution-judge deferred |
| 20 | api-tester-test-timeout-handling | [x] FUNCTIONAL + update-agent authoring-gated 2026-07-01 · Section-3 pass, verify_build PASS, slop 95, code-review+execution-judge deferred |
| 21 | api-tester-test-concurrent-request-handling | [x] FUNCTIONAL + update-agent authoring-gated 2026-07-01 · Section-3 pass, verify_build PASS, slop 95, code-review+execution-judge deferred |
| 22 | api-tester-verify-sorting-behavior | [x] FUNCTIONAL + update-agent authoring-gated 2026-07-01 · Section-3 pass, verify_build PASS, slop 95, code-review+execution-judge deferred |
| 23 | api-tester-verify-third-party-oauth-integration | [x] FUNCTIONAL + update-agent authoring-gated 2026-07-01 · Section-3 pass, verify_build PASS, slop 95, code-review+execution-judge deferred |
| 24 | api-tester-validate-correlation-id-propagation | [x] FUNCTIONAL + update-agent authoring-gated 2026-07-01 · Section-3 pass, verify_build PASS, slop 95, code-review+execution-judge deferred |
| 25 | api-tester-verify-caching-headers | [x] FUNCTIONAL + update-agent authoring-gated 2026-07-01 · Section-3 pass, verify_build PASS, slop 95, code-review+execution-judge deferred |
| 26 | api-tester-test-event-driven-api-triggers | [x] FUNCTIONAL + update-agent authoring-gated 2026-07-01 · Section-3 pass, verify_build PASS, slop 95, code-review+execution-judge deferred |
| 27 | api-tester-verify-audit-log-generation | [x] FUNCTIONAL + update-agent authoring-gated 2026-07-01 · Section-3 pass, verify_build PASS, slop 95, code-review+execution-judge deferred |
| 28 | api-tester-test-api-gateway-routing | [x] FUNCTIONAL + update-agent authoring-gated 2026-07-01 · Section-3 pass, verify_build PASS, slop 95, code-review+execution-judge deferred |
| 29 | api-tester-validate-retry-after-header-compliance | [x] FUNCTIONAL + update-agent authoring-gated 2026-07-01 · Section-3 pass, verify_build PASS, slop 95, code-review+execution-judge deferred |
| 30 | api-tester-validate-graphql-depth-limits | [x] FUNCTIONAL + update-agent authoring-gated 2026-07-01 · Section-3 pass, verify_build PASS, slop 95, code-review+execution-judge deferred |
| 31 | api-tester-test-long-polling-support | [x] FUNCTIONAL + update-agent authoring-gated 2026-07-01 · Section-3 pass, verify_build PASS, slop 95, code-review+execution-judge deferred |
| 32 | api-tester-test-file-upload-and-download | [x] FUNCTIONAL + update-agent authoring-gated 2026-07-01 · Section-3 pass, verify_build PASS, slop 95, code-review+execution-judge deferred |
| 33 | api-tester-test-multipart-form-data-handling | [x] FUNCTIONAL + update-agent authoring-gated 2026-07-01 · Section-3 pass, verify_build PASS, slop 95, code-review+execution-judge deferred |
| 34 | api-tester-track-defect-density | [x] FUNCTIONAL + update-agent authoring-gated 2026-07-01 · Section-3 pass, verify_build PASS, slop 95, code-review+execution-judge deferred |
| 35 | api-tester-test-ip-allowlist-enforcement | [x] FUNCTIONAL + update-agent authoring-gated 2026-07-01 · Section-3 pass, verify_build PASS, slop 95, code-review+execution-judge deferred |
| 36 | api-tester-run-regression-suite | [x] FUNCTIONAL + update-agent authoring-gated 2026-07-01 · Section-3 pass, verify_build PASS, slop 95, code-review+execution-judge deferred |
| 37 | api-tester-test-ssl-tls-enforcement | [x] FUNCTIONAL + update-agent authoring-gated 2026-07-01 · Section-3 pass, verify_build PASS, slop 95, code-review+execution-judge deferred |
| 38 | api-tester-test-bulk-operation-endpoints | [x] FUNCTIONAL + update-agent authoring-gated 2026-07-01 · Section-3 pass, verify_build PASS, slop 95, code-review+execution-judge deferred |
| 39 | api-tester-measure-api-consumer-satisfaction | [x] FUNCTIONAL + update-agent authoring-gated 2026-07-01 · Section-3 pass, verify_build PASS, slop 95, code-review+execution-judge deferred |
| 40 | contract-oracle-rollout-plan | [x] DONE 2026-07-01 · rollout artifact: contract-oracle guardrail applied to all 39 agents + de-bias + verification harness; acceptance 39/39 |
