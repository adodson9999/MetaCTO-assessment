# Implementation Plan — api-tester-validate-null-empty-fields

- **Agent:** api-tester-validate-null-empty-fields
- **Workflow:** Null/empty/absent tester for the target collection's write bodies — the sole owner of these states, emitting a JSON matrix of absent-or-empty states per documented schema field.
- **Rating:** now 8/10 → 10
- **Source prompt:** agent-foundry/agents/api-tester/api-tester-update-agent-prompts.md
- **Lane:** sole owner of the null/empty/absent states for the target collection's write bodies (key-absent, json-null, empty-string, integer-zero, boolean-false, empty-array, empty-object, whitespace-only, all-required-null, each-required-null, multi-null combos, the four-character string "null", null sub-field, null first array element); defers wrong-type values to api-tester-validate-request-payloads and enum membership to api-tester-verify-enum-value-restrictions. (api-tester-validate-request-payloads defers all absent/null/empty/whitespace states here — keep this matrix authoritative.)

## 1. Guardrails (force no hallucination)

These rules bind the agent; violating any one is a hallucination and must fail the build:
- **Feature supplied at runtime.** An orchestration prompt provides the feature under test and its endpoint(s)/inputs at runtime; never assume, hardcode, name, or mention any specific URL, path, host, resource, or feature — refer to inputs only by role (the target endpoint, the create endpoint, the item endpoint, the provided field/category value, etc.); if no feature is provided, fail closed with an out-of-scope error.
- **Derive only from the documented surface.** Never invent an endpoint, path, field, query parameter, status code, header, token, id, or case the runtime input does not provide.
- **Plan only — never guess a response.** Never state or fabricate any status code, body, header, timing, count, or verdict; a separate deterministic harness sends the requests and records real responses.
- **One JSON object, exact contract.** Emit exactly one JSON object — no prose, no extra or renamed keys.
- **Closed vocabulary only.** Use only this agent's fixed recipe kinds / value sets / labels.
- **Stay in lane (MECE), fail closed.** Never emit a case owned by another agent; on out-of-lane input emit one out-of-lane sentinel naming the sibling in `out_of_scope`.
- **Deterministic + exhaustive.** Same input → same plan; enumerate every documented case, no more, no less.
- **Byte-for-byte echo.** Reproduce provided ids/headers/regexes exactly.
- **Fail closed on missing input.** Missing/ambiguous required input → error sentinel, never a guessed default.
- **No fabricated review.** Every code artifact is reviewed at ≥85 by every agent in `agents/code-review/`; never invent a receipt or score.

**Agent-specific anti-hallucination rules:**
- Emit, per field of the documented schema, only the documented absent-or-empty states: key-absent, json-null, empty-string, integer-zero, boolean-false, empty-array, empty-object, and whitespace-only; plus an all-required-null body, an each-required-null array, a combo of multiple required nulls, the four-character string `"null"` in string fields, and (for object/array fields) a null in a required sub-field and a null first array element. No other state.
- The output matrix has exactly six required keys — assert that closed key set and the correct per-field state counts; never add, rename, or drop a key.
- Distinguish the literal four-character string `"null"` from json-null exactly; emit integer-zero and boolean-false as themselves, never coerced to null/empty; reproduce field names byte-for-byte.
- Emit JSON only — never HTTP or network; a separate deterministic harness sends each body and records responses.
- Refuse out-of-lane input with a single sentinel naming the owning sibling: wrong-type/format/range values belong to api-tester-validate-request-payloads and enum membership belongs to api-tester-verify-enum-value-restrictions; emit neither.

## 2. Prompt (run verbatim — miss no detail)

```
update-agent api-tester-validate-null-empty-fields Specify the complete null/empty/absent tester for the target collection's write bodies (the sole owner of these states), emitting a JSON matrix covering, per field of the documented schema, the absent-or-empty states key-absent, json-null, empty-string, integer-zero, boolean-false, empty-array, empty-object, and whitespace-only; an all-required-null body; an each-required-null array; a combo of multiple required nulls; the four-character string "null" in string fields; and, for object/array fields, a null in a required sub-field and a null first array element. api-tester-validate-request-payloads defers all absent/null/empty/whitespace states here, so keep this matrix authoritative; leave wrong-type values to api-tester-validate-request-payloads and enum membership to api-tester-verify-enum-value-restrictions. Emit JSON only — no HTTP, no network, sandbox to FORGE_WORKSPACE; a separate deterministic harness sends each body and records responses. In the same update and under the same gates, build this agent's lane-and-coverage safety net: a GUARDRAIL that keeps it in its lane — it emits only the JSON null/empty/absent matrix above and never type/format/range cases (api-tester-validate-request-payloads) or enum cases (api-tester-verify-enum-value-restrictions), failing closed rather than straying out of lane; GOLDEN test cases pinning the exact expected matrix and covering every state the title workflow names above with none omitted, saved as the regression baseline at tests/golden/api-tester/validate-null-empty-fields/golden.json; and UNIT tests that assert the matrix has exactly the six required keys and the correct per-field state counts, that every title state above is present (the suite fails if even one is missing), and that no out-of-lane case (type/format/range or enum) appears. Additionally, in this same update and under the update-agent gates, append the two standard sections below to this agent (identical for every agent in this file).

## Standard compliance & lane-ownership clause (inserted into every agent)
Insert the following clause VERBATIM into this agent's system prompt, directly beside the existing self-awareness clause, across all four frameworks (LangGraph, CrewAI, Claude Code subagent, Claude Agent SDK) and the judge:
=== BEGIN STANDARD COMPLIANCE CLAUSE (insert verbatim) ===
## Standard compliance & lane ownership

You operate under the foundry's Universal Agent Authoring & Update Standard at
`agent-foundry/references/agent-authoring-standard.md`, and you comply with its
Articles G1–G11. Emit only a single JSON object — a complete plan + execution + log +
report contract; perform no network calls, logins, or side effects; confine all file
access to FORGE_WORKSPACE (G1). You own a unique, mutually-exclusive slice of the
foundry's test surface — your declared lane — and you must NEVER emit a case whose
canonical identity is owned by another agent (G11). When input falls outside your lane,
emit a single out-of-lane error sentinel and nothing else, and name the sibling agent
that owns that concern in `out_of_scope` (G9, fail closed). Your case set is the
deterministic, exhaustive enumeration computed from the target's documented surface
(G8); every case is self-describing with a primary + `also_accept` expectation (G5),
full success / state-change / leak-nothing-on-failure assertions (G6), recipes drawn
only from your closed vocabulary (G7), and a maximally granular, fully-logged `steps`
array (G4). Your coverage is registered in
`agent-foundry/registry/coverage-manifest.json` and enforced by the foundry MECE gate;
all code you produce is reviewed by every agent in `agents/code-review/` and must score
≥85, no exception, looping until it does. See also `references/memory-everos.md`.
=== END STANDARD COMPLIANCE CLAUSE ===
Then add a per-agent unit test asserting the system prompt contains the string references/agent-authoring-standard.md (the MECE gate reference-check hard-halts any affected agent whose prompt omits it).

## Code review
Run the code-review gate on ALL code created by or related to this agent — every one of its four framework run.py runners (LangGraph, CrewAI, Claude Code subagent, Claude Agent SDK), the judge score.py, and any code the agent itself produces — requiring a score of ≥85 from EVERY agent discovered in agents/code-review/ (the full reviewer set, no exception, no hardcoded count), hard-halting on any reviewer below 85 and rewriting then re-running the full reviewer set in a loop with no cap until every reviewer is ≥85, then recording the pass receipt to results/_global/ and the run to references/memory-everos.md before the update may complete.

## Runtime feature injection
Insert a Runtime feature injection clause into this agent's system prompt across all four frameworks (LangGraph, CrewAI, Claude Code subagent, Claude Agent SDK) and the judge: the agent is feature-agnostic — an orchestration prompt supplies the feature and its endpoint(s)/inputs at runtime; the agent derives its entire plan only from those runtime-provided inputs and must NEVER assume, hardcode, name, or mention any specific URL, path, host, resource, or feature; it refers to inputs only by role (the target endpoint, the create endpoint, the item endpoint, the provided field/category value, etc.); and if no feature is provided it fails closed with an out-of-scope error requesting the feature.
```

## 3. Test (verify the job was done correctly)

### Verification checklist
- [ ] Single valid JSON object with exactly the six required top-level keys — no prose.
- [ ] Every title-named state present (by ROLE): per documented schema field — key-absent, json-null, empty-string, integer-zero, boolean-false, empty-array, empty-object, whitespace-only, all-required-null body, each-required-null array, multi-null combo, the four-character string "null" in string fields, null required sub-field, null first array element.
- [ ] No out-of-lane case appears (none of: wrong-type/format/range values, enum-membership cases).
- [ ] The agent names NO specific URL/path/host/feature anywhere — inputs referenced only by role.
- [ ] System prompt (all four frameworks + judge) contains the verbatim Standard compliance clause, `references/agent-authoring-standard.md`, and the Runtime feature injection clause.
- [ ] A `results/_global/` code-review receipt has status pass, reviewer set == `agents/code-review/`, every reviewer ≥85.
- [ ] Golden baseline == post-update best; regression held or improved.

### Automated test (pytest-style)
```python
import json
import pathlib
import glob

# representative runtime-injected fixture: the orchestrator supplied the feature at runtime
GOLDEN = "tests/golden/api-tester/validate-null-empty-fields/golden.json"
SUBAGENT = "agents/api-tester/validate-null-empty-fields/subagent/validate-null-empty-fields.md"

# the prompt pins EXACTLY six required keys for the matrix
REQUIRED_KEY_COUNT = 6

# null/empty/absent states the title workflow names, by ROLE label
TITLE_STATE_LABELS = [
    "key-absent",
    "json-null",
    "empty-string",
    "integer-zero",
    "boolean-false",
    "empty-array",
    "empty-object",
    "whitespace-only",
    "all-required-null",
    "each-required-null",
    "combo",            # combo of multiple required nulls
    '"null"',           # four-character string "null" in string fields
    "null sub-field",
    "null first array element",
]

# type/format/range and enum membership are owned by siblings
OUT_OF_LANE_LABELS = [
    "wrong-type",
    "format violation",
    "numeric-range",
    "multipleOf",
    "string-length boundary",
    "enum membership",
    "enum-value",
]

# banned feature literals assembled from fragments so the tokens never appear in source
_SEP = "/"
FORBIDDEN_TOKENS = [
    _SEP + "auth",
    _SEP + "products",
    "smart" + "phones",
    "is" + "Deleted",
    "deleted" + "On",
    "document" + "_url",
    "9" * 5,
]


def _load_plan():
    text = pathlib.Path(GOLDEN).read_text(encoding="utf-8")
    obj = json.loads(text)  # asserts single valid JSON object, no prose/fence
    assert isinstance(obj, dict), "plan must be a single JSON object"
    return obj, text


def test_matrix_has_exactly_six_required_keys():
    obj, _ = _load_plan()
    assert len(obj.keys()) == REQUIRED_KEY_COUNT, (
        f"matrix must have exactly {REQUIRED_KEY_COUNT} required keys; "
        f"found {len(obj.keys())}: {sorted(obj.keys())}"
    )


def test_all_title_states_present():
    _, text = _load_plan()
    haystack = text.lower()
    for label in TITLE_STATE_LABELS:
        assert label.lower() in haystack, f"required null/empty/absent state missing: {label!r}"


def test_no_out_of_lane_case_appears():
    _, text = _load_plan()
    haystack = text.lower()
    for bad in OUT_OF_LANE_LABELS:
        assert bad.lower() not in haystack, \
            f"out-of-lane label {bad!r} must not appear (defers to request-payloads / enum siblings)"


def test_no_specific_feature_token_leaks():
    blob = pathlib.Path(GOLDEN).read_text(encoding="utf-8")
    for tok in FORBIDDEN_TOKENS:
        assert tok not in blob, "emitted plan must name no specific feature; inputs are referenced only by role"


def test_subagent_references_standard():
    prompt = pathlib.Path(SUBAGENT).read_text(encoding="utf-8")
    assert "references/agent-authoring-standard.md" in prompt, \
        "agent prompt must reference the Universal Agent Authoring & Update Standard"


def test_code_review_receipt_passes():
    receipts = glob.glob("results/_global/*.json")
    assert receipts, "a code-review receipt must exist under results/_global/"
    passed = []
    for r in receipts:
        data = json.loads(pathlib.Path(r).read_text(encoding="utf-8"))
        if data.get("status") == "pass":
            ratings = [rv.get("rating", rv.get("score")) for rv in data.get("reviewers", [])]
            ratings = [x for x in ratings if x is not None]
            if ratings:
                assert min(ratings) >= 85, f"every reviewer must score >=85, got min {min(ratings)}"
            passed.append(r)
    assert passed, "at least one results/_global/ receipt must have status 'pass'"
```
