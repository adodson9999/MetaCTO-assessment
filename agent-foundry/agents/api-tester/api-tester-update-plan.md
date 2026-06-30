# api-tester — Coverage Ranking & update-agent Prompts

**Scope:** all 39 `api-tester` agents. Each is scored **/10** on whether it *fully tests the
workflow its name implies*. For every agent there is one `update-agent` prompt (39 total) written
in the exact format the `update-agent` skill expects:

```
update-agent <agent_name> <change prompt…>
```

Every prompt does two things: (1) **adds** the missing coverage that pushes the agent toward 10/10,
and (2) where another agent already owns an area, **explicitly defers** that area so the update
doesn't make two agents test the same thing. The deferrals map to the overlap analysis below.

> How scoring works: an agent scores high when the cases it emits exhaust the *contract surface* of
> its named workflow (happy path + boundaries + negatives + the relevant headers/DB/observability
> assertions). It loses points for happy-path-only coverage, a single hardcoded shape, or missing
> negative/boundary cases.

---

## Summary ranking (low score = higher update priority)

| # | Agent | Score | Biggest gap to 10 | Primary overlap to fence off |
|---|-------|:----:|-------------------|------------------------------|
| 1 | test-pagination-behavior | 5 | No page metadata, no last/beyond-last page, no size-cap/default, no overlap-or-gap assertion | query-param (limit/skip wrong-type), sorting |
| 2 | validate-json-schema-responses | 5 | Only the happy 2xx body is validated; error-response schemas, `additionalProperties`, list-item schemas unchecked | error-message-clarity (error bodies) |
| 3 | validate-header-propagation | 5 | Only X-Correlation-ID — no Authorization/W3C trace/X-Forwarded/hop-by-hop forwarding | **near-duplicate of correlation-id-propagation** |
| 4 | validate-request-payloads | 6 | No format/pattern/range/minLength/array/nested-object constraints; POST-only | null-empty (absent/null), enum agent |
| 5 | verify-response-status-codes | 6 | Missing 405/409/422/204/redirect/410 | auth(401), authz(403), content-type(406/415), rate-limit(429) |
| 6 | test-authentication-flows | 6 | No login success/failure/lockout, no JWT tampering, no header-malformation variants | oauth (3p flow), authz (403) |
| 7 | validate-query-parameter-handling | 6 | No multi-value/array params, encoding, defaults, name-case | search (filters), sorting (order), pagination (limit/skip) |
| 8 | test-rate-limit-enforcement | 6 | No per-key/IP isolation, no RateLimit-* headers, no scope | **Retry-After agent (shared burst)** |
| 9 | test-idempotency-of-endpoints | 6 | No same-key-different-body conflict, no key TTL, no safe-method idempotency | concurrency (parallel races) |
| 10 | verify-content-type-negotiation | 6 | No charset, q-value preference, Accept-Encoding/Language | — |
| 11 | verify-error-message-clarity | 6 | No envelope-shape consistency, field-level detail, status↔code alignment, request-id | authz (leakage list) |
| 12 | validate-api-versioning-behavior | 6 | No header/media-type or query versioning, no Sunset/default-version | — |
| 13 | test-webhook-delivery | 6 | One retry only — no backoff schedule, DLQ exhaustion, event filtering, tamper-reject | event-driven (pub/poll) |
| 14 | test-timeout-handling | 6 | No slow-client/slowloris, connect-vs-read, retry-on-timeout, error-body safety | gateway |
| 15 | test-concurrent-request-handling | 6 | No lost-update/optimistic-lock 409, no same-unique-key race | idempotency (sequential) |
| 16 | verify-sorting-behavior | 6 | No multi-field/secondary, tie-break stability, numeric-vs-lexical, null ordering, sort+paging | query-param (order) |
| 17 | validate-search-and-filter-queries | 6 | Hardcoded status/category; no range/substring/case/multi-value/injection-safety | query-param (mechanics), pagination |
| 18 | verify-third-party-oauth-integration | 6 | Happy-path only — no CSRF-state/redirect-uri/used-code/bad-secret negatives, no PKCE | auth-flows (token validity) |
| 19 | validate-correlation-id-propagation | 6 | No malformed-id handling, no W3C traceparent/tracestate, no id in errors | **near-duplicate of header-propagation** |
| 20 | verify-caching-headers | 6 | No Last-Modified/If-Modified-Since, Vary, If-Match/412, max-age correctness | idempotency (PUT) |
| 21 | test-event-driven-api-triggers | 6 | No duplicate/out-of-order/replay, poison-retry count, ordering-per-key | webhook (delivery) |
| 22 | verify-audit-log-generation | 6 | No read/failed-action/auth-event audit, no immutability, no before/after values | correlation-id (logs) |
| 23 | test-api-gateway-routing | 6 | No path-rewrite, LB/weighting, unknown-route 404, gateway-injected headers | header-propagation, timeout |
| 24 | test-multipart-form-data-handling | 6 | No multi-file, no-filename part, boundary edge, duplicate fields | **file-upload (size/MIME/MD5)** |
| 25 | validate-retry-after-header-compliance | 6 | No HTTP-date variant, no 503 Retry-After, no sanity bound | **rate-limit agent (shared burst)** |
| 26 | validate-graphql-depth-limits | 6 | No complexity/cost, alias amplification, fragment cycles, introspection, batching | — |
| 27 | test-long-polling-support | 6 | No queued/multiple events, Last-Event-ID resume, concurrent pollers, drop | event-driven |
| 28 | check-authorization-rules | 7 | No owner-positive case, no cross-tenant IDOR, no role mass-assignment | auth-flows (token validity) |
| 29 | track-defect-density | 7 | No severity weighting, per-endpoint/area density, coverage linkage | other metric agents |
| 30 | verify-crud-operation-integrity | 7 | No PATCH, no update/delete-missing 404, no list-membership, no concurrency bump | soft-delete, idempotency |
| 31 | test-ip-allowlist-enforcement | 7 | No CIDR/subnet, IPv6, multi-hop XFF depth, denylist precedence | — |
| 32 | run-regression-suite | 7 | No flaky detection, more formats (TAP/TRX/NUnit), duration trend | metric agents |
| 33 | test-ssl-tls-enforcement | 7 | No HSTS, pinning/OCSP, cipher-order/PFS, SNI/wildcard | — |
| 34 | test-bulk-operation-endpoints | 7 | No all-valid/empty/single/duplicate batch, atomic mode, bulk update/delete | concurrency |
| 35 | measure-api-consumer-satisfaction | 7 | NPS-only — no CSAT/CES, segmentation, quarter trend | metric agents |
| 36 | verify-enum-value-restrictions | 7 | No numeric enums, array/multi-select, whitespace-pad, unicode look-alike | query-param/sorting (query enums) |
| 37 | test-soft-delete-behavior | 7 | No restore/undelete, double-delete, update-deleted, unique-key reuse, cascade | crud, audit |
| 38 | validate-null-empty-fields | 8 | No whitespace-only, no null inside nested/array element | **owns** absent/null (request-payloads defers here) |
| 39 | test-file-upload-and-download | 6 | No 0-byte / path-traversal filename, magic-byte-vs-MIME mismatch, download authz/404 (score 6 — grouped with the 6s, listed last as a late add) | **multipart (upload encoding mechanics)** |

---

## Overlap map (the "don't test the same thing twice" notes for the next step)

These are the pairs/clusters where two agents currently touch the same surface. Each prompt below
resolves the overlap by assigning a clear **owner** and making the other agent **defer**.

- **A. Burst/over-limit cluster** — `test-rate-limit-enforcement` vs `validate-retry-after-header-compliance`
  emit the *same* at_limit/over_limit burst. **Owner of enforcement (count, window reset, per-key
  isolation, `RateLimit-*` headers):** rate-limit. **Owner of the 429/503 `Retry-After` header
  (presence, integer + HTTP-date formats, honoring):** retry-after.
- **B. Correlation/trace headers** — `validate-header-propagation` vs `validate-correlation-id-propagation`
  are near-duplicates (both: X-Correlation-ID with/without header + log asserts). **Owner of
  correlation-id semantics (echo, auto-gen UUIDv4, malformed-id handling, downstream logs):**
  correlation-id. **Owner of generic header forwarding (Authorization, W3C `traceparent`/`tracestate`,
  B3, `X-Forwarded-*`, custom passthrough, hop-by-hop stripping):** header-propagation.
- **C. Upload cluster** — `test-file-upload-and-download` vs `test-multipart-form-data-handling`
  both cover oversized/MIME/MD5. **Owner of file semantics (size limits, MIME-vs-magic-byte,
  0-byte, path-traversal filename, download authz + integrity):** file-upload. **Owner of multipart
  *encoding* mechanics (text+file parts, boundary, duplicate/no-filename parts, field parsing):**
  multipart.
- **D. Request-body constraints** — `validate-request-payloads` vs `validate-null-empty-fields` vs
  `verify-enum-value-restrictions`. **Owner of absent/null/empty/whitespace states:** null-empty.
  **Owner of enum membership:** enum agent. **Owner of everything else (type, format/pattern,
  numeric range, length boundaries, arrays, nested objects):** request-payloads.
- **E. Collection-query cluster** — `validate-query-parameter-handling` vs
  `validate-search-and-filter-queries` vs `verify-sorting-behavior` vs `test-pagination-behavior`.
  **Owner of generic param mechanics (type coercion, multi-value/array, encoding, defaults,
  unknown-param policy, name-case):** query-param. **Owner of filtering/search semantics:** search.
  **Owner of ordering:** sorting. **Owner of page math/metadata:** pagination.
- **F. Status-code generalist** — `verify-response-status-codes` should only own codes no dedicated
  agent owns: **405, 409, 422, 204, 301/302, 410**. It defers 401→auth, 403→authz, 406/415→content-type,
  429→rate-limit.
- **G. Auth cluster** — `test-authentication-flows` (credential validity), `check-authorization-rules`
  (RBAC/IDOR/leakage), `verify-third-party-oauth-integration` (3p auth-code flow) stay distinct;
  each prompt notes the boundary so 401/403 isn't re-litigated three times.

---

## The 39 update-agent prompts

Listed update-first (lowest score first). Each block is ready to paste.

### 1. test-pagination-behavior — 5 → 10
Adds page metadata + boundary pages + size cap/default; defers param mechanics & ordering.

```
update-agent api-tester-test-pagination-behavior extend the plan beyond the three offset pages and four invalid-param probes: add a "last_page" case (skip lands on the final partial page) and a "beyond_last" case (skip past the end, expect an empty list and a success status, not an error); add an "oversize_limit" case asserting a limit above the documented max is clamped to the max rather than honored; add a "default_limit" case that sends no page-size param and asserts the documented default size; add a "metadata" assertion block requiring total/count and hasMore (or RFC 5988 Link rel=next/prev) to be present and correct; and add cross-page assertions asserting the union of page1+page2+page3 ids has zero overlap and zero gap against an ordered baseline. Keep this agent the sole owner of page math/metadata: do NOT add wrong-type limit/skip cases (owned by api-tester-validate-query-parameter-handling) and do NOT add ordering cases (owned by api-tester-verify-sorting-behavior).
```

### 2. validate-json-schema-responses — 5 → 10
Adds error-body + strictness + list-item schema validation; defers clarity wording.

```
update-agent api-tester-validate-json-schema-responses stop validating only the happy 2xx body: emit one request descriptor per documented response code (2xx plus each documented 4xx/5xx) so the harness validates every error response body against its own documented schema, not just the success body. For each schema add explicit assertions that strict validation runs (additionalProperties:false rejects undocumented response fields, every documented required field is present, and each field matches its declared type/format). When the response is a collection, validate every item against the item schema and assert the list is non-empty before claiming conformance. Add a charset assertion that the response Content-Type is application/json. Keep response-body schema conformance the focus here; defer human-readability of error text and internal-leak checks to api-tester-verify-error-message-clarity.
```

### 3. validate-header-propagation — 5 → 10
Repositioned to generic header forwarding (resolves the correlation-id duplicate).

```
update-agent api-tester-validate-header-propagation reposition this agent from correlation-ID-only to general request-header forwarding so it no longer duplicates api-tester-validate-correlation-id-propagation. Keep the with-header/no-header structure but cover a configurable set of forwarded headers: Authorization, the W3C trace context pair traceparent and tracestate, B3 (X-B3-TraceId/SpanId), and one arbitrary custom X-* header. Emit assertions that each of these is propagated byte-for-byte to every downstream service and appears unmodified in the downstream logs; add a "hop_by_hop_stripped" assertion that Connection, Keep-Alive, Transfer-Encoding, and Upgrade are NOT forwarded; and add a "traceparent_continued" assertion that when an inbound traceparent is supplied the downstream span keeps the same trace-id. Explicitly hand off the X-Correlation-ID echo, UUIDv4 auto-generation, and correlation-specific log greps to api-tester-validate-correlation-id-propagation and do not re-emit them here.
```

### 4. validate-request-payloads — 6 → 10
Adds the full constraint surface; defers null/empty and enum.

```
update-agent api-tester-validate-request-payloads broaden the payload matrix beyond required/wrong-type/extra-field/maxlength so it exercises the whole request-body constraint surface: add format/pattern probes (per string field with a documented format or regex, one body that violates it — bad email, bad uuid, bad date-time, regex-miss), numeric-range probes (below minimum, above maximum, exclusive-bound, and multipleOf violations for integer/number fields), string-length boundary probes that assert exactly maxLength is accepted and maxLength+1 is rejected and minLength-1 is rejected, array probes (minItems-1, maxItems+1, and a wrong-item-type element), and nested-object probes (a required sub-field absent and a sub-field of wrong type one level down). Also emit a "valid" and matching invalid set for PATCH partial bodies, not just POST/PUT. To avoid duplication, do NOT add absent/null/empty-state cases (owned by api-tester-validate-null-empty-fields) and do NOT add enum-membership cases (owned by api-tester-verify-enum-value-restrictions); reference those two agents in the prompt so the boundary is explicit.
```

### 5. verify-response-status-codes — 6 → 10
Adds the uncovered codes; defers the ones dedicated agents own.

```
update-agent api-tester-verify-response-status-codes add request descriptors for the documented status codes this agent currently skips and that no other api-tester agent owns: 405 (send a method not allowed on a path that documents others, expect Allow header listing valid methods), 409 (trigger a uniqueness/conflict, e.g. create a duplicate of an existing unique key), 422 (well-formed JSON that fails semantic validation), 204 (a no-content success such as DELETE, asserting an empty body), 301/302 (a documented redirect, asserting the Location header) and 410 (a documented gone resource). Keep one descriptor per documented code in documented order. Explicitly defer the codes other agents already own — 401 to api-tester-test-authentication-flows, 403 to api-tester-check-authorization-rules, 406/415 to api-tester-verify-content-type-negotiation, and 429 to api-tester-test-rate-limit-enforcement — and do not emit those here.
```

### 6. test-authentication-flows — 6 → 10
Adds login lifecycle + JWT tampering + header malformation; defers 3p OAuth.

```
update-agent api-tester-test-authentication-flows add the credential cases the five token subtests don't reach. Add a login-lifecycle block: correct credentials return a token (2xx), wrong password returns 401, and N consecutive failures trigger account lockout (subsequent correct login is blocked). Add a JWT-tampering block for bearer schemes: alg=none token, a token with a modified payload claim, and a token with a broken signature — each expected 401. Add an Authorization-header-malformation block: wrong scheme word (Basic where Bearer is required), missing the "Bearer " prefix, and extra interior whitespace — each expected 401. Add an "apikey_wrong_location" case that actually sends the API key in the wrong place (query string when a header is required, or vice versa) instead of only listing it as not_applicable. Keep the third-party authorization-code/refresh flow out of scope — that stays with api-tester-verify-third-party-oauth-integration — and don't re-test plain 403 authorization, which belongs to api-tester-check-authorization-rules.
```

### 7. validate-query-parameter-handling — 6 → 10
Repositioned to generic param mechanics; defers filters/order/paging.

```
update-agent api-tester-validate-query-parameter-handling make this the generic query-parameter MECHANICS agent and stop overlapping the filter/sort/page agents. Derive cases from the full documented parameter list rather than the hardcoded limit/skip/sortBy/order/select/q set, and add: a multi-value case (?tag=a&tag=b) and a comma-list case (?tag=a,b) asserting the documented array/CSV policy; a URL-encoding case (a value with spaces and reserved characters percent-encoded) asserting correct decoding; a default-application case (a documented-default param omitted, asserting the default takes effect); a parameter-name-case case (LIMIT vs limit) asserting the documented case policy; and a duplicate-same-key case (?limit=5&limit=10) asserting the documented first/last-wins rule. Keep the existing missing-required, wrong-type, and undocumented-ignored probes. Explicitly defer filtering semantics to api-tester-validate-search-and-filter-queries, ordering to api-tester-verify-sorting-behavior, and page math to api-tester-test-pagination-behavior, and do not duplicate their valued cases.
```

### 8. test-rate-limit-enforcement — 6 → 10
Adds isolation + RateLimit-* headers + scope; defers Retry-After to its agent.

```
update-agent api-tester-test-rate-limit-enforcement deepen enforcement coverage and draw a clean line against api-tester-validate-retry-after-header-compliance. Keep the at_limit burst, over_limit request, and the two timed window probes, but add: a per-key isolation case (a second api_key_value runs its own full allowance in the same window and is unaffected by the first key's exhaustion); a scope case asserting the limit is counted per the documented scope (per-endpoint vs global — a different endpoint with the same key is or isn't counted per the contract); and a headers block asserting the success and throttled responses carry the documented RateLimit-Limit / RateLimit-Remaining / RateLimit-Reset (or X-RateLimit-*) values and that Remaining decrements correctly across the burst. This agent owns enforcement (counting, window reset, isolation, RateLimit-* surfacing). Do NOT assert the 429 Retry-After header's presence, format, or honoring — that is owned by api-tester-validate-retry-after-header-compliance; reference it explicitly.
```

### 9. test-idempotency-of-endpoints — 6 → 10
Adds key-conflict + TTL + safe-method idempotency; defers concurrent races.

```
update-agent api-tester-test-idempotency-of-endpoints extend the PUT/DELETE/POST replay plan with the idempotency-key edge cases it omits. Add a "same_key_different_body" case: replay the POST add with the SAME idempotency key but a changed body, asserting the documented conflict response (422/409) rather than a second create. Add a "key_scope" case asserting two different keys on the same POST produce two distinct resources (already implied — make it an explicit assertion). Add a "stale_field_stable" assertion on the PUT replays that server-managed fields (updated_at / version / etag) are identical across all three replays, not just the body. Add a "safe_method_idempotent" case: GET the target three times and assert byte-identical bodies. If the contract documents an idempotency-key TTL, add an "expired_key" case. Keep concurrent/parallel same-key races out of scope — those belong to api-tester-test-concurrent-request-handling — and reference it so the sequential-vs-parallel split is explicit.
```

### 10. verify-content-type-negotiation — 6 → 10
Adds charset, q-values, encoding, language.

```
update-agent api-tester-verify-content-type-negotiation extend both kinds beyond the five Accept probes and three Content-Type probes. For the accept kind add: a charset probe (Accept with application/json; charset=utf-8 and an assertion the response echoes a correct charset), a q-value preference probe (Accept: <fmt1>;q=0.8, <fmt2>;q=0.9 asserting the server picks the higher-q format), and an Accept-Encoding probe (gzip, br) asserting the response is correctly encoded with a matching Content-Encoding. For the consumes kind add a missing-Content-Type probe (a body sent with no Content-Type header, asserting the documented default-or-415 behavior) and a charset-in-Content-Type probe. Add an Accept-Language probe only if the contract documents localization. Keep every existing label and probe; add the new ones with explicit labels and keep the agent's no-network, plan-only contract.
```

### 11. verify-error-message-clarity — 6 → 10
Adds envelope consistency + field detail + status/code alignment + request-id.

```
update-agent api-tester-verify-error-message-clarity go beyond per-code triggering and clarity/no-leak checks. Add assertions that every error body conforms to a single consistent error envelope (the same top-level shape — e.g. {error:{code,message,details}} — across all triggered codes), that a validation 400 names the specific offending field(s) in a machine-readable details array, that the body's machine-readable code value is consistent with the HTTP status (no 200-shaped body on a 404, no "ok" on an error), and that each error response carries a request-id / correlation reference for support. Keep the existing internal-detail-leak checks (stack/SQL/path substrings). Do not duplicate the field-name leakage list maintained by api-tester-check-authorization-rules — reference it — and keep response-schema conformance with api-tester-validate-json-schema-responses; this agent owns human-facing clarity and envelope consistency.
```

### 12. validate-api-versioning-behavior — 6 → 10
Adds header/media-type/query versioning + Sunset + default version.

```
update-agent api-tester-validate-api-versioning-behavior cover versioning mechanisms beyond path-prefix. Add a header-versioning case set (the same request with Accept: application/vnd.<api>.v2+json current and v1 deprecated and an unsupported v0/v99) and, if documented, a query-parameter versioning case (?version=2). Add a "default_version" case that sends no version at all, asserting the documented default-or-explicit-error behavior. Extend the deprecated case to also require a Sunset header (a valid future HTTP-date) and a Link rel="successor-version" alongside the existing Deprecation header. Keep the existing path-based current/deprecated/unsupported cases and the per-version ajv schema validation. Keep all version negotiation here; do not fold in generic Accept/Content-Type negotiation, which stays with api-tester-verify-content-type-negotiation.
```

### 13. test-webhook-delivery — 6 → 10
Adds backoff schedule + DLQ exhaustion + filtering + tamper-reject.

```
update-agent api-tester-test-webhook-delivery extend the register/trigger/poll/assert/retry plan past a single retry. Add an event-filtering case: register a receiver for only a subset of event types and assert non-subscribed events are NOT delivered while subscribed ones are. Add a multi-retry backoff case: force repeated 500s and assert redelivery follows the documented increasing backoff schedule (capture per-attempt timestamps) and that after the documented max attempts the delivery is moved to a dead-letter / disabled state. Add a non-retryable case: a 4xx receiver response is NOT retried. Add a signature-negative assertion: a payload whose body is altered fails HMAC verification (the test consumer rejects it), proving the signature is meaningful, in addition to the existing valid-signature assertion. Keep delivery-deadline, exact event_type/resource_id, ISO timestamp, and HMAC header/format assertions. This agent owns HTTP-callback webhooks; defer message-topic/broker semantics to api-tester-test-event-driven-api-triggers.
```

### 14. test-timeout-handling — 6 → 10
Adds slow-client + connect/read split + retry-on-timeout + safe-body.

```
update-agent api-tester-test-timeout-handling extend the upstream-timeout plan with the client- and connection-side timeout cases. Add a slow-client / slowloris case (the client dribbles the request body slower than the server's request-read budget, asserting the server closes with the documented 408-class response and does not hang). Add a distinction between connect timeout and read timeout for the upstream call (assert the documented status for each). Add a "retry_on_timeout" assertion if the contract documents server-side retry of the upstream before failing (assert it retries the documented number of times within max_wait_s). Strengthen the delayed case with an explicit "safe_error_body" assertion that the timeout response body is a clean documented error with no upstream URL, stack, or internal host leaked. Keep max_wait_s = upstream_timeout_s + buffer_s and the per-endpoint delayed/restore probes. Keep gateway-routing concerns with api-tester-test-api-gateway-routing.
```

### 15. test-concurrent-request-handling — 6 → 10
Adds lost-update/optimistic-lock + same-unique-key race.

```
update-agent api-tester-test-concurrent-request-handling add the contention cases the 50-way read/write plan doesn't cover. Add a "concurrent_update_same_row" case: fire N simultaneous PUT/PATCH against one resource and assert the documented concurrency control holds — either optimistic locking rejects stale writers with 409/412 (and exactly one winner) or the final persisted value equals exactly one of the submitted values with no lost-update torn write. Add a "concurrent_create_same_unique_key" case: N simultaneous POSTs with an identical unique field, asserting exactly one 201 and the rest 409, with the database holding exactly one row. Keep the existing concurrent read (identical bodies) and concurrent write (unique per-VU id, DB count-delta / zero-duplicate / zero-missing) cases and assert_zero_500. Keep sequential idempotent replay with api-tester-test-idempotency-of-endpoints; this agent owns parallel races.
```

### 16. verify-sorting-behavior — 6 → 10
Adds multi-field + stability + numeric + null ordering + sort×paging.

```
update-agent api-tester-verify-sorting-behavior extend the six-case single-field plan. Add a numeric sort field to the seed (e.g. a price/score with deliberately non-sequential values) and assert numeric ordering, not lexicographic (so 9 sorts before 100). Add a multi-field / secondary-sort case (sort by a field with ties, then by a tiebreaker) and a stability assertion that equal primary keys retain secondary order. Add a null-ordering case (seed some null sortable values) asserting the documented nulls-first or nulls-last rule. Add a case-sensitivity assertion for string sort per the documented collation. Add a sort+pagination interaction case asserting ordering is stable and correct across page boundaries. Keep the existing asc/desc-by-name, asc/desc-by-created_at, invalid-field 400, and invalid-order 400 cases and the adjacent-pair ordering check. This agent owns all ordering; the invalid-order probe should be removed from api-tester-validate-query-parameter-handling (note that in the prompt).
```

### 17. validate-search-and-filter-queries — 6 → 10
Adds range/substring/case/multi-value/injection; defers param mechanics.

```
update-agent api-tester-validate-search-and-filter-queries derive filters from the documented filter list instead of the hardcoded status/category pair, and add the semantic cases. Add a range-filter case (numeric/date gte+lte, asserting only in-range records return), a substring/full-text search case (q= partial term, asserting all and only matching records) with a case-insensitivity assertion, a multi-value filter case (status=a,b returns the union), and a negation case if documented. Add an injection-safety case: a filter value containing SQL/NoSQL metacharacters returns a normal filtered/empty result or 400 and never an error or unfiltered dump. Keep the every-returned-record-matches-all-filters invariant and the response-count-equals-DB-count check, and keep the existing single/multi/invalid/unknown/empty cases. Defer generic param type-coercion/encoding/defaults to api-tester-validate-query-parameter-handling and page math to api-tester-test-pagination-behavior.
```

### 18. verify-third-party-oauth-integration — 6 → 10
Adds the negative-path security cases + PKCE.

```
update-agent api-tester-verify-third-party-oauth-integration add the negative and security stages the happy-path five-stage flow omits. Add cases asserting: a callback whose state does not match the authorize state is rejected (CSRF protection), a token exchange with a redirect_uri different from the registered one is rejected, an authorization code replayed a second time is rejected (single-use), an expired authorization code is rejected, and a token exchange with a wrong client_secret is rejected. Add a PKCE block if documented (authorize sends code_challenge, token exchange must present the matching code_verifier and a mismatch is rejected). Add an error-redirect case (user denies consent → access_denied returned to the callback). Keep the existing redirect / code_receipt / token_exchange / access_token_use / token_refresh happy-path stages and their asserts. Keep first-party credential validity with api-tester-test-authentication-flows.
```

### 19. validate-correlation-id-propagation — 6 → 10
Adds malformed-id handling + W3C trace; stays the correlation-id owner.

```
update-agent api-tester-validate-correlation-id-propagation deepen correlation-id semantics so it clearly owns this surface versus api-tester-validate-header-propagation. Keep the with-header / no-header (UUIDv4 auto-gen) structure and the downstream-log assertions, and add: a malformed-correlation-id case set (an over-long id, an id containing CRLF or control characters, and an id with injection metacharacters) asserting the server rejects-or-sanitizes per contract and never reflects the raw value into logs unescaped; a uniqueness assertion that two no-header requests generate two different UUIDv4 values; a "correlation_id_in_error" assertion that an error response on this endpoint still echoes the correlation id; and, if the contract uses W3C trace context, an assertion that the correlation id maps into the trace-id consistently. Hand off generic forwarding of Authorization / traceparent / X-Forwarded / custom headers and hop-by-hop stripping to api-tester-validate-header-propagation and do not duplicate them.
```

### 20. verify-caching-headers — 6 → 10
Adds Last-Modified + Vary + If-Match/412 + freshness correctness.

```
update-agent api-tester-verify-caching-headers extend the cacheable-GET / update / four-mutation plan. Add a Last-Modified / If-Modified-Since conditional case alongside the existing ETag / If-None-Match 304 case (assert a 304 with empty body when unmodified). Add a Vary-header assertion that the documented Vary (e.g. Accept, Accept-Encoding) is present on cacheable responses. Add an If-Match precondition case on the update: a stale ETag in If-Match yields 412 Precondition Failed and the row is unchanged. Add a freshness assertion that Cache-Control max-age/s-maxage (and no-store on mutations) match the documented values, not merely that the header exists. Keep the post-update ETag-change assertion and the mutation no-store checks. Keep idempotent-replay semantics with api-tester-test-idempotency-of-endpoints.
```

### 21. test-event-driven-api-triggers — 6 → 10
Adds duplicate/out-of-order/replay + poison-retry + ordering.

```
update-agent api-tester-test-event-driven-api-triggers extend the well-formed / malformed plan with delivery-semantics cases. Add a duplicate-event case (publish the same well-formed event twice with the same event id, asserting the consumer is idempotent and the resource reaches the expected state exactly once with no double-apply). Add an out-of-order case (publish two ordered events for the same key in reverse, asserting the documented ordering/versioning rule — later state wins or the stale event is dropped). Add a poison-message case asserting the consumer retries the documented number of times before dead-lettering, not an immediate DLQ. Keep the well-formed-within-5s state change and the malformed → ERROR-log + DLQ-within-30s + state-unchanged + consumer-health assertions. This agent owns broker/topic message semantics; defer HTTP-callback delivery to api-tester-test-webhook-delivery.
```

### 22. verify-audit-log-generation — 6 → 10
Adds read/failed/auth-event audit + immutability + before/after.

```
update-agent api-tester-verify-audit-log-generation extend the create/update/delete audit plan. Add a read-audit case if the contract requires GETs on sensitive resources to be logged. Add a failed-action audit case: a denied (403) or unauthenticated (401) attempt must still produce an audit entry with the outcome recorded. Add an auth-event case: login and logout generate audit entries. Add a before/after-value assertion on the update entry (the entry captures old and new field values). Add an immutability assertion: an attempt to modify or delete an existing audit entry via the API is rejected. Keep the three-entry CREATE/UPDATE/DELETE expectation, the required-fields set (user_id, action_type, resource_id, timestamp, ip_address), the time window, and the timestamp tolerance. Keep correlation/trace log propagation with api-tester-validate-correlation-id-propagation; this agent owns audit semantics.
```

### 23. test-api-gateway-routing — 6 → 10
Adds path-rewrite + LB/weighting + unknown-route + gateway headers.

```
update-agent api-tester-test-api-gateway-routing extend the single-route correctness plan. Add a path-rewrite case asserting a documented prefix strip / rewrite reaches the backend with the rewritten path (not the gateway path). Add an unknown-route case (a path no backend serves) asserting the gateway returns 404 itself without hitting a backend, and a method-not-allowed-at-gateway case. Add a load-balancing case if multiple instances back one service (repeated requests spread across instances per the documented policy; for weighted/canary, assert the split roughly matches the documented weights). Add a gateway-injected-header assertion that the gateway adds the documented X-Forwarded-For / X-Forwarded-Proto / X-Request-ID before the backend sees the request. Keep the exact-single-backend, body/headers-unchanged, other-backends-untouched, and service-down 503 assertions. Defer upstream timeout behavior to api-tester-test-timeout-handling and header forwarding correctness to api-tester-validate-header-propagation.
```

### 24. test-multipart-form-data-handling — 6 → 10
Repositioned to multipart encoding mechanics; defers file semantics to file-upload.

```
update-agent api-tester-test-multipart-form-data-handling focus this agent on multipart ENCODING mechanics so it stops duplicating api-tester-test-file-upload-and-download. Keep the two-text-part + one-file-part baseline and the create-status / text-exact / document_url / persisted-readback cases, and add encoding-edge cases: a multi-file case (two file parts under the same field name → array, asserting both stored), a part-without-filename case (a file part missing its filename, asserting the documented handling), a duplicate-text-field case (same field name twice, asserting first/last/array policy), a field-order-independence case (file part before text parts, asserting parsing is order-independent), and a malformed-boundary case (a body whose declared boundary doesn't match, asserting 400). Hand the size-limit (oversized→413), MIME-type (wrong-content-type→415), and MD5 round-trip integrity assertions to api-tester-test-file-upload-and-download — reference it and keep only as much as proves the parts were parsed, not the file-handling policy.
```

### 25. validate-retry-after-header-compliance — 6 → 10
Adds HTTP-date variant + 503 Retry-After; stays the Retry-After owner.

```
update-agent api-tester-validate-retry-after-header-compliance sharpen the boundary with api-tester-test-rate-limit-enforcement so this agent solely owns the Retry-After header. Keep the at_limit burst and over_limit→429 structure only as the means to elicit a Retry-After, and add: a format-coverage assertion that the agent verifies BOTH supported Retry-After forms — a positive-integer seconds value and a valid future RFC 7231 HTTP-date — by checking the parsed value is honored regardless of which form the server used; a 503 case that elicits a Retry-After on a maintenance/overload 503 (not only the 429), asserting the same presence/positive/honored rules; and a sanity bound asserting the advertised delay is within a documented reasonable maximum (not absurdly large). Keep the still_limited(-1s)/reset(+1s) deadline-anchored probes. Do NOT assert counting, window reset, per-key isolation, or RateLimit-* headers — those stay with api-tester-test-rate-limit-enforcement.
```

### 26. validate-graphql-depth-limits — 6 → 10
Adds complexity/cost + alias amplification + fragment cycle + introspection + batching.

```
update-agent api-tester-validate-graphql-depth-limits extend beyond pure nesting depth to the related query-cost protections (keeping depth as the core). Add a complexity/cost case: a query that is shallow but very broad (many fields / large requested list sizes) exceeding the documented complexity budget is rejected with a complexity error. Add an alias-amplification case: the same expensive field requested under many aliases is rejected. Add a fragment-cycle case: a circular fragment spread is rejected rather than expanded infinitely. Add an introspection case asserting the documented production introspection policy (disabled → introspection query rejected, or enabled per contract). Add a batched-query case: an array of many operations in one request is capped per the documented batch limit. Keep the depth_3 accept, at_limit accept, one_over reject, and deep_15 timed-reject (<1s) cases and the depth-counting definition (nested selection sets, not characters/tokens).
```

### 27. test-long-polling-support — 6 → 10
Adds queued events + Last-Event-ID resume + concurrent pollers + drop.

```
update-agent api-tester-test-long-polling-support extend the no_event/event two-case plan. Add a "multiple_events" case: two events published during one poll window are both delivered (queued, not just the first). Add a "resume_after_gap" case using the documented cursor / Last-Event-ID: an event published between two polls is not lost — the second poll, carrying the last id, receives it. Add a "concurrent_pollers" case: two clients long-polling the same channel both receive a broadcast event (fan-out) or receive per the documented single-consumer rule. Add a "connection_drop" case: a client that disconnects mid-poll does not wedge the channel and a fresh poll still works. Keep client_max_time_s = poll_timeout_s + 5, the no-event 204-empty-within-window assertion, and the event 200-within-2s-of-trigger with correct event_type assertion. Keep broker-side message semantics with api-tester-test-event-driven-api-triggers.
```

### 28. check-authorization-rules — 7 → 10
Adds owner-positive + cross-tenant IDOR + role mass-assignment.

```
update-agent api-tester-check-authorization-rules extend the eight-case matrix with the access-control cases it misses. Add an owner-positive case: the owner GETs and PUTs their OWN resource and is allowed (200), proving the 403s are scoping and not a blanket block. Add a cross-tenant / IDOR case: a second non-owner, non-admin user requests the owner's resource by id and is denied (403/404) with no field data leaked. Add a horizontal-list case: that second user's collection listing excludes the owner's resource. Add a privilege-escalation / mass-assignment case: a viewer submits a body containing a role or owner_id field attempting to elevate, asserting the field is ignored or rejected and no escalation occurs. Keep the VIEWER_GET/PUT/DELETE 403s, ADMIN_GET 200, VIEWER_ADMIN_ENDPOINT 403, VIEWER_LIST exclusion, NO_TOKEN/BAD_TOKEN 401 controls, and the field/substring leakage assertions. Keep token validity/expiry/revocation with api-tester-test-authentication-flows.
```

### 29. track-defect-density — 7 → 10
Adds severity weighting + per-area density + coverage linkage.

```
update-agent api-tester-track-defect-density enrich the ten-field report toward an actionable dashboard while keeping every existing field and formula. Add a severity-weighted density (P1=8/P2=4/P3=2/P4=1 weighting, or the documented weights) alongside the raw defect_density so a sprint full of P1s isn't equal to one full of P4s. Add a per-area breakdown: group jira_issues by a component/area label and emit per-area defect counts and densities so the hottest module is visible. Add a coverage-linkage field if the brief provides test-coverage data (density per uncovered KLOC). Keep sprint_name, defect_density, rolling_avg_3_sprint, deviation_pct, alert_flag, p1..p4 counts, and trend exactly as defined, and keep the test-file exclusion rules and round-half-up arithmetic deterministic. This stays a pure calculator over the supplied brief — no Jira/git calls.
```

### 30. verify-crud-operation-integrity — 7 → 10
Adds PATCH + negative lifecycle + list membership.

```
update-agent api-tester-verify-crud-operation-integrity extend the six-step CREATE/READ/UPDATE/READ_AFTER_UPDATE/DELETE/READ_AFTER_DELETE plan. Add a PATCH step (partial update) between UPDATE and DELETE with a READ_AFTER_PATCH asserting only the patched field changed and others persisted. Add negative-lifecycle steps: UPDATE_MISSING and DELETE_MISSING against a non-existent id (expect 404) and a CREATE_DUPLICATE against a unique field (expect 409). Add list-membership steps: a LIST after CREATE asserts the new id is present, and a LIST after DELETE asserts it is absent. Add a field-level DB assertion that each persisted column equals what was sent (not merely that a row exists). Keep the backing-table name and the read-only DB verification at each step. Keep soft-delete DB semantics with api-tester-test-soft-delete-behavior and PUT/DELETE replay with api-tester-test-idempotency-of-endpoints.
```

### 31. test-ip-allowlist-enforcement — 7 → 10
Adds CIDR + IPv6 + multi-hop XFF + denylist precedence.

```
update-agent api-tester-test-ip-allowlist-enforcement extend the five-case plan. Add a CIDR/subnet case: an IP inside a documented allowed range is allowed and a sibling IP just outside the range is blocked, proving range matching not just exact-IP. Add an IPv6 case (allowed and blocked v6 addresses) if the contract supports v6. Add a multi-hop X-Forwarded-For case: an XFF chain with several hops asserting the gateway honors only the trusted-proxy-depth client IP and cannot be spoofed by prepending a fake hop. Add a denylist-precedence case if a denylist coexists with the allowlist (an IP on both is blocked). Keep the allowlisted-200, non-allowlisted-403, XFF-spoof-403, allowlist-add-allows, and allowlist-remove-blocks cases and the no-resource-data-on-block assertion.
```

### 32. run-regression-suite — 7 → 10
Adds flaky detection + more reporter formats + duration trend.

```
update-agent api-tester-run-regression-suite extend the build-N-1-vs-N comparison. Add flaky-test detection if the brief supplies repeated runs of build N: a test that both passes and fails across runs is reported in a new "flaky" array and excluded from regressions. Add support for additional reporter formats beyond JUnit XML / Jest --json / pytest-json — TAP and one of TRX/NUnit — selected by the stated reporter format. Add a duration-regression field: tests whose runtime grew beyond a documented multiple of their build-N-1 time are reported in a "slowed" array. Keep the seven existing fields (build_n_nus_1, build_n, total_tests_in_suite, prev_passed_count, regressions, newly_passing, overall_status), the exact regression definition (passed in N-1, failed in N), and the rule that already-failing, skipped, and removed tests are never regressions. Stay a pure two-artifact comparator — no test execution or deployment actions.
```

### 33. test-ssl-tls-enforcement — 7 → 10
Adds HSTS + pinning/OCSP + cipher-order/PFS + SNI.

```
update-agent api-tester-test-ssl-tls-enforcement extend the protocol/cert/cipher plan. Add an HSTS assertion that HTTPS responses carry Strict-Transport-Security with a documented max-age (and includeSubDomains/preload if required). Add a forward-secrecy/cipher-order assertion that the negotiated suite uses ECDHE (PFS) and that the server enforces its own cipher order. Add a certificate-revocation assertion (OCSP stapling present, or the chain is not revoked) alongside the existing not_expired/cn_or_san_match/chain_of_trust_ok/not_self_signed checks. Add an SNI case (a handshake with the correct SNI succeeds and a wrong/empty SNI behaves per contract) and a wildcard-scope assertion if a wildcard cert is used. Keep the five protocol probes (plain-HTTP reject, TLS1.0/1.1 reject, TLS1.2/1.3 accept) and the five forbidden weak-cipher families (RC4, DES, 3DES, EXPORT, NULL).
```

### 34. test-bulk-operation-endpoints — 7 → 10
Adds all-valid/empty/single/duplicate + atomic mode + bulk update/delete.

```
update-agent api-tester-test-bulk-operation-endpoints extend the mixed / all-invalid / oversize batch plan. Add an all-valid batch case (every item valid → all per-item 2xx, DB delta = batch size). Add an empty-batch case ([] → documented 400-or-200-empty) and a single-item batch case. Add a duplicate-within-batch case (two items with the same unique key → one succeeds, one per-item 409). Add an atomicity case if the endpoint documents a transactional mode: in all-or-nothing mode one invalid item rolls back the whole batch (DB delta = 0), versus the partial-success 207 default. Add bulk-update and bulk-delete variants if the endpoint supports them (not just bulk-create), asserting per-item results and DB state. Keep the 8-valid + 1-missing-required + 1-wrong-type → 207 multi-status case, the per-item 2xx/400 offending-field naming, the oversize rejection, and the DB-delta = valid-count assertion.
```

### 35. measure-api-consumer-satisfaction — 7 → 10
Adds CSAT/CES + segmentation + quarter-over-quarter trend.

```
update-agent api-tester-measure-api-consumer-satisfaction broaden the NPS measurement plan into a fuller satisfaction dashboard while keeping every existing field and constant. Add a CSAT question/metric (a 1-5 satisfaction item with a documented top-2-box formula) and a CES question/metric (ease-of-use), each with its own band/formula, alongside the existing NPS scale_0_10. Add a segmentation block that computes NPS/CSAT per consumer segment (e.g. by plan tier or call-volume band from the usage fixture) so a single blended score isn't the only output. Add a quarter-over-quarter trend field (current NPS vs the prior period with a delta). Keep the 90-day recipient window, the four verbatim survey questions, the 14-day collection window, the promoter/passive/detractor bands, the round(promoter_pct - detractor_pct) formula, the 30% validity threshold, the k-means/TF-IDF top-3-themes config, and the ten dashboard fields. Stay plan-only over the local fixture.
```

### 36. verify-enum-value-restrictions — 7 → 10
Adds numeric enums + array/multi-select + whitespace + unicode look-alike.

```
update-agent api-tester-verify-enum-value-restrictions extend the six-key enum matrix. Add numeric-enum support: for integer/number enum fields, emit valid_values from the numeric VALID_ENUMS and off-enum probes using an out-of-set number and a stringified number ("1" where 1 is valid) asserting the documented type strictness. Add an array/multi-select case for fields whose value is an array of enum members (a valid multi-select accepted, an array containing one off-enum member rejected). Add a whitespace-padded case (" ACTIVE " for a valid ACTIVE) asserting it is rejected or trimmed per contract, and a unicode-look-alike case (a Cyrillic/full-width character resembling a valid value) asserting rejection. Keep valid_values, unknown_string, empty_string, null_value (nullability judged elsewhere), wrong_type(0), and case_variant. Keep enum-in-query-parameter probes out of scope — those belong to api-tester-validate-query-parameter-handling and api-tester-verify-sorting-behavior; this agent owns request-body enums.
```

### 37. test-soft-delete-behavior — 7 → 10
Adds restore + double-delete + update-deleted + unique-key reuse + cascade.

```
update-agent api-tester-test-soft-delete-behavior extend the create→delete→verify lifecycle. Add a restore/undelete case if the contract documents it (POST/PATCH restore → resource reappears in the collection, deleted_at cleared, is_deleted=false). Add a double-delete case: deleting an already-soft-deleted resource returns the documented 404/409 and does not change deleted_at. Add an update-deleted case: a PUT/PATCH on a soft-deleted resource is rejected (404/409). Add a unique-key-reuse case: after soft-deleting a resource, creating a new one with the same unique field succeeds (or fails) per the documented rule. Add a cascade case if children exist: soft-deleting a parent soft-deletes its children. Keep the DELETE 200/204, GET-by-id exactly-404 with no field leak, absent-from-collection, present-under-?include_deleted, and the DB row-survives / deleted_at-not-null-within-tolerance / is_deleted=true assertions, over case_count lifecycles. Keep hard-delete lifecycle with api-tester-verify-crud-operation-integrity.
```

### 38. validate-null-empty-fields — 8 → 10
Adds whitespace-only + null inside nested/array element (already the absent/null owner).

```
update-agent api-tester-validate-null-empty-fields close the two remaining gaps in the already-strong null/empty matrix. Add a "whitespace_only" state to the required_state and optional_state sets: the field present with a value of one or more space characters ("   "), asserting the documented trim-then-reject or accept behavior, distinct from empty_string. Add a "nested_null" set: for any field whose type is object or array, one payload with a null in a required SUB-field one level down, and one with a null as the first array element, asserting deep null handling rather than only top-level null. Keep required_state (7 states/field), optional_state (6 states/field), all_required_null, each_required_null, combo_required_null (pairwise or first-half), and string_null ("null" the 4-char string). This agent remains the sole owner of absent/null/empty/whitespace states — api-tester-validate-request-payloads defers all of these here.
```

### 39. test-file-upload-and-download — 6 → 10
Adds 0-byte + magic-byte/MIME mismatch + path-traversal + download authz/404; defers multipart parsing.

```
update-agent api-tester-test-file-upload-and-download focus this agent on file SEMANTICS and security so it complements api-tester-test-multipart-form-data-handling rather than duplicating it. Keep the size-limit (1KB / exactly max_size_bytes / max_size_bytes+1 over), allowed-vs-invalid MIME, and the download byte-for-byte MD5 round-trip cases, and add: a 0-byte (empty) file case asserting the documented accept-or-reject; a magic-byte-vs-declared-MIME mismatch case (a file whose declared Content-Type is image/jpeg but whose bytes are not a JPEG) asserting content sniffing rejects it; a path-traversal filename case (a filename like ../../evil.sh) asserting the stored name is sanitized and no traversal occurs; a download-nonexistent case (GET a never-uploaded or already-deleted file id, expect 404 with no bytes); and a download-authorization case (a second user cannot download the first user's file, expect 403/404 with no bytes). Add a Content-Disposition filename assertion on successful downloads. Hand the multipart parsing mechanics (text+file parts, boundary edges, duplicate/no-filename parts, field-order independence) to api-tester-test-multipart-form-data-handling; this agent owns file size/MIME/integrity/security and the download path.
```

### 40. (spare / cross-cutting) verify-response-status-codes follow-up — optional 40th
A 40th prompt is available if you want to split the status-code generalist into two passes
(success-class vs error-class) rather than one combined update:

```
update-agent api-tester-verify-response-status-codes after the 405/409/422/204/redirect/410 additions land, split the emitted descriptors into a "success_class" group (2xx/3xx: 200, 201, 202, 204, 301, 302) and an "error_class" group (4xx/5xx this agent owns: 400, 404, 405, 409, 410, 422, 500), each in documented order, so the harness can report conformance per class. Keep deferring 401 to api-tester-test-authentication-flows, 403 to api-tester-check-authorization-rules, 406/415 to api-tester-verify-content-type-negotiation, and 429 to api-tester-test-rate-limit-enforcement, and do not emit those codes here.
```

---

## How to run these

Pick an agent (lowest score first is the highest-leverage order), paste its block, and the
`update-agent` skill applies the change through the full v2 flow (debate gate per changed line,
determinism + 95 code-quality gate on regenerated runners, `/analyze`, re-judge, the 10-round
keep-if-improved tournament, the dynamic code-review gate at ≥85, and golden regression
protection). Because each prompt only *adds* cases and explicitly fences off another agent's
territory, none of them should regress a baseline or create new overlap.

> Note: scores are coverage judgments based on each agent's named workflow and current emitted
> cases, not on a live run. After an update lands, the skill's own re-judge produces the real
> post-change metric.

