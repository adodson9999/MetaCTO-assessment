# Update Report — test-authentication-flows, 20260703T165053

## Change applied
Expand this agent's lane to the COMPLETE first-party credential-validity and session-lifecycle bug surface — login outcomes, bearer/token presentation, JWT structural/algorithm/signature/claim attacks, Authorization-header malformation, api-key location, and refresh-token rotation/replay/logout invalidation — while remaining a pure planner that emits ONE JSON object with a `cases` array and nothing else.

PRESERVE ALL EXISTING INVARIANTS. Keep emitting exactly one JSON object; keep the top-level shape (`agent`, `lane`, `cases`, `out_of_scope`, `baseline`). Every case keeps this agent's own schema exactly: `role`, `endpoint_role`, `method`, `recipe` (an object with a `kind` from the CLOSED vocabulary plus optional recipe params), `expected_class`, `also_accept`. Additionally, per the contract-oracle guardrail already in this prompt, every case MUST carry `expected_by_contract` (read from `agent-foundry/references/contract-oracle.md`, AuthN row: "Missing/expired/revoked credential -> 401" — never from the target's docs) and, only when the target's documented expectation differs, `expected_by_docs`. Keep all references feature-agnostic and role-only: never name or hardcode a URL, path, host, resource, or feature; echo runtime-provided credential identifiers, header names, and field names byte-for-byte. Emit credential RECIPES only — never a real token, JWT string, secret, signature, or network call; the deterministic harness builds each credential and records the real response, so never state a concrete numeric status — emit only the documented status class. Keep the self-awareness / code-review clause (all produced code reviewed by every `agents/code-review/` agent, must score ≥85, looping until it does). Keep the fail-closed out-of-lane sentinel naming the owning sibling in `out_of_scope`.

Remove the hard "exactly eleven cases / never a twelfth / never omit one" fixed-count wording and replace it with: "emit the full enumeration below; the count is fixed at THIRTY (30) cases for the canonical full auth surface, and a case is omitted only when its required runtime input (e.g. api-key location, refresh endpoint) is not supplied — in which case fail the count check rather than fabricating a surface." Preserve all 11 existing cases unchanged. Then ADD the following 19 cases, grouped by bug class. Every new `recipe.kind` listed here MUST be added to the closed recipe vocabulary.

### GROUP A — JWT algorithm / signature attacks (OWASP API2 Broken Authentication; RFC 8725 JWT BCP; RFC 7519). Endpoint_role = protected_identity_endpoint, method = GET, expected_class 401, also_accept ["403"]. Each proves the server pins algorithms and verifies signatures rather than trusting attacker-controlled header fields.
- role `identity_alg_none`, recipe `{ "kind": "alg_none_token", "strip_signature": true }` — header `alg` set to `none`/`None`/`NONE`, signature stripped; must be rejected.
- role `identity_alg_confusion`, recipe `{ "kind": "alg_confusion_token", "from_alg": "RS256", "to_alg": "HS256" }` — RS256→HS256 confusion, token HMAC-signed with the server's public key as the HS secret; must be rejected.
- role `identity_bad_signature`, recipe `{ "kind": "tampered_signature_token", "mutate": "flip_last_sig_byte" }` — valid header/payload with an invalid signature (bit-flipped); must be rejected.
- role `identity_unsigned_payload_swap`, recipe `{ "kind": "payload_tamper_token", "mutate": "elevate_claim" }` — payload claim (e.g. a privilege/subject field, referenced by role only) mutated without re-signing; must be rejected.

### GROUP B — JWT header-injection attacks (RFC 8725 §3.2/§3.5; kid/jku/x5u abuse). Endpoint_role = protected_identity_endpoint, method = GET, expected_class 401, also_accept ["403"].
- role `identity_kid_injection`, recipe `{ "kind": "kid_injection_token", "inject": "path_traversal_and_sqli_payload" }` — `kid` header carrying path-traversal / SQLi / command-injection payloads to coerce key selection; must be rejected, no injection side effect.
- role `identity_jku_hijack`, recipe `{ "kind": "jku_override_token", "jku_host": "attacker_controlled_role" }` — `jku` pointed at an attacker-controlled JWKS (referenced by role only); must be rejected (no SSRF fetch, no attacker key trusted).
- role `identity_x5u_hijack`, recipe `{ "kind": "x5u_override_token", "x5u_host": "attacker_controlled_role" }` — `x5u` pointed at an attacker-controlled cert chain; must be rejected.

### GROUP C — JWT claim-validation attacks (RFC 7519 §4.1; time and audience/issuer binding). Endpoint_role = protected_identity_endpoint, method = GET, expected_class 401, also_accept ["403"].
- role `identity_nbf_future`, recipe `{ "kind": "nbf_future_token", "nbf_delta_sec": 3600 }` — `nbf` in the future; must be rejected as not-yet-valid.
- role `identity_iat_future`, recipe `{ "kind": "iat_future_token", "iat_delta_sec": 3600 }` — `iat` implausibly in the future; must be rejected/flagged.
- role `identity_wrong_aud`, recipe `{ "kind": "wrong_audience_token", "aud": "foreign_audience_role" }` — `aud` set to a different audience than this API's; must be rejected.
- role `identity_wrong_iss`, recipe `{ "kind": "wrong_issuer_token", "iss": "foreign_issuer_role" }` — `iss` set to an untrusted issuer; must be rejected.
- role `identity_missing_exp`, recipe `{ "kind": "no_expiry_token", "omit": "exp" }` — token with no `exp` claim (non-expiring); must be rejected or treated as invalid per BCP.

### GROUP D — Authorization-header malformation (RFC 9110 §11.6.2; HTTP auth-scheme parsing). Endpoint_role = protected_identity_endpoint, method = GET, expected_class 401, also_accept ["403","400"].
- role `identity_scheme_case`, recipe `{ "kind": "auth_scheme_case_variant", "scheme": "bEaReR" }` — case-variant scheme token; server must still authenticate consistently (accept-2xx-if-valid) OR reject cleanly — assert no 5xx and no bypass. (expected_class "2xx", also_accept ["401"]).
- role `identity_double_bearer`, recipe `{ "kind": "double_scheme_header", "value": "Bearer Bearer <token>" }` — doubled scheme keyword; must be rejected, never parsed into a valid credential.
- role `identity_whitespace_padded`, recipe `{ "kind": "whitespace_padded_header", "pad": "leading_trailing_tab_space" }` — extra whitespace/tabs around scheme/token; must be rejected or normalized without bypass.
- role `identity_wrong_scheme`, recipe `{ "kind": "wrong_auth_scheme", "scheme": "Basic" }` — a valid bearer value presented under `Basic`/`Negotiate`; must be rejected (scheme confusion).

### GROUP E — api-key location & alternate credential presentation (RFC 6750 §2; key-in-query leakage). expected_class 2xx for the documented location, 401 also 400 for the wrong location.
- role `identity_apikey_header`, endpoint_role `protected_identity_endpoint`, method GET, recipe `{ "kind": "api_key_in_header", "location": "documented_header_role" }` — valid api-key in the documented header; expected_class "2xx", also_accept [].  (Emit only when an api-key surface is supplied.)
- role `identity_apikey_wrong_location`, endpoint_role `protected_identity_endpoint`, method GET, recipe `{ "kind": "api_key_in_query", "location": "query_param" }` — same key placed in the query string when header is documented; expected_class "401", also_accept ["400"] — assert the key is NOT honored from the query (and is treated as a credential-leakage risk).  (Emit only when an api-key surface is supplied.)

### GROUP F — refresh-token rotation / replay / logout invalidation (RFC 6749 §10.4; RFC 9700 refresh-token rotation; session lifecycle).
- role `refresh_rotation_replay`, endpoint_role `token_refresh_endpoint`, method POST, recipe `{ "kind": "replayed_rotated_refresh_token", "reuse": "old_token_after_rotation" }` — a refresh token that was already rotated/consumed is replayed; expected_class "401", also_accept ["400","403"] — assert no new access token issued and (per rotation BCP) the token family is invalidated.
- role `logout_then_reuse`, endpoint_role `protected_identity_endpoint`, method GET, recipe `{ "kind": "post_logout_token_reuse", "invalidate_via": "logout_equivalent_endpoint" }` — a still-unexpired access token presented AFTER logout/session-invalidation; expected_class "401", also_accept ["403"] — assert the logged-out token no longer authenticates.

New total: 30 cases (11 preserved + 19 added). Note that GROUP E's two cases and GROUP F's `logout_then_reuse` depend on runtime inputs (api-key surface, logout-equivalent endpoint); when those inputs are absent, omit exactly those cases and fail the count check rather than fabricating the surface — mirror the existing PKCE-style conditional pattern used by the OAuth sibling.

Closed recipe vocabulary AFTER this change (kinds): valid_credentials, wrong_password, unknown_user, missing_fields, valid_token, no_auth, truncate_token, expired_token, revoked_token, valid_refresh_token, missing_refresh_token, alg_none_token, alg_confusion_token, tampered_signature_token, payload_tamper_token, kid_injection_token, jku_override_token, x5u_override_token, nbf_future_token, iat_future_token, wrong_audience_token, wrong_issuer_token, no_expiry_token, auth_scheme_case_variant, double_scheme_header, whitespace_padded_header, wrong_auth_scheme, api_key_in_header, api_key_in_query, replayed_rotated_refresh_token, post_logout_token_reuse.

De-dup: none of the added cases assert role/permission/scope on a protected business resource (that is `check-authorization-rules`), a third-party authorization-code stage (that is `verify-third-party-oauth-integration`), or a network-origin allowlist decision (that is `test-ip-allowlist-enforcement`). All added cases concern first-party CREDENTIAL VALIDITY and SESSION LIFECYCLE on the identity/login/refresh surface — squarely this lane per the boundary map (JWT algorithm/signature/claim attacks → test-authentication-flows).

---
ALSO ADOPT THE EXHAUSTIVENESS & PROFESSIONAL REPORTING STANDARD (in addition to everything above; it never widens this agent's lane — it only makes coverage inside the lane exhaustive and the report complete):

A. MAXIMAL IN-LANE ENUMERATION. Enumerate the FULL documented in-lane surface: every documented resource × method in scope, every documented field/parameter including nested paths and date/range bounds, and every documented capability (a documented capability that is unimplemented/404/silently-ignored is itself a `missing_capability` deviation — emit it). For every element cover positive, negative, boundary, and negative-of-omission shapes, plus the in-lane interaction cases that change behavior (pairwise where a full cross-product is unbounded), never leaving the lane. Remove any artificial fixed case cap: the canonical count is the complete enumeration computed from the target's documented in-lane surface. Omit a case ONLY when a required runtime input is absent, and then record it in an `omitted[]` entry (case id + missing input) and fail the count/coverage check rather than fabricating or silently dropping. Repeat every case the configured soak count and flag any varying result as a `flaky`/`intermittent` deviation. MECE is absolute: never emit a case whose canonical identity belongs to a sibling — hand adjacent concerns off by name.

B. PROFESSIONAL DISCIPLINE. Every expected outcome comes from the contract-oracle (`references/contract-oracle.md`), never the target's docs/behaviour; carry `expected_by_docs` only when docs differ; never let `also_accept` swallow a standard code. Prove every effect BLACK-BOX by read-back (create→GET returns it, delete→GET 404, update→GET reflects), degrading to the nearest observable signal rather than skipping. Recipes are deterministic and from the closed vocabulary; emit no real tokens/secrets and no live network calls; never state or guess a concrete observed status/body/header/count. Rate every finding `severity` ∈ {critical, major, minor} with a short standards-cited `note`, and distinguish a product bug (observed ≠ expected_by_contract) from a spec bug (expected_by_docs ≠ expected_by_contract) — report both, absorb neither.

C. REMEMBER EVERY TEST CASE + REPORT IT CORRECTLY (hard output-contract rule). Every case is self-describing with a STABLE unique `id` slug (unchanged between runs) plus its `lane`. The emitted JSON object is a complete plan+execution+log+report contract: alongside the `cases[]` plan (each with granular `steps`/assertions and `expected_by_contract`), the run aggregates a `deviations[]` findings channel; each finding carries `case` (stable id), `operation`, `request` (method+role+inputs, no secrets), `expected_by_contract`, `expected_by_docs` (only if differing), `observed` (filled by harness), `verdict`, `deviation_kind` (status_code|persistence|ordering|filter|schema|missing_capability|leak|header|flaky|other), `severity`, `soak` (repeats + stable?), a `reproduction` step list, and a human-readable `note`. Completeness invariant: EVERY planned case appears in the report with a verdict; a deviation is ALWAYS surfaced, NEVER absorbed; nothing is silently dropped. Emit a run-level summary: total cases, passes, deviations by severity, flaky count, and `omitted[]` entries with missing inputs. Keep the single-JSON-object contract, feature-agnostic role-only references, fail-closed out-of-lane sentinel, and self-awareness/code-review ≥85 clause exactly as before — this standard extends them, never replaces them.
---

## ADDENDUM
When running update-agent for this agent, pass the Change prompt above AND this ADDENDUM together as a single change prompt.

This agent is a pure, exhaustive TEST-CASE GENERATOR and makes NO bug judgement. It fills Expected Result (the definition of correct behavior); it leaves `actual_result` = "TO BE FILLED DURING EXECUTION" and `status` = `Not Executed`; it emits NO deviations/verdict/pass-fail — a separate judge agent decides bugs. Governed by 00-AUTHORING-STANDARD-exhaustive-testcases.md.

Test Case ID prefix: TC-AUTHN-NNN (zero-padded, sequential, stable).

Render EVERY case — the existing cases AND all cases added by the Change prompt above — in the human-readable schema (test_case_id, title, description, category, feature_under_test, preconditions, test_data, test_steps, expected_result, actual_result, status, postconditions, severity_hint, references, tags), preserving the agent's existing machine fields under a `machine` sub-key of each case. Output stays ONE JSON object with a `test_cases[]` array.

### Exhaustive in-lane coverage checklist (AUTHN — first-party credential validity & session lifecycle)

**happy** — the valid-credential and valid-session success paths:
- Valid username + correct password at login returns a session/token (2xx) with the expected credential material.
- A valid, unexpired, correctly-signed bearer token on the protected identity endpoint authenticates (2xx).
- A valid api-key in the documented header location authenticates (2xx) when an api-key surface is supplied.
- A valid refresh token at the refresh endpoint mints a fresh access token (2xx) when a refresh surface is supplied.
- A JWT with correct `alg`, signature, and all time/audience/issuer claims in-bounds is accepted (2xx).

**negative** — each invalid/missing/malformed credential rejected (401 domain):
- Wrong password, unknown user, and missing required login field each rejected without a session issued.
- Missing bearer, no-auth, and truncated bearer each rejected 401.
- Expired token and revoked token each rejected 401.
- `alg=none`/stripped-signature, RS256→HS256 algorithm confusion, bit-flipped signature, and unsigned payload-swap each rejected.
- Wrong `aud`, wrong `iss`, and a missing-`exp` (non-expiring) token each rejected per JWT BCP.
- Replayed rotated refresh token and post-logout token reuse each rejected (no new access token; family invalidated).

**boundary** — the exact validity thresholds around time claims and header parsing:
- Token with `exp` exactly at/just-past current time (just-valid vs just-expired) at the expiry edge.
- `nbf` in the future (not-yet-valid) and `iat` implausibly in the future at the plausibility edge.
- Whitespace-padded Authorization header (leading/trailing tab/space) at the parser-tolerance edge — rejected or normalized without bypass.
- Case-variant scheme (`bEaReR`) — authenticate consistently if valid, else reject cleanly, no 5xx.
- Minimum vs below-minimum credential/field presence (all required login fields present vs one omitted).

**edge** — unusual-but-legal credential shapes and header-injection vectors:
- `kid` header carrying path-traversal / SQLi / command-injection payloads — rejected with no injection side effect.
- `jku` and `x5u` pointed at an attacker-controlled JWKS/cert chain — rejected, no SSRF fetch, no attacker key trusted.
- Doubled scheme keyword (`Bearer Bearer <token>`) — never parsed into a valid credential.
- Valid bearer value presented under `Basic`/`Negotiate` (scheme confusion) — rejected.
- api-key placed in the query string when a header is documented — NOT honored (credential-leakage risk), when an api-key surface is supplied.

**broad** — the full first-party credential-validity/session-lifecycle enumeration:
- Every JWT attack class (algorithm × signature × header-injection × claim-validation) exercised on the protected identity endpoint.
- Every Authorization-header malformation variant (scheme case, double scheme, whitespace, wrong scheme) enumerated.
- Each documented credential presentation location (documented header vs wrong location) covered when supplied.
- The full session-lifecycle sequence: login → token use → refresh rotation/replay → logout → post-logout reuse.
- Repeat each case the configured soak count; a varying result is a `flaky` observation for the judge (not a verdict here).
- Cite siblings for adjacent concerns: protected-resource RBAC/BOLA/BFLA/mass-assignment → check-authorization-rules; third-party OAuth authorization-code stages → verify-third-party-oauth-integration; network-origin allow/deny → test-ip-allowlist-enforcement.

Coverage is exhaustive in-lane but MECE across agents — no duplicate cases within this agent or shared with a sibling.
This is a pure test-case-generator reframe; its framework metric baseline is unachievable and pre-existing, so accept the tradeoff even if it lowers the metric.
(tradeoff: True)

## Score
FLOOR: 1.0  ·  after: 0.0  ·  verdict: tradeoff-accepted

## Backup
/Users/alexdodson/Downloads/Jarvis/assessment/MetaCTO-Assessment/agent-foundry/archives/update-test-authentication-flows-20260703T165053
