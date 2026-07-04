# Update Spec — validate-request-payloads

## User prompt
Expand this agent's lane to the exhaustive type/format/range/length/structure request-body-constraint bug universe for the create-body and update-body of the write surface — every JSON Schema / OpenAPI structural-validation defect except the three sibling-owned concerns (pure null/empty/absent states → api-tester-validate-null-empty-fields; enum membership → api-tester-verify-enum-value-restrictions; wrong media-type negotiation status 415 → api-tester-verify-content-type-negotiation) — while preserving every existing case and invariant.

Mirror this agent's OWN golden.json schema exactly: the single emitted JSON object keeps its top-level keys `agent`, `lane`, `schema_roles`, `payloads` (with a `create_body` and `update_body` block, each holding a `valid` example body and a `cases[]` array), `expected_class` (`valid`:`2xx`, `malformed`:`4xx`, `also_accept`:`["422"]`), `out_of_scope`, and `baseline`. Every case object stays self-describing and carries the SAME field set this golden already uses for its class — `field` (targeted by ROLE, e.g. "the provided field", never a hardcoded name beyond what the runtime schema supplies), `category`, the class-specific descriptor keys (`variant`, `expected_type`, `length`, `pattern`, and the new ones spelled out below), and the full `body` (the known-valid example with ONLY the one targeted mutation applied, every other field unchanged) — and additionally carries `expected_by_contract` drawn from `references/contract-oracle.md` (the Validation row: "Malformed/invalid body → 4xx (400/422) with a machine-readable error; NEVER 5xx on a well-formed request"), an optional `expected_by_docs` only when the target's documented expectation differs, and the standard success / state-change / leak-nothing-on-failure assertion set. Reproduce every runtime schema regex/format pattern byte-for-byte; never invent a field, type, bound, regex, or limit the schema does not define; derive every payload only from the documented schema; refer to inputs only by role.

ADD the following NEW cases, grouped by class, to BOTH the create_body and update_body `cases[]` wherever the mutated field exists in that body's schema:

STRING FORMAT / PATTERN class (new `category` `"format"` variants; each case adds `format` naming the runtime format and a `variant` label; body = valid body with the one string field set to a value that violates the runtime-declared format byte-for-byte):
- `variant`:`email-invalid` — for a field whose format is `email`, a value missing `@`/domain.
- `variant`:`uri-invalid` — for a field whose format is `uri`/`url`, a non-absolute or scheme-less value.
- `variant`:`uuid-invalid` — for a field whose format is `uuid`, a value that is not a canonical 8-4-4-4-12 hex UUID.
- `variant`:`date-time-invalid` — for a field whose format is `date-time`, a non-RFC-3339 timestamp.
- `variant`:`date-invalid` — for a field whose format is `date`, a non-`YYYY-MM-DD` value.
- `variant`:`ipv4-invalid` — for a field whose format is `ipv4`, an out-of-range/octet-count-wrong value.
- `variant`:`pattern-violation` — for a field carrying a raw regex `pattern`, a value failing the byte-for-byte pattern (this generalizes the existing single `format` case).

STRING LENGTH class (extend existing `category`:`string-length`; keep `variant`:`max-accepted`/`max-plus-1-rejected`/`min-minus-1-rejected` and their `length` key; ADD):
- `variant`:`min-accepted`, `length`:<min> — exactly min characters, expected accepted (boundary-inclusive proof).
- `variant`:`empty-vs-minlength` ONLY when the field has NO explicit null/empty ownership overlap — but DEFER the pure empty-string state to api-tester-validate-null-empty-fields; therefore emit this variant ONLY as a `min-minus-1` when min>1 (do not emit a standalone empty-string case).

NUMERIC RANGE / PRECISION class (extend existing `category`:`numeric-range`; keep `variant`:`below-min`/`above-max`/`exclusive-bound`/`multipleOf`; ADD):
- `variant`:`min-accepted` — exactly `minimum`, expected accepted.
- `variant`:`max-accepted` — exactly `maximum` (non-exclusive), expected accepted.
- `variant`:`exclusive-minimum-off-by-one` — value equal to `exclusiveMinimum`, expected rejected.
- `variant`:`integer-with-fraction` — for an `integer` field, a fractional number (e.g. `x.5`), expected rejected (integer-vs-number distinction).
- `variant`:`number-as-string` — a stringified number for a numeric field, expected rejected (type-juggling/coercion abuse).
- `variant`:`precision-overflow` — for a `number` with a documented scale, a value exceeding the documented decimal precision, expected rejected.
- `variant`:`numeric-overflow` — a value beyond 2^53 / documented int range, expected rejected.

ARRAY class (extend existing `category`:`array`; keep `variant`:`item-wrong-type`; ADD for array fields carrying the relevant constraint):
- `variant`:`min-items-minus-1` — fewer than `minItems` elements, expected rejected.
- `variant`:`max-items-plus-1` — more than `maxItems` elements, expected rejected.
- `variant`:`unique-items-duplicate` — a duplicate element where `uniqueItems:true`, expected rejected.
- `variant`:`non-array-scalar` — a scalar where an array is documented, expected rejected (wrong-type at container level).

NESTED-OBJECT class (extend existing `category`:`nested-object`; keep `variant`:`inner-required-key-absent`; ADD):
- `variant`:`inner-wrong-type` — a nested required sub-field replaced with a wrong-JSON-type value, expected rejected.
- `variant`:`inner-extra-field` — an undefined key added inside the nested object where the nested schema is closed, expected rejected.
- `variant`:`non-object-scalar` — a scalar where a nested object is documented, expected rejected.

EXTRA / UNKNOWN FIELD class (extend existing `category`:`extra`; ADD):
- `variant`:`additional-properties-rejected` — one added top-level key not in the schema, asserted rejected ONLY when the schema declares `additionalProperties:false`; when the schema is open, emit `expected_by_contract` as accepted-and-ignored and flag a `missing_capability`/`leak` deviation if the extra key is echoed back or persisted (read-back).

STRUCTURAL / PARSER class (NEW `category`:`structural` with a NEW recipe KIND `structural_body_mutation` added to the closed recipe vocabulary; each case carries `variant` and either a `body` or, where the mutation cannot be expressed as valid JSON, a `raw_body` string + `content_type` descriptor; ALL assert `4xx`, NEVER `5xx`):
- `variant`:`malformed-json` — `raw_body` a syntactically invalid JSON string (trailing comma / unterminated), expected `400` not `500`.
- `variant`:`duplicate-json-key` — `raw_body` a JSON object literal repeating one documented key with two different values, expected deterministic reject-or-first/last-wins with NO `5xx` and no silent last-wins bypass.
- `variant`:`wrong-content-type-body` — a well-formed body sent with a mismatched `content_type` descriptor (this agent emits the case; the harness handles the header). NOTE: if this collides with 415 negotiation ownership, DEFER to api-tester-verify-content-type-negotiation and REMOVE.
- `variant`:`deeply-nested-body` — a body nested to a large depth (parser-DoS probe), expected `400/413` within limits, NEVER `5xx`/hang.
- `variant`:`oversized-body` — a body exceeding a documented/typical size cap, expected `413/400`, NEVER `5xx`.
- `variant`:`redos-pattern-input` — ONLY when a runtime string field carries a catastrophic-backtracking-prone regex `pattern`, a crafted adversarial input for that exact pattern, asserting the response returns within a sane deadline and NEVER `5xx`/timeout (ReDoS guardrail); reproduce the pattern byte-for-byte.

REMOVE / DO NOT EMIT (route to sibling owner, cite in-case):
- The existing `missing-required` `variant`:`key-present-null` cases and ANY pure null/empty-string/whitespace-only/empty-array/empty-object/integer-zero/boolean-false/string-"null" state — these are SOLE-owned by api-tester-validate-null-empty-fields. Keep ONLY `missing-required` `variant`:`key-absent` here (structural required-key omission is a payload-shape constraint, not a null state); remove `key-present-null` and add a de-dup note naming the sibling. (If the foundry MECE gate assigns `key-absent` to the null agent too, defer both and keep only wrong-type/format/range/length/structure.)
- Any enum-membership probe (unknown/case-variant/homoglyph/whitespace-padded value in an enum-constrained field) → api-tester-verify-enum-value-restrictions.

PRESERVE invariants: emit exactly ONE JSON object, no prose/extra/renamed keys; feature-agnostic (roles/field-roles only, never a hardcoded URL/host/resource/field beyond runtime schema); `expected_by_contract` from the contract oracle including "malformed/invalid body → 4xx with machine-readable error, NEVER 5xx on a well-formed request"; every malformed case asserts a 4xx + a machine-readable error body and asserts NO state change on failure (leak-nothing); full success/state-change/leak assertions and black-box read-back; recipes drawn ONLY from the closed vocabulary (now including the new `structural_body_mutation` KIND); soak-repeat with flaky-flagging; fail closed with an `out_of_scope` sentinel naming the owning sibling on out-of-lane input; confine all file access to FORGE_WORKSPACE; retain the code-review ≥85 self-awareness clause.

New total case count: the two golden bodies currently carry 17 (create) + 15 (update) = 32 cases; after adding the ~7 format + ~2 length + ~7 numeric + ~4 array + ~3 nested + ~1 extra + ~7 structural NEW variants (emitted per applicable field/body) and REMOVING the 4 `key-present-null` cases (2 create + 2 update), the agent should emit on the order of 90–120 cases for a representative multi-field, multi-format two-body surface — the exact total is the deterministic enumeration over the runtime schema's actual fields, formats, bounds, and structures, not a fixed number.

## ADDENDUM
When running update-agent for this agent, pass the Change prompt above AND this ADDENDUM together as a single change prompt.

This agent is a **pure, exhaustive test-case generator** — it makes NO bug judgement. It authors each case and fills the *Expected Result* (the definition of correct type/format/range/length/structure validation, sourced from the contract oracle and the given schema). It leaves `actual_result` = `"TO BE FILLED DURING EXECUTION"` and sets `status` = `Not Executed`. It emits **no** deviations, verdicts, `is_bug` flags, or pass/fail counts — a **separate judging agent** executes the cases and decides whether an Actual Result is a bug. This addendum is governed by `00-AUTHORING-STANDARD-exhaustive-testcases.md`.

**Test Case ID prefix: `TC-PAYLOAD-NNN`** (zero-padded, sequential, stable across runs).

**Render every case in the human-readable schema.** In addition to the machine fields, each test case MUST carry these human-readable fields in plain language with maximum detail: `test_case_id`, `title`, `description`, `category` (`happy`|`negative`|`boundary`|`edge`|`broad`), `feature_under_test`, `preconditions`, `test_data`, `test_steps`, `expected_result`, `actual_result` (= `"TO BE FILLED DURING EXECUTION"`), `status` (= `Not Executed`), `postconditions`, `severity_hint`, `references`, `tags`. Preserve every existing machine field (the `create_body`/`update_body` structure, `field`, `category`, `variant`, `expected_type`, `length`, `pattern`, `format`, `body`/`raw_body`/`content_type`, `expected_class`, `also_accept`, `expected_by_contract`, the `structural_body_mutation` recipe KIND) as sub-fields under a `machine` key so the harness/judge still gets structured inputs while humans get the readable case. Emit ONE JSON object with a `test_cases[]` array.

**Lane-specific exhaustive coverage checklist** (type/format/range/length/structure body constraints only — cite the sibling owner for anything adjacent so nothing overlaps):
- *Happy path*: the known-valid create body and update body accepted (2xx) with read-back proof; boundary-inclusive proofs accepted — string at exactly minLength and maxLength, numeric at exactly `minimum` and `maximum`.
- *Negative path*: wrong-JSON-type per field; string format/pattern violations (email/uri/uuid/date-time/date/ipv4 and raw `pattern`); integer-with-fraction; number-as-string coercion; array item-wrong-type; nested inner-wrong-type; non-array-scalar and non-object-scalar container mismatches; each malformed case asserts 4xx + machine-readable error and NO state change (leak-nothing).
- *Boundary*: maxLength+1 and minLength−1 rejected; numeric below-min/above-max; `exclusiveMinimum`/`exclusiveMaximum` off-by-one; `multipleOf`; array `minItems`−1 / `maxItems`+1 / `uniqueItems` duplicate; numeric-overflow beyond 2^53 / documented int range; precision-overflow beyond documented scale.
- *Edge*: `additionalProperties:false` extra-field rejection (or accepted-and-ignored with echo/persist leak flag when open); nested inner-extra-field where the sub-schema is closed; required KEY-ABSENT (structural omission).
- *Broad / parser (SOLE OWNER of parser-DoS + ReDoS)*: malformed JSON → 400 not 500; duplicate JSON key → deterministic reject/first-or-last-wins, no `5xx`; deeply-nested body → 400/413 within limits, never `5xx`/hang; oversized body → 413/400, never `5xx`; ReDoS adversarial input against the schema's own catastrophic `pattern` → response within a sane deadline, never `5xx`/timeout; enumerate over every documented field × create/update body.
- Cite the owner for adjacencies: pure null/empty/absent-VALUE states (json-null, empty-string, whitespace-only, empty-array/object, integer-zero, boolean-false, string-"null", key-present-null) → **validate-null-empty-fields** (this lane keeps only structural key-ABSENT); enum membership → **verify-enum-value-restrictions**; wrong media-type / 415 negotiation → **verify-content-type-negotiation**.

Coverage is exhaustive in-lane and MECE across agents — no duplicate cases within this agent or against any sibling.
This is a pure test-case-generator reframe; its framework metric baseline is unachievable and pre-existing, so accept the tradeoff even if it lowers the metric.

## Tradeoff authorized
True
