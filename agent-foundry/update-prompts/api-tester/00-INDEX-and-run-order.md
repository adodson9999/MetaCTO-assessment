# api-tester update-agent prompts — index, run order & MECE reconciliation

39 agents reviewed (all of `agents/api-tester/` except `create-postman-collection`, which moves to
the general/ folder). Each has an exhaustive `update-agent` prompt in this folder that (a) closes
its gaps vs. the full researched bug universe for its title, and (b) removes/hands off anything a
sibling owns. Governed by `00-MECE-boundary-map.md`.

## v2 — exhaustive test-case + reporting standard (read this)
Every agent is now a **pure test-case generator that renders no bug verdict**. Governed by
`00-AUTHORING-STANDARD-exhaustive-testcases.md`: each agent must exhaust its lane across five angles
(happy / negative / boundary / edge / broad) and emit each case in a plain-language reporting schema
(`test_case_id`, `title`, `description`, `category`, `feature_under_test`, `preconditions`, `test_data`,
`test_steps`, `expected_result`, `actual_result`=blank, `status`=`Not Executed`, `postconditions`,
`severity_hint`, `references`, `tags`), with the original machine fields preserved under a `machine` key.
The tester fills Expected Result only; a **separate judge agent** fills Actual Result and decides Pass/Fail.
Each `<name>.update-agent.md` carries this as its **## ADDENDUM (v2)** section — pass it together with the
Change prompt when you run `update-agent` (see RUN-ALL.prompt.md).

## How to apply
Run each invocation from the repo (interactive Claude Code or CI):
```
update-agent <agent_name> "<change prompt from that agent's file>"
# CI form:
python .claude/skills/update-agent/scripts/update_agent.py <agent_name> "<prompt>" --workspace <repo>/agent-foundry
```
Each file's **## Invocation** + **## Change prompt (verbatim)** is the exact text to pass. The skill
re-authors line-by-line through its debate/determinism/code-review(≥85)/regression gates, so a prompt
that would regress an agent will hard-halt for your decision rather than silently degrade it.

### Suggested run order (lowest-overlap → highest, so MECE gate sees clean neighbors first)
1. Standalone lanes: test-ssl-tls-enforcement, validate-graphql-depth-limits, verify-audit-log-generation, validate-retry-after-header-compliance, validate-correlation-id-propagation
2. Reframed aggregators: track-defect-density, run-regression-suite, measure-api-consumer-satisfaction
3. Request-body trio: validate-null-empty-fields → verify-enum-value-restrictions → validate-request-payloads
4. Query quartet: validate-query-parameter-handling → validate-search-and-filter-queries → test-pagination-behavior → verify-sorting-behavior
5. Response trio: verify-response-status-codes → verify-error-message-clarity → validate-json-schema-responses
6. Headers/negotiation six
7. CRUD/state five, Resilience three, Async three, Files two, Auth four

## Case-count deltas (before → after)

| Agent | Before | After | Note |
|---|---|---|---|
| test-authentication-flows | 11 | 30 | JWT alg/sig/claim, header malformation, api-key location, refresh replay |
| check-authorization-rules | 12 | 24 | BOLA, BFLA, BOPLA/mass-assignment, success-body leak |
| verify-third-party-oauth-integration | 11 | 19 | state CSRF/fixation, redirect_uri, code injection, scope upgrade, mix-up |
| test-ip-allowlist-enforcement | 9 | 16 | XFF/X-Real-IP/Forwarded spoof, IPv4-mapped IPv6, proxy-depth off-by-one |
| verify-crud-operation-integrity | 8 | 18 | PATCH partial, If-Match/412/428, duplicate 409, Location+read-back |
| test-idempotency-of-endpoints | 4 | 9 | POST key dedupe, first-response caching, key scope/TTL, 422 conflict |
| test-soft-delete-behavior | 4 | 11 | list exclusion, restore, update-on-deleted, unique-key reuse, cascade |
| test-concurrent-request-handling | 5 | 8 | create+delete TOCTOU, parallel same-key race, thundering herd |
| test-bulk-operation-endpoints | 10 | 12 | best-effort partial, per-item index mapping, DB-delta invariants |
| validate-search-and-filter-queries | 5 | 16 | AND/OR/range/date, wildcard/escaping, SOLE-owner SQL+NoSQL injection |
| test-pagination-behavior | 10 | 18 | cursor/keyset, max-cap, Link header, unstable-sort drift soak |
| validate-query-parameter-handling | 8 | 13 | array-bracket, comma-list, HPP precedence, boolean, plus-vs-%20 |
| verify-sorting-behavior | 12 | 15 | ORDER-BY identifier injection, default-sort, stable-tie determinism |
| validate-request-payloads | ~13 | ~90–120 | formats, boundaries, coercion, arrays, nested, structural DoS/ReDoS |
| validate-null-empty-fields | ~ | ~70–110 | whitespace/unicode, null-vs-missing pair, required-null power-set |
| verify-enum-value-restrictions | ~ | ~55–90 | casing/whitespace/homoglyph, shape mismatch, numeric/boolean-for-enum |
| verify-response-status-codes | 8 | 25 | 202/204/201-Loc, 3xx+method preserve, 410/412/428/431/503, HEAD/OPTIONS |
| verify-error-message-clarity | 3 | 7 | RFC 9457 problem+json, validation array, 500 no-leak |
| validate-json-schema-responses | 4 desc | 4 desc / 11 flags | nullable, format, enum, envelope, unevaluatedProperties:false |
| validate-header-propagation | 8 | 17 | hop-by-hop strip, traceparent continue/originate, CRLF, folding, smuggling |
| validate-correlation-id-propagation | 6 | 10 | length bound, X-Request-ID alias, not-regenerated, id-in-error-body |
| verify-caching-headers | 11 | 20 | directive coverage, weak/strong ETag, conditional precedence, Age/Date |
| verify-content-type-negotiation | 11 | 19 | subtype wildcard, q=0 exclusion, encoding fallback, malformed Accept |
| validate-api-versioning-behavior | 8 | 15 | Deprecation/Sunset/successor Link, per-version schema, silent-downgrade |
| validate-retry-after-header-compliance | 7 | 14 | 503 parity, HTTP-date form, degenerate values, presence-required |
| test-rate-limit-enforcement | 7 | 14 | window model, isolation, cost-weighted, distributed counter, spoof bypass |
| test-timeout-handling | 6 | 11 | deadline floor, no-half-open, client-cancel, keep-alive, connect-vs-read |
| test-api-gateway-routing | 7 | 14 | host/header routing, canary weight, 414/431 at gateway, normalization |
| test-webhook-delivery | 6 | 10 | replay-window, idempotent redelivery, retryable-4xx, SOLE-owner SSRF |
| test-event-driven-api-triggers | 5 | 8 | versioned-event compat, ordering-key partition, consumer-lag backpressure |
| test-long-polling-support | 6 | 8 | immediate-return-pending, hold-timeout boundary |
| test-file-upload-and-download | 10 | 22 | dangerous/double/null-byte filename, traversal, zip-bomb, EXIF, MD5 |
| test-multipart-form-data-handling | 6 | 13 | boundary framing, per-part CT/charset, part-count, extra-header ignore |
| test-ssl-tls-enforcement | 6 | 10 | self-signed reject, CRIME, secure-renegotiation, cert pinning |
| validate-graphql-depth-limits | 9 | 15 | field-dup/variable amplification, directive abuse, Clairvoyance, persisted |
| verify-audit-log-generation | 9 | 19 | actor/source-ip/timestamp fidelity, immutability, log-injection, redaction |
| track-defect-density | calc | 20 (bug-finder) | REFRAMED: defects in the density-report endpoint |
| run-regression-suite | calc | 22 (bug-finder) | REFRAMED: defects in the regression-compare endpoint |
| measure-api-consumer-satisfaction | calc | 20 (bug-finder) | REFRAMED: defects in the satisfaction-metrics endpoint |

## Cross-cluster canonical-ownership ledger (one owner per shared concept)

| Shared concept | Sole owner | Others must |
|---|---|---|
| 401 (authN) | test-authentication-flows | defer |
| 403 (authZ), BOLA/BFLA/BOPLA, cross-tenant leak | check-authorization-rules | defer |
| OAuth state/PKCE/redirect/scope | verify-third-party-oauth-integration | defer |
| SQL/NoSQL operator injection (filter sink) | validate-search-and-filter-queries | defer |
| ORDER-BY identifier injection (sort sink) | verify-sorting-behavior | defer |
| CRLF/header injection + hop-by-hop + forwarding | validate-header-propagation | defer |
| Correlation/X-Request-ID echo/auto-gen | validate-correlation-id-propagation | defer |
| Log injection / redaction / immutability | verify-audit-log-generation | defer |
| ReDoS + oversized/deep-nested BODY (413) | validate-request-payloads | defer |
| null/empty/absent field states | validate-null-empty-fields | defer |
| enum membership | verify-enum-value-restrictions | defer |
| Idempotency-Key sequential replay | test-idempotency-of-endpoints | defer |
| Parallel same-key race / lost-update | test-concurrent-request-handling | defer |
| SSRF on server-side URL (webhook target) | test-webhook-delivery | defer |
| Retry-After value/format (429 & 503) | validate-retry-after-header-compliance | defer |
| RateLimit-* header math / counting | test-rate-limit-enforcement | defer |
| 406/415 content negotiation | verify-content-type-negotiation | defer |
| Response schema / additionalProperties | validate-json-schema-responses | defer |
| Error envelope wording / stack-trace leak | verify-error-message-clarity | defer |
| Path traversal + zip bomb (upload policy) | test-file-upload-and-download | defer |
| Multipart boundary/part parsing | test-multipart-form-data-handling | defer |

## One seam to confirm before you run (same trigger, 3 aspects)

**Oversized request-line / header-fields (414 / 431).** Three agents legitimately touch this by a
DIFFERENT aspect, so under the MECE canonical-identity hash they are distinct cases — but if you want
zero conceptual overlap, pick one owner:
- `verify-response-status-codes` — the **code value** 431/414 in isolation on a generic endpoint.
- `test-api-gateway-routing` — the gateway **rejects at the edge, no backend hit** (routing invariant).
- `validate-header-propagation` — the oversized header is **not forwarded unbounded** (forwarding disposition).

Recommendation: **keep all three** (they assert different invariants and different endpoints/roles, so
they are not duplicate test cases), but if you prefer strict single-ownership, drop the 414/431 cases
from `test-api-gateway-routing` and keep only its "no backend hit" journal assertion referencing the
status agent's case. Everything else resolved to exactly one owner with no action needed.

## Reframed aggregators — what changed conceptually
`track-defect-density`, `run-regression-suite`, and `measure-api-consumer-satisfaction` were plan-only
metric CALCULATORS. Their prompts convert them into pure bug-finders that emit a `cases[]` matrix
against the endpoint/artifact that SERVES the metric, using the researched formula (NPS = %promoters −
%detractors; CSAT top-2-box; defect density = defects/KLOC × 1000 with severity weighting; JUnit/TAP
parse rules) as `expected_by_contract`, and surface miscomputation, malformed-input (4xx-not-5xx), auth,
and schema defects. Non-deterministic pieces with no black-box oracle (e.g. k-means theme clustering)
are dropped rather than faked.
