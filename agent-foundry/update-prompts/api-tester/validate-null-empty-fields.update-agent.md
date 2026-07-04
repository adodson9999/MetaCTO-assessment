# update-agent: api-tester-validate-null-empty-fields

## Invocation

```
update-agent api-tester-validate-null-empty-fields "<CHANGE PROMPT below>"
```

## Change prompt (verbatim, exhaustive)

Expand this agent's lane to the exhaustive, SOLE-owned null/empty/absent request-body-state universe for the write surface — every distinguishable "value-is-absent-or-empty" state per documented field plus the cross-field null combinations and the null-vs-missing semantic distinction — while preserving every existing state, key, and invariant, and continuing to defer wrong-type/format/range/length/structure to api-tester-validate-request-payloads and enum membership to api-tester-verify-enum-value-restrictions.

Mirror this agent's OWN golden.json schema exactly: the single emitted JSON object keeps EXACTLY its six top-level keys and no others — `required_state`, `optional_state`, `all_required_null`, `each_required_null`, `combo_required_null`, `string_null` — where `all_required_null` is one body object and the other five are arrays of labeled payload objects. Each `required_state`/`optional_state` object keeps the SAME shape this golden uses: `{"field": <field name by role, reproduced byte-for-byte from the runtime schema>, "state": <the exact state role label>, "body": <the known-valid example with only that one field set to that state's value, or its key removed for key-absent, every other field unchanged>}`. `each_required_null` objects keep `{"label", "field", "body"}`; `combo_required_null` objects keep `{"label", "fields":[…], "body"}`; `string_null` objects keep `{"label":"\"null\"", "field", "body"}`. Additionally carry, per object, `expected_by_contract` drawn from `references/contract-oracle.md` (Validation row) and the standard success / state-change / leak-nothing-on-failure assertions, WITHOUT adding or renaming any of the six top-level keys.

PRESERVE the existing eight-state fixed order and its exact role labels and values for EACH required field — `key-absent`, `json-null`, `empty-string`, `integer-zero`, `boolean-false`, `empty-array`, `empty-object`, `whitespace-only` — with `integer-zero` emitted as the literal `0` and `boolean-false` as the literal `false`, never coerced to null/empty; and for object/array-typed fields keep the extra `null sub-field` and `null first array element` states after the eight. Keep `optional_state` enumerating its applicable states per optional field, `all_required_null` (every required field null), `each_required_null` (one required field null at a time), `combo_required_null` (two-or-more required fields null), and `string_null` (the four-character string `"null"` per required string field, distinguished byte-for-byte from the JSON null token).

ADD the following NEW states/labels, each slotted into the EXISTING six keys (no new top-level key), applied per applicable field with the body = valid example mutated in that one field only:

Into `required_state` and `optional_state` per applicable field (extend the state vocabulary; add each as a `state` label in the fixed enumeration for fields to which it applies):
- `state`:`whitespace-tab-newline` — a string of only tab/newline/carriage-return characters (distinct from the space-only `whitespace-only`), for string fields.
- `state`:`whitespace-unicode` — a string of only non-ASCII unicode whitespace (e.g. U+00A0 no-break space, U+3000 ideographic space), for string fields — probes trim-then-validate gaps.
- `state`:`empty-array-with-null-element` — for array fields, a single-element array whose one element is the JSON null token (distinct from `empty-array` and from `null first array element` on a populated valid array).
- `state`:`empty-object-with-null-value` — for object fields, an object with one documented sub-key present and set to the JSON null token (distinct from `empty-object` and from `null sub-field` on a populated valid object).
- `state`:`nested-null-deep` — for object fields with a nested object sub-field, the deepest documented leaf set to the JSON null token (nested-null distinction beyond one level).
- `state`:`zero-length-vs-absent-echo` — a `key-absent` companion PAIR marker so the harness can compare absent-vs-null-vs-empty read-back semantics on the SAME field (null-vs-missing distinction): the case body is identical to `key-absent` but its label records `pair:json-null` so grading asserts absent and null are NOT silently collapsed by the target.

Into `combo_required_null` (extend beyond the existing two-field pairs):
- Add a full-combinatorial set of required-null combinations sized to the runtime required-field count: all adjacent pairs (already present), plus every three-field combination where ≥3 required fields exist, so the array covers "each required field null", "each pair null", and "each larger subset null" up to `all_required_null` — the exact set is the deterministic power-set-minus-singletons-and-full enumeration over the runtime required fields (singletons live in `each_required_null`, the full set lives in `all_required_null`).

Into `string_null` (extend the literal-string family per required string field; keep `"null"` and ADD analogous confusable-literal probes that are STILL pure string values, not JSON tokens):
- `label`:`"NULL"` — the uppercase four-character string.
- `label`:`"None"` — the Python-style none literal as a string.
- `label`:`"nil"` / `"undefined"` — other language null-literal spellings as strings.
- `label`:`whitespace-null` — the string `" null "` (padded), still a non-null string, to probe trim-then-null-coerce bugs.
(All remain pure string values distinguished byte-for-byte from the JSON null token; when no required field is string-typed, this family stays an empty array.)

REMOVE / DO NOT EMIT (route to sibling owner, cite in-case): nothing currently in this golden crosses a boundary — this agent is the SOLE owner of every absent/null/empty/whitespace/zero/false/empty-container/string-"null" state, and api-tester-validate-request-payloads explicitly defers all such states here. Continue to NOT emit any wrong-type-that-is-not-an-empty-state value (e.g. a number where a string is documented is a wrong-type case → api-tester-validate-request-payloads) EXCEPT where the value is itself one of this lane's canonical empty-states (`integer-zero`, `boolean-false`, `empty-array`, `empty-object` placed in a differently-typed field are DELIBERATELY this lane's states and stay here). Continue to NOT emit enum-membership probes → api-tester-verify-enum-value-restrictions.

PRESERVE invariants: emit exactly ONE JSON object with EXACTLY the six required keys and no others, no prose/extra/renamed keys; feature-agnostic (field names reproduced byte-for-byte from the runtime schema, never assumed/hardcoded); reproduce every runtime field name byte-for-byte; `expected_by_contract` from the contract oracle including "malformed/invalid body → 4xx with machine-readable error, NEVER 5xx on a well-formed request" (a required field set null/empty/absent that the contract requires present → 4xx; an optional field null/absent per the optional contract → accepted, proven by read-back); every rejection asserts a 4xx + machine-readable error and NO state change on failure (leak-nothing); every acceptance proven black-box by read-back (follow-up GET reflects the stored value / absence); recipes from the closed vocabulary; soak-repeat with flaky-flagging; fail closed with an `out_of_scope` sentinel naming the owning sibling on out-of-lane input; confine file access to FORGE_WORKSPACE; retain the code-review ≥85 self-awareness clause.

New total case count: the current golden emits 27 `required_state` + 12 `optional_state` + 1 `all_required_null` + 3 `each_required_null` + 3 `combo_required_null` + 1 `string_null` = 47 labeled states for its 3-required/2-optional fixture; after adding the new whitespace/nested/null-element/absent-vs-null-pair states per applicable field, the full combo power-set, and the extended string-literal family, the agent should emit on the order of 70–110 states for a representative 3–5-field write body — the exact total is the deterministic enumeration over the runtime schema's actual required/optional fields and their JSON types, not a fixed number.

## Research basis

- The null / empty-string / absent-key trichotomy is semantically distinct and must be handled distinctly, especially for PATCH partial-updates where explicit-null means "clear" and absent means "leave unchanged". (baeldung.com/jackson-field-absent-vs-null; calhoun.io null-vs-not-provided; conradakunga.com System.Text.Json null-vs-empty.)
- Validation rules legitimately differ for missing vs null vs empty depending on whether a field is required/optional/nullable; each state must be probed independently. (albertmoreno.dev JSON API null design; medium.com null-vs-empty-vs-unknown.)
- `integer-zero` and `boolean-false` are frequent false-empty bugs — falsy values wrongly coerced to null/absent by lenient frameworks; must be sent as literal `0`/`false` and verified to persist. (System.Text.Json null/empty handling.)
- Whitespace-only, tab/newline-only, and unicode-whitespace inputs expose trim-then-validate ordering bugs where a "non-empty" string collapses to empty after trimming. (JSON API null design; input-validation literature.)
- Null-vs-missing must not be silently collapsed on read-back — the absent-vs-null pair marker enforces the distinction black-box.

## Gap summary

Current golden covers: the eight states × each required field, object/array `null sub-field` + `null first array element`, optional-field states, `all_required_null`, `each_required_null`, one `combo` pair set, and the single `"null"` string family. MISSING: tab/newline-only and unicode-whitespace distinct from space-only; `empty-array-with-null-element` and `empty-object-with-null-value` distinct from the plain empty containers; deep (>1 level) nested null; the explicit absent-vs-null read-back PAIR that proves null and missing are not collapsed; the full combinatorial required-null power-set (only adjacent pairs today); and the extended pure-string null-literal family (`"NULL"`/`"None"`/`"nil"`/`"undefined"`/padded `" null "`). This update adds all of them within the six existing keys.

## De-dup notes

- Per the MECE boundary map §Request-body cluster and boundary map line 39, this agent is the SOLE owner of "per-field absent / json-null / empty-string / zero / false / empty-array / empty-object / whitespace-only; all/each/combo-required-null; string-'null'; nested & array-element nulls". api-tester-validate-request-payloads DEFERS every such state here (confirmed in that agent's own prompt and the coverage-manifest handoff).
- No cross-boundary case exists to remove. The only adjacency risk is a value that is BOTH an empty-state and a wrong-type (e.g. `[]` in a string field): the boundary map assigns the empty-state framing to THIS agent, so it stays here; a genuinely non-empty wrong-type value (e.g. `42` in a string field) is NOT emitted here — that is api-tester-validate-request-payloads's `wrong-type` case.
- Enum-constrained fields set to null/empty are emitted here ONLY as the pure null/empty STATE; the off-enum value probes (unknown/case-variant/homoglyph/whitespace-padded VALUE) belong to api-tester-verify-enum-value-restrictions.

## ADDENDUM (v2 — exhaustive test-case + reporting standard)

When running update-agent for this agent, pass the Change prompt above AND this ADDENDUM together as a single change prompt.

This agent is a **pure, exhaustive test-case generator** — it makes NO bug judgement. It authors each case and fills the *Expected Result* (the definition of correct null/empty/absent-state handling, sourced from the contract oracle and the given schema). It leaves `actual_result` = `"TO BE FILLED DURING EXECUTION"` and sets `status` = `Not Executed`. It emits **no** deviations, verdicts, `is_bug` flags, or pass/fail counts — a **separate judging agent** executes the cases and decides whether an Actual Result is a bug. This addendum is governed by `00-AUTHORING-STANDARD-exhaustive-testcases.md`.

**Test Case ID prefix: `TC-NULLEMPTY-NNN`** (zero-padded, sequential, stable across runs).

**Render every case in the human-readable schema.** In addition to the machine fields, each test case MUST carry these human-readable fields in plain language with maximum detail: `test_case_id`, `title`, `description`, `category` (`happy`|`negative`|`boundary`|`edge`|`broad`), `feature_under_test`, `preconditions`, `test_data`, `test_steps`, `expected_result`, `actual_result` (= `"TO BE FILLED DURING EXECUTION"`), `status` (= `Not Executed`), `postconditions`, `severity_hint`, `references`, `tags`. Preserve every existing machine field — the SIX top-level keys (`required_state`, `optional_state`, `all_required_null`, `each_required_null`, `combo_required_null`, `string_null`) and per-object `field`/`state`/`label`/`fields`/`body`/`expected_by_contract` — as sub-fields under a `machine` key so the harness/judge still gets structured inputs while humans get the readable case; do NOT add or rename any of the six machine keys. Emit ONE JSON object with a `test_cases[]` array.

**Lane-specific exhaustive coverage checklist** (null / empty / absent STATES only — cite the sibling owner for anything adjacent so nothing overlaps):
- *Happy path*: an OPTIONAL field set to json-null or absent per the optional contract → accepted, proven by read-back; `integer-zero` (literal `0`) and `boolean-false` (literal `false`) persist and are NOT coerced to null/empty.
- *Negative path*: a REQUIRED field set to key-absent / json-null / empty-string that the contract requires present → 4xx + machine-readable error, NO state change (leak-nothing).
- *Boundary*: `all_required_null` (every required field null); `each_required_null` (one at a time); the full combinatorial `combo_required_null` power-set (every pair, every ≥3 subset up to but excluding the full set and singletons).
- *Edge*: whitespace-only (space) vs `whitespace-tab-newline` vs `whitespace-unicode` (U+00A0 / U+3000) — trim-then-validate gaps; `empty-array-with-null-element` and `empty-object-with-null-value` distinct from the plain empty containers; `nested-null-deep` (deepest leaf null, >1 level); the absent-vs-null read-back PAIR proving null and missing are NOT silently collapsed.
- *Broad*: the fixed eight-state enumeration × every required field, plus per-type extras (`null sub-field`, `null first array element`); optional-field states per applicable field; the pure-string null-literal family — `"null"`, `"NULL"`, `"None"`, `"nil"`, `"undefined"`, padded `" null "` — each a byte-for-byte non-null string per required string field.
- Cite the owner for adjacencies: wrong-type/format/range/length/structure (a genuinely non-empty wrong value, e.g. `42` in a string field) → **validate-request-payloads**; enum-membership value probes → **verify-enum-value-restrictions** (this lane emits only the pure null/empty STATE of an enum field). Values that are BOTH an empty-state and off-type (`[]` in a string field) are deliberately this lane's empty-state framing and stay here.

Coverage is exhaustive in-lane and MECE across agents — no duplicate cases within this agent or against any sibling.
