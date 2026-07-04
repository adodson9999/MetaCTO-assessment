# update-agent: api-tester-test-bulk-operation-endpoints

## Invocation
update-agent api-tester-test-bulk-operation-endpoints "<CHANGE PROMPT below>"

## Change prompt (verbatim, exhaustive)

Expand the lane one sentence: you own **bulk/batch operation semantics** — all-valid, mixed-partial-failure (RFC 4918 207 Multi-Status with per-item offending-field naming), all-invalid, empty, single-item, duplicate-within-batch, oversize-reject, transactional-atomic rollback vs best-effort, bulk-update, bulk-delete, and now **best-effort partial-success** (explicit non-atomic 207), **per-item result ordering/index-mapping**, and **DB delta count** on every case — proven by a pre/post collection count (DB read-back is the correct oracle for a batch delta the per-item HTTP body may misreport); you do NOT own single-resource CRUD (sibling `api-tester-verify-crud-operation-integrity`) or parallel/simultaneous batch races (sibling `api-tester-test-concurrent-request-handling`).

Keep the single-JSON-object output with the top-level `cases` array plus the existing `endpoint` and `item_template` blocks. Every case keeps EXACTLY `name`, `endpoint_role`, `method`, `recipe` (with `kind` + recipe fields), `primary`, `also_accept`, `steps` (string array), and the optional `conditional`, and additionally carries `expected_by_contract` (from `references/contract-oracle.md`) and, only when docs differ, `expected_by_docs`. The closed recipe `kind` vocabulary becomes: `all_valid_batch`, `mixed_batch`, `all_invalid_batch`, `empty_batch`, `single_item_batch`, `duplicate_pair`, `oversize_batch`, `atomic_batch_one_invalid`, `bulk_update_batch`, `bulk_delete_batch`, `best_effort_partial_batch`, `per_item_index_mapping`.

### Group A — explicit best-effort (non-atomic) partial success
- NEW case. `name: best_effort_partial`; `endpoint_role: bulk_endpoint`; `method: POST`; `conditional: "if_best_effort_mode_documented"`; `recipe`: `{ "kind": "best_effort_partial_batch", "invalid_index": "[k]" }`; `primary`: `{ "overall_class": "207", "valid_item_class": "2xx", "invalid_item_class": "400", "expected_db_delta": "valid_count" }`; `also_accept: ["200_envelope_per_item_status"]`; `steps`: ["assert or select the documented best-effort (non-atomic) mode","build a batch of valid items plus one invalid item [k]","record the pre-count","POST the batch to the bulk endpoint","assert the valid items each committed with 2xx and item [k] returned 400 (partial success, NOT wholesale rollback)","assert post-count minus pre-count equals the valid count (the valid writes persisted despite the failure)"]; `expected_by_contract`: `{ "status": 207, "invariants": ["best_effort_commits_valid_items", "failed_item_reported_per_item", "db_delta_equals_valid_count"] }`. This is the explicit counterpart to `atomicity_rollback` — the two modes must be tested as a matched pair so a best-effort endpoint wrongly rolling back everything (or an atomic endpoint wrongly committing partials) is caught.

### Group B — per-item result ordering / index mapping (RFC 4918 §13 per-response href/index)
- NEW case. `name: per_item_index_mapping`; `endpoint_role: bulk_endpoint`; `method: POST`; `recipe`: `{ "kind": "per_item_index_mapping", "defects": [{ "index": "[i]", "defect": "wrong_type" }] }`; `primary`: `{ "overall_class": "207", "result_order": "each_result_maps_to_its_request_index", "invalid_item_class": "400", "offending_field": "named_per_invalid_item", "expected_db_delta": "valid_count" }`; `also_accept: ["200_envelope_indexed_results"]`; `steps`: ["build a batch where exactly item [i] is a wrong-type defect and all others valid","record the pre-count","POST the batch to the bulk endpoint","assert the response returns one result per request item, each mapped to its original request index/position","assert the result at index [i] is the 400 (and no other index is), naming the offending field","assert post-count minus pre-count equals the valid count"]; `expected_by_contract`: `{ "status": 207, "invariants": ["per_item_results_map_to_request_indices", "error_lands_on_correct_index", "db_delta_equals_valid_count"] }`. Catches the bug where per-item statuses are returned but mis-aligned to the wrong items.

### Tighten existing cases (add expected_by_contract + explicit DB-delta read-back)
- `all_valid`: `expected_by_contract`: `{ "status": 207, "invariants": ["every_item_2xx", "db_delta_equals_batch_size"] }` (keep `also_accept: ["200_per_item_success_report","201"]`).
- `mixed_207`: `expected_by_contract`: `{ "status": 207, "invariants": ["overall_207_multi_status", "each_invalid_item_400_naming_offending_field", "valid_items_2xx", "db_delta_equals_valid_count"] }`.
- `all_invalid`: `expected_by_contract`: `{ "status": 400, "invariants": ["every_item_rejected_or_top_level_400", "db_delta_zero"] }`.
- `empty`: `expected_by_contract`: `{ "status": 400, "invariants": ["documented_empty_batch_behavior", "db_delta_zero"] }`.
- `single_item`: `expected_by_contract`: `{ "status": 201, "invariants": ["single_item_2xx", "db_delta_one"] }`.
- `duplicate_within_batch`: `expected_by_contract`: `{ "status": 207, "invariants": ["one_item_2xx_other_409", "net_delta_one"] }`.
- `oversize_reject`: `expected_by_contract`: `{ "status": 413, "invariants": ["over_max_batch_rejected_naming_limit", "db_delta_zero"] }` (keep `also_accept: ["400"]`).
- `atomicity_rollback`: `expected_by_contract`: `{ "status": "top_level_failure", "invariants": ["atomic_mode_rolls_back_entire_batch", "db_delta_zero"] }`.
- `bulk_update`: `expected_by_contract`: `{ "status": 207, "invariants": ["valid_items_updated", "invalid_items_per_item_error_and_unchanged", "only_valid_updates_applied"] }`.
- `bulk_delete`: `expected_by_contract`: `{ "status": 207, "invariants": ["existing_ids_deleted", "missing_ids_per_item_error", "db_delta_equals_count_deleted"] }`.

REMOVE (de-dup): none currently emitted are out of lane — the existing 10 cases stay. Do NOT add: any parallel/simultaneous batch submission or two-batch race (owner `api-tester-test-concurrent-request-handling`); single-resource create/read/update/delete lifecycle proof (owner `api-tester-verify-crud-operation-integrity`); per-item request-body field-type/format/length constraint enumeration (owner `validate-request-payloads` — here defects are only the coarse missing_required / wrong_type used to trigger partial-failure routing, not a validation matrix); idempotency-key on the batch submission itself (owner `api-tester-test-idempotency-of-endpoints`).

PRESERVE invariants: emit exactly ONE JSON object and nothing else; feature-agnostic role-only references (`[MAX]`, `[N]`, `[i]`, `[j]`, `[k]`, `[REQUIRED_FIELDS]` placeholders preserved byte-for-byte, never numeric substitution); every `expected_by_contract` from `references/contract-oracle.md` (207 for partial per RFC 4918; Validation row "never 5xx on well-formed request"; delta rows proven by pre/post count), never target docs; DB delta proven black-box by a pre-count/post-count of the collection (the sanctioned oracle for a batch delta the per-item body may misreport — oracle §4); no `also_accept` swallowing a standard code; no network/HTTP calls in the plan — a deterministic harness POSTs each batch and counts; conditional cases (`atomicity_rollback`, `best_effort_partial`, `bulk_update`, `bulk_delete`) emitted only when the documented surface supports them; fail-closed out-of-lane sentinel naming the sibling in `out_of_scope`; keep the Standard-compliance / code-review ≥85 / self-awareness clause verbatim.

New total case count: **10 → 12** (existing 10 + 2 new: best_effort_partial, per_item_index_mapping; best_effort_partial conditional on documented best-effort mode). All 10 existing cases gain explicit `expected_by_contract` with a DB-delta invariant.

## Research basis
- **RFC 4918 §11.1 / §13 (207 Multi-Status)** — a batch with mixed outcomes returns 207 with one status per member, each mapped to its target; grounds mixed_207, best_effort_partial, per_item_index_mapping, and the index-mapping invariant (a real bug is per-item statuses mis-aligned to items).
- **Atomic vs best-effort batch semantics** — a batch is either transactional (one invalid → whole rollback, delta 0) or best-effort (valid items commit, invalid reported, delta = valid_count). These are opposite contracts and must be tested as a matched pair (atomicity_rollback ↔ best_effort_partial) so the wrong mode is caught.
- **Batch size limits (413 Payload Too Large / 400)** — over-max batches rejected naming the limit (existing oversize_reject, tightened).
- **Duplicate-within-batch uniqueness** — a batch containing an internal duplicate pair must commit exactly one and 409 the other (existing, tightened to net-delta-one).
- **DB delta as oracle** — the authoritative check that the batch did exactly what its per-item body claims is a pre/post collection count; per-item HTTP bodies can lie about persistence, so every case asserts the delta (oracle §4 black-box degrade to observable signal — here the collection count is observable).
- **Contract-oracle** Create / Validation / Delete rows drive every `expected_by_contract`.

## Gap summary
Before: 10 cases — all_valid, mixed_207, all_invalid, empty, single_item, duplicate_within_batch, oversize_reject, atomicity_rollback, bulk_update, bulk_delete; DB delta present in `primary` but no explicit `expected_by_contract`, and no explicit best-effort-partial or per-item-index-mapping case.
After: 12 cases — adds explicit best-effort partial-success (matched pair to atomic rollback) and per-item index-mapping (per-item results aligned to request indices); all 10 prior cases now carry `expected_by_contract` with a DB-delta invariant.

## De-dup notes
Removed: none (all 10 originals in-lane). Routed to owners:
- Parallel/simultaneous batch submission, two concurrent batches racing on a shared unique key → `api-tester-test-concurrent-request-handling`.
- Single-resource CRUD lifecycle → `api-tester-verify-crud-operation-integrity`.
- Full per-item request-body constraint matrix (type/format/length/range/nested) → `validate-request-payloads` (here defects are only coarse missing_required/wrong_type to route partial failure).
- Idempotency-Key on the batch POST itself / batch replay dedupe → `api-tester-test-idempotency-of-endpoints`.
- 429 on batch rate limit → `test-rate-limit-enforcement`.
Boundary proposals: none — every new class is enumerated bulk semantics in §1 of the boundary map (207 Multi-Status, partial-failure atomicity vs best-effort, per-item error mapping, DB delta count). The bulk↔concurrency handoff (batch internals sequential-per-batch here; simultaneity to concurrency sibling) is preserved.

## ADDENDUM (v2 — exhaustive test-case + reporting standard)

When running update-agent for this agent, pass the Change prompt above AND this ADDENDUM together as a single change prompt.

This agent is a **pure, exhaustive test-case generator** in its lane. It makes **NO bug judgement, verdict, or pass/fail call**. For every case it authors the scenario and fills the *Expected Result* (the definition of correct behavior, sourced from `references/contract-oracle.md` and the given feature spec). It leaves `actual_result` = `"TO BE FILLED DURING EXECUTION"` and `status` = `Not Executed`. It emits **no** deviations, no findings, no verdict, no `is_bug`, no pass/fail counts — a **separate judging/executor agent** runs the cases and decides whether an Actual Result is a bug. This role is governed by `00-AUTHORING-STANDARD-exhaustive-testcases.md`.

**Test Case ID prefix: `TC-BULK-NNN`** (zero-padded, sequential, stable across runs).

**Render every case in the human-readable schema.** In addition to the existing machine fields (keep `name`, `endpoint_role`, `method`, `recipe`, `primary`, `also_accept`, `steps`, the optional `conditional`, `expected_by_contract`, `expected_by_docs` intact under a `machine` key on each case, plus the top-level `endpoint` and `item_template` blocks, and preserve the `[MAX]`/`[N]`/`[i]`/`[j]`/`[k]`/`[REQUIRED_FIELDS]` placeholders byte-for-byte), every test case MUST also carry these plain-language fields: `test_case_id`, `title`, `description`, `category` (`happy`|`negative`|`boundary`|`edge`|`broad`), `feature_under_test`, `preconditions`, `test_data`, `test_steps`, `expected_result`, `actual_result` (="TO BE FILLED DURING EXECUTION"), `status` (=`Not Executed`), `postconditions`, `severity_hint`, `references`, `tags`. Still output ONE JSON object with a `test_cases[]` array.

**Lane-specific exhaustive coverage checklist (bulk/batch lane):**

- *Happy path:* all-valid batch → every item 2xx with DB delta = batch size; single-item batch → 2xx with delta one; bulk-update applies only the valid updates; bulk-delete removes the existing ids with delta = count deleted.
- *Negative path:* all-invalid batch → top-level 400 (or every item rejected) with DB delta zero; oversize batch over `[MAX]` → 413 (also-accept 400) naming the limit with delta zero.
- *Boundary:* empty batch → documented empty-batch behavior, delta zero; single-item batch (delta one); a batch at exactly `[MAX]` vs one over `[MAX]`; duplicate-pair within the batch → one item 2xx and the other 409, net delta one.
- *Edge:* mixed batch → 207 Multi-Status with each invalid item 400 naming the offending field and valid items 2xx (delta = valid count); atomic mode → one invalid item rolls the entire batch back, delta zero; best-effort (non-atomic) mode → valid items commit and the failed item is reported per-item, delta = valid count (the matched pair to atomic rollback — a best-effort endpoint wrongly rolling everything back, or an atomic endpoint wrongly committing partials, is caught); per-item index-mapping — one wrong-type defect at index `[i]` must land the 400 on exactly that index (and no other), catching mis-aligned per-item statuses.
- *Broad / combinatorial:* each mode (all-valid, mixed-207, all-invalid, empty, single, duplicate, oversize, atomic-rollback, best-effort-partial, per-item-index-mapping, bulk-update, bulk-delete) × explicit DB pre/post count-delta invariant; conditional cases (`atomicity_rollback`, `best_effort_partial`, `bulk_update`, `bulk_delete`) emitted only when the documented surface supports them.

DB delta is proven black-box by a pre/post collection count (the sanctioned oracle for a batch delta the per-item HTTP body may misreport). Cite sibling owners for adjacent concerns: any parallel/simultaneous batch submission or two-batch race → `api-tester-test-concurrent-request-handling`; single-resource CRUD lifecycle → `api-tester-verify-crud-operation-integrity`; the full per-item request-body constraint matrix (type/format/length/range/nested) → `validate-request-payloads` (here defects are only coarse missing_required/wrong_type to route partial-failure); Idempotency-Key on the batch POST itself / batch replay dedupe → `api-tester-test-idempotency-of-endpoints`; 429 on batch rate limit → `test-rate-limit-enforcement`.

Coverage exhaustive in-lane, MECE across agents — no duplicate cases.
