# update-agent: api-tester-verify-crud-operation-integrity

## Invocation
update-agent api-tester-verify-crud-operation-integrity "<CHANGE PROMPT below>"

## Change prompt (verbatim, exhaustive)

Expand the lane one sentence: you own the **hard-CRUD lifecycle-integrity contract for one resource** — the ordered create/read/update/**PATCH-partial**/delete sequence with byte-for-byte field-echo, list-membership proof, RFC 9110 method-semantics conformance (POST→201+Location, PUT full-replace, PATCH→only-named-fields, DELETE idempotent-shaped read-back-404), conditional-update preconditions (If-Match/ETag → 412 on stale, 428 when required), and the full negative lifecycle (update/delete-missing→404, duplicate-unique→409) — each proven **black-box by read-back**; you do NOT own repeated-key idempotency dedupe (sibling `api-tester-test-idempotency-of-endpoints`), soft-delete tombstone/restore semantics (sibling `api-tester-test-soft-delete-behavior`), or parallel races (sibling `api-tester-test-concurrent-request-handling`).

Keep the single-JSON-object output with the top-level `steps` array; every step keeps EXACTLY the existing keys `role`, `kind`, `endpoint_role`, `method`, `asserts`, `expected_class`, `also_accept`, and additionally carries `expected_by_contract` (read from `references/contract-oracle.md`) and, only when docs differ, `expected_by_docs`. Add each NEW step below. The closed `kind` vocabulary becomes: `create`, `read`, `update`, `patch`, `delete`, `write_persistence_proof`, `list_membership`, `conditional_update`, `precondition_required`, `duplicate_conflict`, `method_not_allowed`.

### Group A — Location + create read-back (RFC 9110 §9.3.3 / oracle "Create")
Tighten the existing `create` step: `asserts` add `location_header_present: true` and `location_resolves_to_created_resource: true` (a GET on the returned Location/id returns the resource). `expected_by_contract`: `{ "status": 201, "invariants": ["location_present", "readback_reflects_create", "field_echo_equals_submitted"] }`. `also_accept: []` (do NOT accept 200 for a create — hard-guardrail).

### Group B — PATCH partial-update, only-named-fields (RFC 5789)
- NEW step. `role: patch_partial`; `kind: patch`; `endpoint_role: item_endpoint`; `method: PATCH`; `asserts`: `{ "field_echo": "patched_named_fields_equal_submitted_patch_fields", "unnamed_fields_unchanged": "fields_not_in_patch_body_equal_prior_read_state" }`; `expected_class: 2xx`; `also_accept: []`; `expected_by_contract`: `{ "status": 200, "invariants": ["readback_reflects_patch", "only_named_fields_changed"] }`. Read-back: follow-up GET shows only the named fields changed and every other field byte-for-byte equal to the pre-PATCH read.
- NEW step. `role: patch_readback`; `kind: read`; `endpoint_role: item_endpoint`; `method: GET`; `asserts`: `{ "field_echo": "read_reflects_patch_named_fields_and_preserved_others" }`; `expected_class: 2xx`; `also_accept: []`; `expected_by_contract`: `{ "status": 200, "invariants": ["readback_reflects_patch"] }`.

### Group C — list-membership read-back (oracle "Documented capability" / List)
- NEW step. `role: list_contains_created`; `kind: list_membership`; `endpoint_role: collection_endpoint`; `method: GET`; `asserts`: `{ "created_id_in_list": true }`; `expected_class: 2xx`; `also_accept: []`; `expected_by_contract`: `{ "status": 200, "invariants": ["created_resource_appears_in_collection_listing"] }`. (Membership only; page-math, sort, filter belong to siblings.)
- NEW step. `role: list_excludes_deleted`; `kind: list_membership`; `endpoint_role: collection_endpoint`; `method: GET`; `asserts`: `{ "deleted_id_absent_from_list": true }`; `expected_class: 2xx`; `also_accept: []`; `expected_by_contract`: `{ "status": 200, "invariants": ["hard_deleted_resource_absent_from_collection_listing"] }`. (Hard-delete list-exclusion only; tombstone `includeDeleted` semantics are sibling soft-delete's.)

### Group D — conditional update / lost-update precondition (RFC 9110 §13, oracle "Update")
- NEW step. `role: conditional_update_match`; `kind: conditional_update`; `endpoint_role: item_endpoint`; `method: PUT`; `asserts`: `{ "if_match_current_etag_accepted": true, "readback_reflects_change": true }`; `expected_class: 2xx`; `also_accept: []`; `expected_by_contract`: `{ "status": 200, "invariants": ["if_match_on_current_etag_succeeds", "readback_reflects_update"] }`.
- NEW step. `role: conditional_update_stale`; `kind: conditional_update`; `endpoint_role: item_endpoint`; `method: PUT`; `asserts`: `{ "if_match_stale_etag_rejected": true, "no_state_change_on_reject": true }`; `expected_class: 412`; `also_accept: []`; `expected_by_contract`: `{ "status": 412, "invariants": ["stale_if_match_yields_412", "readback_shows_no_lost_update"] }`. Read-back: after the rejected stale write, GET shows the pre-write value unchanged. (Single sequential stale write — this is contract precondition semantics, NOT a parallel race; parallel two-writer lost-update stays with the concurrency sibling.)
- NEW step (conditional, only if the surface documents mandatory preconditions). `role: precondition_required`; `kind: precondition_required`; `endpoint_role: item_endpoint`; `method: PUT`; `asserts`: `{ "update_without_if_match_rejected": true }`; `expected_class: 428`; `also_accept: []`; `expected_by_contract`: `{ "status": 428, "invariants": ["unconditional_write_rejected_when_precondition_required"] }`.

### Group E — duplicate-unique conflict (oracle "Validation"/409)
- NEW step. `role: duplicate_unique_conflict`; `kind: duplicate_conflict`; `endpoint_role: create_endpoint`; `method: POST`; `asserts`: `{ "second_create_same_unique_key_rejected": true, "no_second_row_via_readback": true }`; `expected_class: 409`; `also_accept: []`; `expected_by_contract`: `{ "status": 409, "invariants": ["duplicate_unique_key_yields_409", "collection_count_unchanged_by_rejected_create"] }`. (Sequential duplicate — the *parallel* same-key create race is the concurrency sibling's.)

### Group F — method-not-allowed on the item/collection surface (RFC 9110 §15.5.6 / 405+Allow)
- NEW step. `role: unsupported_method`; `kind: method_not_allowed`; `endpoint_role: item_endpoint`; `method: PATCH`; `asserts`: `{ "allow_header_lists_supported_methods": true }`; `expected_class: 405`; `also_accept: []`; `expected_by_contract`: `{ "status": 405, "invariants": ["allow_header_enumerates_supported_methods"] }`. Emit ONLY when the documented surface declares the method unsupported; otherwise omit (do not fabricate an unsupported method). Generic residual 405 conformance elsewhere belongs to `verify-response-status-codes`; here it is scoped to the item/collection under CRUD test.

REMOVE (de-dup): none currently emitted are out of lane — the existing 8 steps stay. Do NOT add: repeated-call replay-dedupe (owner `api-tester-test-idempotency-of-endpoints`), soft-delete markers-as-primary/restore/double-delete/tombstone-visibility (owner `api-tester-test-soft-delete-behavior` — retain only the existing hard-delete `delete`+`write_persistence_proof` read-back-404 proof, which is CRUD-lane), any parallel/simultaneous write race including two-writer lost-update and parallel same-key create (owner `api-tester-test-concurrent-request-handling`).

PRESERVE invariants: emit exactly ONE JSON object and nothing else; feature-agnostic role-only references (never a URL/path/host/resource/feature name); every `expected_by_contract` read from `references/contract-oracle.md`, never target docs/observed behaviour; every effect proven BLACK-BOX by read-back (create→GET-present, delete→GET-404, update/patch→GET-reflects, stale-write→GET-unchanged); no `also_accept` that swallows a standard code (no 200-for-create); no network/HTTP calls in the plan — a deterministic harness executes; keep the fail-closed out-of-lane sentinel naming the owning sibling in `out_of_scope`; keep the Standard-compliance / code-review ≥85 / self-awareness clause verbatim.

New total step count: **8 → 18** (existing 8 + 10 new: patch_partial, patch_readback, list_contains_created, list_excludes_deleted, conditional_update_match, conditional_update_stale, precondition_required, duplicate_unique_conflict, unsupported_method — plus tightened create Location asserts).

## Research basis
- **RFC 9110 (HTTP Semantics)** §9.3 — POST create → 201 + Location; PUT full-replace idempotent; DELETE. §13/§8.8 conditional requests & ETag; §15.5.13 → 412; §15.6 method status. Grounds Groups A, D, F and the create/update/delete oracle rows.
- **RFC 5789 (PATCH)** — PATCH is partial and MUST apply only the described modifications; grounds Group B "only-named-fields-change / others preserved", a classic real bug (PATCH silently nulling unspecified fields, or behaving as full replace).
- **RFC 9110 §15.6.5 (405) + Allow header** — grounds Group F, scoped to the CRUD resource.
- **RFC 6585 §3 (428 Precondition Required) / RFC 9110 §13.1 (If-Match, 412)** — lost-update prevention via preconditions; grounds Group D (sequential precondition semantics, distinct from concurrency-lane parallel races). Confirmed: 428 = "must send a condition", 412 = "condition failed".
- **Contract-oracle rows** Create / Read / Update / Delete / List / Validation — every new step's `expected_by_contract` is a direct oracle read; read-back (create→GET, delete→404, update→GET-reflects) is the oracle's black-box rule §4.
- **OWASP API** — mass-assignment on create/PATCH is out-of-lane (authZ/BOPLA sibling); here we assert field-echo integrity only, not privilege.

## Gap summary
Before: 8 steps — create, read, PUT-update, delete, write_persistence_proof, and 3 not-found negatives (read/update/delete missing → 404). No PATCH, no Location assertion, no list-membership, no conditional/precondition update, no sequential duplicate-409, no 405/Allow.
After: 18 steps — adds RFC 5789 PATCH partial + read-back, list-membership (include-created / exclude-hard-deleted), conditional-update (If-Match match/stale-412/428-required), sequential duplicate-unique 409, and scoped 405+Allow; create tightened to assert Location + read-back-resolves.

## De-dup notes
Removed: none (all 8 originals are in-lane). Explicitly NOT claimed and routed to owners:
- Repeated-call replay dedupe / same-key-different-body → `api-tester-test-idempotency-of-endpoints`.
- Soft-delete tombstone visibility, restore, double-delete, update-on-deleted, unique-key reuse-after-delete, `includeDeleted` filter → `api-tester-test-soft-delete-behavior`.
- Parallel two-writer lost-update, parallel same-unique-key create race, concurrent create+delete, zero-5xx-under-load → `api-tester-test-concurrent-request-handling`.
- Generic residual 405/Allow conformance across non-CRUD endpoints → `verify-response-status-codes` (kept here only scoped to the resource under CRUD test).
- Mass-assignment / property-level authZ on create/PATCH → `check-authorization-rules` (BOPLA).
Boundary proposals: none — every new class fits the CRUD lane per §1 of the boundary map. The CRUD/idempotency/soft-delete/concurrency four-way handoff is respected: CRUD keeps *single-sequence lifecycle + sequential preconditions/duplicates*, hands *replay*, *tombstone*, and *parallel* to the three named siblings.

## ADDENDUM (v2 — exhaustive test-case + reporting standard)

When running update-agent for this agent, pass the Change prompt above AND this ADDENDUM together as a single change prompt.

This agent is a **pure, exhaustive test-case generator** in its lane. It makes **NO bug judgement, verdict, or pass/fail call**. For every case it authors the scenario and fills the *Expected Result* (the definition of correct behavior, sourced from `references/contract-oracle.md` and the given feature spec). It leaves `actual_result` = `"TO BE FILLED DURING EXECUTION"` and `status` = `Not Executed`. It emits **no** deviations, no findings, no verdict, no `is_bug`, no pass/fail counts — a **separate judging/executor agent** runs the cases and decides whether an Actual Result is a bug. This role is governed by `00-AUTHORING-STANDARD-exhaustive-testcases.md`.

**Test Case ID prefix: `TC-CRUD-NNN`** (zero-padded, sequential, stable across runs).

**Render every case in the human-readable schema.** In addition to the existing machine fields (keep `role`, `kind`, `endpoint_role`, `method`, `asserts`, `expected_class`, `also_accept`, `expected_by_contract`, `expected_by_docs` intact under a `machine` key on each case), every test case MUST also carry these plain-language fields: `test_case_id`, `title`, `description`, `category` (`happy`|`negative`|`boundary`|`edge`|`broad`), `feature_under_test`, `preconditions`, `test_data`, `test_steps`, `expected_result`, `actual_result` (="TO BE FILLED DURING EXECUTION"), `status` (=`Not Executed`), `postconditions`, `severity_hint`, `references`, `tags`. Still output ONE JSON object with a `test_cases[]` array.

**Lane-specific exhaustive coverage checklist (CRUD hard-lifecycle lane):**

- *Happy path:* create → 201 + Location that resolves; read-back reflects create with byte-for-byte field-echo; PUT full-replace succeeds and read-back reflects it; PATCH updates only the named fields; DELETE then read-back-404; created id appears in the collection listing.
- *Negative path:* read-missing → 404; update-missing → 404; delete-missing → 404; sequential duplicate-unique-key create → 409; method-not-allowed on the item/collection surface → 405 with an Allow header enumerating supported methods.
- *Boundary:* create/read/update/patch/delete against a just-created vs just-deleted id; hard-deleted id absent from the collection listing; collection count unchanged by a rejected duplicate create; exact-limit field values echoed on create/replace.
- *Edge:* PATCH that names only one field must leave every unnamed field byte-for-byte equal to the pre-PATCH read (no silent null / no accidental full-replace); If-Match on a stale ETag → 412 with read-back showing no lost update; 428 when a required precondition is omitted; read-back proof after every mutating step (create→GET-present, delete→GET-404, update/patch→GET-reflects, stale-write→GET-unchanged).
- *Broad / combinatorial:* every documented CRUD method × item-vs-collection endpoint × present-vs-missing-resource state; each field echoed on create, full-replace, and partial-patch.

Cite sibling owners for adjacent concerns: repeated-key replay dedupe → `api-tester-test-idempotency-of-endpoints`; soft-delete tombstone/restore/unique-key-reuse-after-delete/cascade → `api-tester-test-soft-delete-behavior` (this lane owns only the hard-delete read-back-404 proof); any parallel/simultaneous write race (two-writer lost-update, parallel same-key create, create+delete TOCTOU) → `api-tester-test-concurrent-request-handling`; mass-assignment/property-level authZ → `check-authorization-rules`.

Coverage exhaustive in-lane, MECE across agents — no duplicate cases.
