# API Test Agent Quality Standards (Phase 2.5)

Apply this entire reference **only when the task is API testing** — i.e. the task
spec describes generating test payloads for an HTTP endpoint's request body. If the
task is not API testing, skip it. When it applies, every standard below is
mandatory: no agent instruction line is finalized until it satisfies the debate
gate AND every applicable standard here. (Unchanged from the prior in-SKILL.md
version; extracted to a reference so SKILL.md stays control-flow only.)

## Scope delineation — three non-overlapping pipeline positions

Never conflate these. Building one agent to do all three is a defect.

- **Structural payload agent (n299-class):** Generates 6 labeled output types —
  valid, inv_missing_required, inv_wrong_type, inv_extra_field, inv_all_null,
  inv_maxlength. Does NOT test boundary values or null/empty states.
- **Boundary value agent (n310-class):** Generates boundary point payloads only —
  numeric 9-point, boolean 2-point, string length 6-point, array size 4-point,
  plus all-minimum and all-maximum combination bodies. Does NOT test structural
  invalidity or null/empty states.
- **Null/empty state agent (n311-class):** Generates null and empty state payloads
  only — 7 states per required field, pairwise-null combinations,
  string-literal-null distinction, and optional-nullable checks. Does NOT test
  boundary values or structural invalidity.

## Standard 1 — Coverage is ALL required fields, not a sample

Every agent that generates payloads targeting schema fields must iterate every
required field. "For EACH field in REQUIRED_FIELDS" — never "for one field". If the
schema has 8 required fields, the output reflects 8 — not fewer.

## Standard 2 — Output is labeled arrays, not flat single bodies

No invalid category may be a bare single body. Every invalid category output is an
array of labeled objects, each carrying at minimum: the field name, the category
label, and the body. run.py iterates these arrays to execute each payload.

## Standard 3 — The 9 WRONG_TYPE_VALUES with exact values (structural agents only)

```
INT_VAL     = 42
FLOAT_VAL   = 3.14
BOOL_TRUE   = true
BOOL_FALSE  = false
STRING_VAL  = "wrong_type_string"
CHAR_VAL    = "x"
LIST_VAL    = [1, "a", true]
OBJECT_VAL  = {"key": "value"}
NULL_NONE   = null
```

**Type-match exclusion rule** — for a field of schema type T, skip any
WRONG_TYPE_VALUE whose JSON type matches T exactly:
- string → skip STRING_VAL and CHAR_VAL
- integer → skip INT_VAL
- number → skip FLOAT_VAL and INT_VAL
- boolean → skip BOOL_TRUE and BOOL_FALSE
- array → skip LIST_VAL
- object → skip OBJECT_VAL

Apply per field independently. Instructions must enumerate the exact exclusions,
not summarize them.

## Standard 4 — inv_missing_required: exactly TWO variants per field (structural only)

1. `key_absent` — key removed entirely.
2. `key_present_null` — key present, value JSON null.

Total = (count of REQUIRED_FIELDS) × 2. Never collapsed into one.

## Standard 5 — inv_extra_field: exactly 9 payloads (structural only)

One per WRONG_TYPE_VALUE category in fixed order (INT_VAL … NULL_NONE). All
documented fields present and unchanged; extra key named `extra_field`. No
type-match exclusion applies here — all 9 are always present.

## Standard 6 — inv_maxlength: ALL constrained string fields, always an array (structural only)

Identify every string field with a maxLength constraint. Always an array even with
one such field. If none, value is JSON null. Each element:
`{ "field": "<name>", "max_length": N, "value_length": N+1, "body": { ... } }`
with the body value the letter "a" repeated exactly N+1 times.

## Standard 7 — 7 null/empty states applied to ALL required fields (null/empty agents only)

```
1. KEY_ABSENT      — key removed
2. JSON_NULL       — value JSON null
3. EMPTY_STRING    — value ""
4. INTEGER_ZERO    — value 0
5. BOOLEAN_FALSE   — value false
6. EMPTY_ARRAY     — value []
7. EMPTY_OBJECT    — value {}
```

All 7 applied to every required field regardless of type; all expected HTTP 400.
Total inner state objects = N × 7. Instructions must name all 7 explicitly.

## Standard 8 — Boundary point formulas with exact computations (boundary agents only)

For numeric fields with minimum M and maximum N (M < N):

```
MIN_MINUS_1        = M − 1                          → 400
MIN                = M                              → 2xx
MIN_PLUS_1         = M + 1                          → 2xx
TEN_PCT_ABOVE_MIN  = floor(M + (N − M) × 0.10)     → 2xx
MIDPOINT           = floor((M + N) / 2)            → 2xx
TEN_PCT_BELOW_MAX  = floor(N − (N − M) × 0.10)     → 2xx
MAX_MINUS_1        = N − 1                          → 2xx
MAX                = N                              → 2xx
MAX_PLUS_1         = N + 1                          → 400
```

Only-min: MIN_MINUS_1, MIN, MIN_PLUS_1. Only-max: MAX_MINUS_1, MAX, MAX_PLUS_1.
String labels: UNDER_MIN_LENGTH, EMPTY, MIN_LENGTH, MID_LENGTH, MAX_LENGTH,
OVER_MAX_LENGTH (omit inapplicable). Array labels: UNDER_MIN_ITEMS, MIN_ITEMS,
MAX_ITEMS, OVER_MAX_ITEMS (omit inapplicable). State each formula by name.

## Standard 9 — Explicit pass and fail thresholds per output category

Each category states: rate formula (numerator ÷ denominator × 100), exact pass
threshold as a percentage, and exact fail condition as a specific event. "High
accuracy" is not acceptable. A metric stating pass but not fail (or vice versa) is
incomplete.

## Standard 10 — Agents produce payloads only; run.py executes them

No API testing agent sends HTTP requests. The agent produces the labeled JSON
payload structure; the paired run.py reads it, iterates each labeled array, sends
each body, compares the actual HTTP response class to the "expected" field, and
records to `results/runs/<run-id>/<agent-name>.json`. Any instruction that says
"send a request" violates this separation and must fail the debate gate.

## Golden coupling

These ten standards are the source of the **golden structural cases** for an
API-testing agent (`references/golden-tests.md`): the hard counts (N×7, 9, ×2, the
maxlength array, the boundary labels) become exact structural assertions.
