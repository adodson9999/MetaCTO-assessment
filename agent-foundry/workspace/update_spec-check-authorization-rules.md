# Update Spec — check-authorization-rules

## User prompt
Expand this agent's lane to the COMPLETE authorization/access-control bug surface on protected resources — object-level authorization (BOLA/IDOR), function-level authorization (BFLA), property-level authorization / mass-assignment (BOPLA), privilege escalation, HTTP-method-override and path-case bypass, and per-case field + substring leakage — while remaining a pure planner that emits ONE JSON object with a `cases` array and nothing else.

PRESERVE ALL EXISTING INVARIANTS. Keep emitting exactly one JSON object; keep the top-level shape (`agent`, `lane`, `baseline`, `cases`, `out_of_scope`). Every case keeps this agent's own schema exactly: `role`, `endpoint_role`, `method`, `recipe` (an object with `kind` from the CLOSED vocabulary, plus optional attack sub-objects like `cross_tenant_idor`), `expected_class`, `also_accept`, and `leakage` (the assertion block with `assert_no_forbidden_field_value`, `assert_no_internal_detail_substring`, `no_resource_data_on_failure`). Per the contract-oracle guardrail already in this prompt, every case MUST carry `expected_by_contract` (read from `agent-foundry/references/contract-oracle.md`, AuthZ row: "Insufficient permission -> 403; no cross-tenant data leak" — never from target docs) and, only when docs differ, `expected_by_docs`. Keep the denial-class vocabulary: 401 for missing/invalid auth, 403 for insufficient permission. Keep all references feature-agnostic and role-only — never name a URL/path/host/resource/feature; echo runtime-provided tokens, resource ids, header names, and field names byte-for-byte. Emit authorization RECIPES only — never a real token/secret/JWT/network call; the deterministic harness provisions tokens, sends each case, and records the real response, so never state a concrete numeric status/body/header/count. Keep the self-awareness / code-review clause (≥85, loop until it does) and the fail-closed out-of-lane sentinel naming the owning sibling in `out_of_scope`. Explicitly continue to DEFER credential validity/expiry/revocation to `api-tester-test-authentication-flows`.

Remove the hard "exactly twelve cases / never a thirteenth / never a third endpoint / never omit one" wording and replace with: "emit the full enumeration below; the canonical count is TWENTY-FOUR (24) cases; a case is omitted only when its required runtime input (e.g. an admin-only function endpoint, a writable protected field, a mass-assignment forbidden field) is not supplied — in which case fail the count check rather than fabricating a surface." Preserve all 12 existing cases unchanged (the authorized/unauthorized GET/PUT/DELETE matrix over protected_endpoint_1 and protected_endpoint_2, each with the `cross_tenant_idor` attempt and `leakage` block). Then ADD the following 12 cases, grouped by bug class. Every new `recipe.kind` MUST be added to the closed vocabulary. Every added case carries the SAME `leakage` block as the existing cases (all three flags true).

### GROUP A — BOLA / IDOR direct object reference (OWASP API1:2023). Prove an authenticated-but-unauthorized principal cannot read/mutate another owner's object by id. Method per row, expected_class 403, also_accept ["401"].
- role `bola_read_foreign_object_endpoint_1`, endpoint_role `protected_endpoint_1`, method GET, recipe `{ "kind": "authenticated_foreign_object_id", "cross_tenant_idor": { "target": "foreign_owner_resource_id" } }` — a VALID low-privilege token (not `no_token`) requesting the foreign owner's object id; assert 403 and no_resource_data.
- role `bola_update_foreign_object_endpoint_1`, endpoint_role `protected_endpoint_1`, method PUT, recipe `{ "kind": "authenticated_foreign_object_id", "cross_tenant_idor": { "target": "foreign_owner_resource_id" } }` — same, mutating; assert 403, no write, no leak.
- role `bola_read_foreign_object_endpoint_2`, endpoint_role `protected_endpoint_2`, method GET, recipe `{ "kind": "authenticated_foreign_object_id", "cross_tenant_idor": { "target": "foreign_owner_resource_id" } }`.
- role `bola_enumerable_id_probe_endpoint_1`, endpoint_role `protected_endpoint_1`, method GET, recipe `{ "kind": "sequential_id_enumeration", "cross_tenant_idor": { "target": "adjacent_resource_id" } }` — an adjacent/guessable id (predictable identifier) with a valid token; assert 403/404 and no cross-owner leak.

### GROUP B — BFLA function/method-level authorization (OWASP API5:2023). Prove a low-privilege principal cannot reach privileged functions or elevate via method/verb manipulation. expected_class 403, also_accept ["401","405"].
- role `bfla_admin_function_as_user`, endpoint_role `admin_function_endpoint`, method GET, recipe `{ "kind": "low_priv_token_on_admin_function" }` — a normal-user token calling an admin-only function endpoint (referenced by role); assert 403, no privileged data.  (Emit only when an admin-function endpoint is supplied.)
- role `bfla_method_override_delete`, endpoint_role `protected_endpoint_1`, method DELETE, recipe `{ "kind": "verb_override_privileged_method", "override_via": "x_http_method_override_header" }` — a user-permitted verb tunneled to a privileged verb (e.g. `X-HTTP-Method-Override: DELETE`); assert the override does NOT bypass authorization (403), no state change.
- role `bfla_forbidden_verb_on_owned`, endpoint_role `protected_endpoint_2`, method DELETE, recipe `{ "kind": "unpermitted_verb_for_role" }` — a verb the role is not permitted to use even on its own resource; assert 403/405, no state change.
- role `bfla_path_case_bypass`, endpoint_role `admin_function_endpoint`, method GET, recipe `{ "kind": "path_case_or_trailing_slash_variant" }` — case/trailing-slash/encoding variant of a privileged path used to dodge the authZ rule; assert the variant is still authorized-checked (403), no bypass.  (Emit only when an admin-function endpoint is supplied.)

### GROUP C — BOPLA / mass-assignment / property-level authorization (OWASP API3:2023). Prove the API does not accept privileged/read-only properties from the request body and does not over-return forbidden properties. Method per row, expected_class 2xx-with-property-rejected OR 403.
- role `bopla_mass_assign_privileged_field`, endpoint_role `protected_endpoint_1`, method PUT, recipe `{ "kind": "mass_assignment_privileged_field", "inject_field_role": "privilege_or_role_field" }` — body includes a privilege/role/owner field the caller must not set; expected_class "2xx", also_accept ["400","403","422"]; `leakage` asserts read-back shows the privileged field UNCHANGED (assert_no_forbidden_field_value = the injected value was NOT persisted).  (Emit only when a forbidden writable field is supplied.)
- role `bopla_mass_assign_ownership_transfer`, endpoint_role `protected_endpoint_2`, method PUT, recipe `{ "kind": "mass_assignment_ownership_field", "inject_field_role": "owner_id_field" }` — body attempts to change `owner_id`/tenant to seize the object; expected_class "2xx", also_accept ["400","403","422"]; assert ownership NOT reassigned on read-back.  (Emit only when an owner field is supplied.)
- role `bopla_read_only_field_write`, endpoint_role `protected_endpoint_1`, method PATCH, recipe `{ "kind": "read_only_field_override", "inject_field_role": "server_managed_field" }` — body sets a server-managed/read-only field (e.g. id/created_at/balance role); expected_class "2xx", also_accept ["400","422"]; assert the field is ignored (read-back unchanged).
- role `bopla_excessive_property_leak`, endpoint_role `protected_endpoint_2`, method GET, recipe `{ "kind": "excessive_property_exposure_probe" }` — authorized read; `leakage.assert_no_forbidden_field_value` asserts the success body does NOT include forbidden/sensitive properties (e.g. other users' PII, internal-only fields) — success-path leakage, complementing the failure-path leak checks.

New total: 24 cases (12 preserved + 12 added). GROUP B's admin-function cases and GROUP C's mass-assignment cases depend on runtime inputs (admin-function endpoint, forbidden writable field, owner field); when absent, omit exactly those cases and fail the count check rather than fabricating a surface.

Closed recipe vocabulary AFTER this change (kinds): permitted_token, foreign_owner_token, no_token, authenticated_foreign_object_id, sequential_id_enumeration, low_priv_token_on_admin_function, verb_override_privileged_method, unpermitted_verb_for_role, path_case_or_trailing_slash_variant, mass_assignment_privileged_field, mass_assignment_ownership_field, read_only_field_override, excessive_property_exposure_probe. (The `cross_tenant_idor` sub-object remains an allowed recipe modifier.)

De-dup: no added case tests credential VALIDITY, expiry, or revocation (that is `test-authentication-flows`) — every added case uses an already-valid principal and probes what that principal is ALLOWED to do. No OAuth stage, no network-origin/XFF decision. All added classes map to this lane's reserved rows (BOLA/IDOR, BFLA, mass-assignment/BOPLA, cross-tenant data leak → check-authorization-rules).

## ADDENDUM
When running update-agent for this agent, pass the Change prompt above AND this ADDENDUM together as a single change prompt.

This agent is a pure, exhaustive TEST-CASE GENERATOR and makes NO bug judgement. It fills Expected Result (the definition of correct behavior); it leaves `actual_result` = "TO BE FILLED DURING EXECUTION" and `status` = `Not Executed`; it emits NO deviations/verdict/pass-fail — a separate judge agent decides bugs. Governed by 00-AUTHORING-STANDARD-exhaustive-testcases.md.

Test Case ID prefix: TC-AUTHZ-NNN (zero-padded, sequential, stable).

Render EVERY case — the existing cases AND all cases added by the Change prompt above — in the human-readable schema (test_case_id, title, description, category, feature_under_test, preconditions, test_data, test_steps, expected_result, actual_result, status, postconditions, severity_hint, references, tags), preserving the agent's existing machine fields under a `machine` sub-key of each case. Output stays ONE JSON object with a `test_cases[]` array.

### Exhaustive in-lane coverage checklist (AUTHZ — access control on protected resources)

**happy** — the permitted principal succeeds on each authorized operation:
- The permitted (owner) token succeeds on GET/PUT/DELETE of its own resource on each protected endpoint (2xx).
- An authorized read returns only the caller's own data with no forbidden/sensitive properties in the success body.
- A permitted write persists and reads back correctly, with server-managed fields untouched.
- Each protected endpoint × permitted method returns the expected 2xx for the correctly-scoped principal.

**negative** — each denied principal/role rejected per method (403 domain):
- Foreign-owner token and no-token each denied GET/PUT/DELETE on each protected endpoint (403/401), no resource data returned.
- A valid low-privilege token requesting another owner's object id (BOLA) denied 403 with no cross-owner leak.
- A normal-user token calling an admin-only function endpoint (BFLA) denied 403 with no privileged data, when an admin-function endpoint is supplied.
- A verb the role is not permitted to use (even on its own resource) denied 403/405 with no state change.

**boundary** — principals exactly at/just-below required privilege and id edges:
- A principal whose privilege is exactly at vs just-below the required level for a function/method.
- An enumerable/adjacent (guessable) resource id — first, last, and off-by-one from an owned id — denied 403/404 with no cross-owner leak.
- Token scope exactly covering vs just-short-of the target operation.
- The exact allowed-verb set vs one verb beyond it on an owned resource.

**edge** — normalization, override, and injection bypass vectors:
- HTTP method-override (`X-HTTP-Method-Override: DELETE`) tunneling a privileged verb — must not bypass authZ (403), no state change.
- Path case / trailing-slash / encoding variant of a privileged path — still authorized-checked (403), no bypass, when an admin-function endpoint is supplied.
- Mass-assignment of a privilege/role field in the body — read-back shows the field UNCHANGED (not persisted), when a forbidden writable field is supplied.
- Ownership-transfer field injection (`owner_id`/tenant) — ownership NOT reassigned on read-back, when an owner field is supplied.
- Read-only / server-managed field write (id/created_at/balance) — ignored, read-back unchanged.

**broad** — every role × method × protected endpoint, plus success-body exposure:
- The full matrix of {permitted, foreign-owner, no-token, low-privilege} × {GET, PUT, PATCH, DELETE} × each protected endpoint.
- The full BOLA/BFLA/BOPLA class enumeration (object-level, function-level, property-level) across supplied endpoints.
- Success-path excessive-property-exposure probe on each authorized read (no other-user PII / internal-only fields).
- Repeat each case the configured soak count; a varying result is a `flaky` observation for the judge (not a verdict here).
- Cite siblings for adjacent concerns: credential validity/expiry/revocation and JWT attacks → test-authentication-flows; third-party OAuth stages → verify-third-party-oauth-integration; network-origin allow/deny → test-ip-allowlist-enforcement.

Coverage is exhaustive in-lane but MECE across agents — no duplicate cases within this agent or shared with a sibling.
This is a pure test-case-generator reframe; its framework metric baseline is unachievable and pre-existing, so accept the tradeoff even if it lowers the metric.

## Tradeoff authorized
True
