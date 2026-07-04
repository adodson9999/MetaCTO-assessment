# api-tester — Master MECE Boundary & Ownership Map (governs all update-agent prompts)

Purpose: single de-dup authority. Every bug case any agent emits must have **exactly one**
owner here. Adapted from `agent-foundry/agents/api-tester/coverage-manifest.json` (lanes +
handoffs), then extended with newly-researched bug classes and each assigned to one owner.
`create-postman-collection` is **out of scope** (moving to the general/ folder).

Reviewers/subagents MUST:
- Add cases only inside their agent's lane below.
- REMOVE any existing case that this map assigns to a sibling (cite the sibling).
- Route a newly-found class to its **Reserved-owner** here; if a class fits no lane, add it to
  §Z (Unassigned) for central assignment — do not claim it.

---

## 1. Lane statements (owner of record) — 39 agents

### Auth cluster
- **test-authentication-flows** — First-party credential validity & session lifecycle: valid/missing/malformed/expired/revoked bearer; login success/wrong-password/unknown-user/missing-field/lockout; JWT tampering (alg=none, sig swap, kid injection, exp/nbf/iat, aud/iss); Authorization header malformation (scheme case, double Bearer, extra whitespace); api-key location (header/query/cookie); refresh-token rotation/replay; logout invalidation. → 401 domain.
- **check-authorization-rules** — AuthZ on protected resources: RBAC, owner-positive, cross-tenant IDOR/BOLA, function-level authZ (BFLA), privilege-escalation, **mass-assignment/BOPLA**, per-case field+substring leakage. → 403 domain.
- **verify-third-party-oauth-integration** — Third-party OAuth2 authorization-code flow stages: redirect/code-receipt/token-exchange/userinfo/refresh + CSRF-state, open-redirect redirect_uri, replayed/expired code, wrong client_secret, PKCE mismatch, denied consent, scope tampering/downgrade, state fixation.
- **test-ip-allowlist-enforcement** — network-origin allow/deny: allowlisted 200, non-allowlisted 403, XFF/X-Real-IP spoof, CIDR/subnet, IPv6 + IPv4-mapped, multi-hop XFF trusted-proxy depth, denylist precedence, allowlist mgmt-API add/remove.

### CRUD/state cluster
- **verify-crud-operation-integrity** — Hard CRUD lifecycle: ordered create/read/update/patch/delete, field-echo, list membership, negative lifecycle (update/delete-missing 404, duplicate 409), read-back state proof at each step.
- **test-idempotency-of-endpoints** — Sequential idempotency under one Idempotency-Key: PUT/DELETE/GET replay stability, POST create primary+fresh-key dedupe, same-key-different-body 422 conflict, key TTL/expiry, key scoping per-endpoint/per-user.
- **test-soft-delete-behavior** — Soft-delete semantics: delete markers, post-delete invisibility/non-persistence, restore, double-delete, update-on-deleted, unique-key reuse after soft-delete, cascade, DB-row survival within tolerance.
- **test-concurrent-request-handling** — Parallel races: N concurrent reads; N concurrent unique writes (count delta, zero dup, zero missing); concurrent update optimistic-lock/lost-update; concurrent same-unique-key; concurrent create+delete; zero 500s.
- **test-bulk-operation-endpoints** — Bulk/batch: all-valid, mixed 207 Multi-Status with offending-field naming, all-invalid, empty, single-item, duplicate-within-batch, oversize reject, atomicity rollback, partial-failure semantics, bulk-update/delete, DB delta.

### Query cluster
- **validate-search-and-filter-queries** — Search/filter semantics: keyword/substring, category/range/multi-value filters, invalid-value, unknown-parameter, empty-result, injection-safety (SQL/NoSQL operator injection), every-record-matches, count-equals-DB.
- **test-pagination-behavior** — Page math: first/middle/last/beyond-last, default size, oversize cap, page metadata (total/limit/offset or Link/cursor), zero overlap + zero gap across pages, invalid page params, cursor tamper/stability.
- **validate-query-parameter-handling** — Generic param mechanics: missing-required, wrong-type coercion, valid single, undocumented-ignored, multi-value, comma-list, URL-encoding, default application, name-case, duplicate-key, array-bracket syntax, param pollution.
- **verify-sorting-behavior** — Ordering: asc/desc by string/numeric/timestamp, multi-field secondary + stability, null ordering, collation/case, sort+pagination interaction, invalid-sort-field/invalid-order 400.

### Request-body cluster
- **validate-request-payloads** — Type/format/range/length body constraints: missing-required, wrong-type, extra field, string-length boundary, format/pattern (email/uri/uuid/date), numeric range/precision, array constraints, nested-object, ReDoS-pattern, deep-nesting/oversize-body — across create/update/patch.
- **validate-null-empty-fields** — Sole owner of null/empty/absent states: per-field absent / json-null / empty-string / zero / false / empty-array / empty-object / whitespace-only; all/each/combo-required-null; string-"null"; nested & array-element nulls.
- **verify-enum-value-restrictions** — Request-body enum membership: each valid accepted; unknown/empty/null/wrong-type/case-variant/numeric/array-multiselect/whitespace-padded/unicode-lookalike rejected.

### Response cluster
- **verify-response-status-codes** — Generic status conformance (codes no dedicated agent owns): 200/201/202/204, 301/302/303/307/308, 400, 404, 405 (+Allow header), 409, 410, 412, 422, 428, 431, 500/503. Method semantics (HEAD/OPTIONS).
- **verify-error-message-clarity** — Error-response clarity: human-readable message, machine-readable code, consistent error envelope, RFC 9457 problem+json shape, field-level validation detail, status↔code alignment, request-id in error, zero stack-trace/internal-detail leak.
- **validate-json-schema-responses** — Response-body schema conformance: every documented code's body validated (ajv strict, additionalProperties:false, required+typed, list-item validation, application/json content-type), nullability, format assertions, envelope consistency.

### Headers/negotiation cluster
- **validate-header-propagation** — Generic request-header forwarding: Authorization, W3C traceparent/tracestate, B3, X-Forwarded-*, one custom header reach downstream unmodified; hop-by-hop stripped; inbound traceparent continued; header injection/CRLF; case-insensitive handling; duplicate header folding.
- **validate-correlation-id-propagation** — Sole owner of correlation-ID: exact echo, propagation to API + downstream logs, no-header UUIDv4 auto-gen, uniqueness across requests, id-in-error, malformed-id reject/sanitize.
- **verify-caching-headers** — Caching: Cache-Control/ETag, If-None-Match 304, If-Modified-Since 304, Vary, If-Match 412, post-update ETag change, max-age freshness, mutation no-store, weak vs strong ETag, private/public correctness.
- **verify-content-type-negotiation** — Content negotiation: Accept per media type, 406 unsupported, wildcard, charset, q-value preference, Accept-Encoding; request Content-Type accepted/415, missing Content-Type, charset-in-Content-Type; malformed Accept.
- **validate-api-versioning-behavior** — API versioning: path/header-media-type/query versioning; current (no Deprecation), deprecated (Deprecation+Sunset+successor Link), unsupported (404/400); default-version; per-version schema; version skew/downgrade.
- **validate-retry-after-header-compliance** — Sole owner of Retry-After: 429 & 503 carrying Retry-After in integer-seconds and RFC 7231 HTTP-date forms, deadline-anchored honoring, sanity bound, past/negative/zero handling.

### Resilience cluster
- **test-rate-limit-enforcement** — Rate-limit counting: at-limit burst, over-limit throttle 429, window reset, per-key isolation, limit scope (ip/user/endpoint), RateLimit-Limit/Remaining/Reset decrement, distributed-counter consistency, burst vs sustained.
- **test-timeout-handling** — Timeout: injected upstream delay → gateway timeout within max_wait with safe error body + recovery; slow-client/slowloris; connect-vs-read distinction; retry-on-timeout; partial-response/no-half-open.
- **test-api-gateway-routing** — Gateway routing: request reaches exactly the correct single backend unchanged, other backends untouched; path-rewrite; unknown-route 404; method-not-allowed; load-balancing/weighting; injected X-Forwarded-*/X-Request-ID; service-down 503; header size limits.

### Async/eventing cluster
- **test-webhook-delivery** — HTTP-callback webhooks: register/trigger/poll; payload + ISO timestamp + HMAC signature; event filtering; multi-retry backoff; dead-letter after max; non-retryable 4xx; tamper-negative; **SSRF/URL-validation on registration**; replay-window; ordering.
- **test-event-driven-api-triggers** — Broker/topic events: well-formed event drives state in window; malformed → ERROR-logged + dead-lettered + state-unchanged + consumer-healthy; duplicate idempotent; out-of-order; poison-retry then DLQ; schema-registry/versioned event; consumer-lag.
- **test-long-polling-support** — Long-poll transport: no-event 204 within window, event 200 within 2s with correct type, multiple-events queued, resume-after-gap via Last-Event-ID, concurrent pollers, connection-drop, timeout boundary, no-missed-event across reconnect.

### Files + transport/security cluster
- **test-file-upload-and-download** — File policy/security: size limits (0-byte + over-max), MIME allow/deny, magic-byte-vs-declared-MIME mismatch, path-traversal filename, double-extension, byte-for-byte MD5 download round-trip, download-404, download-authorization, decompression-bomb.
- **test-multipart-form-data-handling** — Multipart encoding mechanics: text+file parts, returned-file-URL field, MD5 round-trip, persisted readback, multi-file array, part-without-filename, duplicate field, field-order independence, malformed/missing boundary, oversized-part-count, content-type per part.
- **test-ssl-tls-enforcement** — TLS: protocol probes (plain HTTP + TLS1.0/1.1 reject, TLS1.2/1.3 accept), cert assertions incl. OCSP/expiry/hostname/chain, HSTS, forward-secrecy/cipher-order, forbidden weak ciphers, SNI/wildcard, renegotiation, compression (CRIME).
- **validate-graphql-depth-limits** — GraphQL query-protection: depth (accept/at-limit/one-over reject/deep timed reject), complexity/cost, alias amplification, fragment-cycle, introspection policy, batched-query cap, field-duplication amplification.

### Observability + reframed aggregators
- **verify-audit-log-generation** — Audit-log semantics: create/update/delete entries with required fields + window/tolerance, read-audit, failed-action audit, login/logout audit, before/after on update, immutability/tamper, actor+source-ip fidelity.
- **track-defect-density** — REFRAME to bug-finder: contract/computation defects in a defect-density **reporting endpoint/artifact** (miscount, test-file exclusion errors, severity-weighting math, per-area rollup, rolling-average window, deviation %, alert-threshold, P1–P4 tally, trend sign) surfaced as deviations. (See prompt for framing.)
- **run-regression-suite** — REFRAME to bug-finder: parse/compare defects in a regression-report **comparator** (format parsing JUnit/Jest/pytest/TAP/TRX, miscount of total/prev-passed/regressions/newly-passing/flaky/slowed, status derivation, empty/malformed artifact handling) as deviations.
- **measure-api-consumer-satisfaction** — REFRAME to bug-finder: computation/validity defects in a satisfaction-metrics **endpoint/artifact** (NPS/CSAT/CES formula errors, band boundaries, validity-threshold gate, per-segment rollup, QoQ trend, response-window filtering, division-by-zero/empty-sample) as deviations.

---

## Z. Reserved cross-cutting classes (assigned to exactly one owner)

| Bug class (research-derived) | Sole owner |
|---|---|
| BOLA / IDOR (object-level) | check-authorization-rules |
| BFLA (function/method-level authZ) | check-authorization-rules |
| Mass assignment / BOPLA (property-level) | check-authorization-rules |
| JWT algorithm/signature/claim attacks | test-authentication-flows |
| OAuth scope/state/PKCE/redirect attacks | verify-third-party-oauth-integration |
| SSRF via server-side URL input (webhook target) | test-webhook-delivery |
| SQL/NoSQL injection via filter operators | validate-search-and-filter-queries |
| Parameter pollution / duplicate query keys | validate-query-parameter-handling |
| CRLF / header injection | validate-header-propagation |
| ReDoS via regex pattern constraint | validate-request-payloads |
| Oversized/deeply-nested JSON body (parser DoS) | validate-request-payloads |
| Unicode/case/whitespace enum lookalikes | verify-enum-value-restrictions |
| Path traversal in upload filename | test-file-upload-and-download |
| Decompression bomb (zip/gzip) | test-file-upload-and-download |
| GraphQL introspection / cost / depth abuse | validate-graphql-depth-limits |
| Stack-trace / internal-detail leak in errors | verify-error-message-clarity |
| Cross-tenant data leak on success body | check-authorization-rules |
| Missing/incorrect Retry-After | validate-retry-after-header-compliance |
| RateLimit-* header math | test-rate-limit-enforcement |
| Response schema additionalProperties leak | validate-json-schema-responses |
| Lost-update / optimistic-lock races | test-concurrent-request-handling |
| Idempotency-key replay dedupe | test-idempotency-of-endpoints |
| TLS downgrade / weak cipher | test-ssl-tls-enforcement |
| Open redirect (non-OAuth) | verify-response-status-codes (3xx Location) unless OAuth → verify-third-party-oauth-integration |

Note: 401 owned by test-authentication-flows; 403 by check-authorization-rules; 406/415 by
verify-content-type-negotiation; 429 by test-rate-limit-enforcement; Retry-After by
validate-retry-after-header-compliance. verify-response-status-codes owns only the residual codes.
