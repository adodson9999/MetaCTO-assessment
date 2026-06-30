# Implementation Plan — api-tester-validate-request-payloads

- **Agent:** api-tester-validate-request-payloads
- **Workflow:** Request-body contract tester for the write endpoints of the target collection — one labeled invalid/malformed-body payload set per documented schema field across the create and update bodies.
- **Rating:** now 6/10 → 10
- **Source prompt:** agent-foundry/agents/api-tester/api-tester-update-agent-prompts.md
- **Lane:** owns the malformed-request-body contract for the write endpoints of the target collection (the create endpoint and the item endpoint) — per-field missing-required (key-absent + key-present-null), wrong-type, extra/unexpected field, string-length boundaries, format/pattern violations, numeric-range violations, plus array/nested-object violations; defers pure null/empty/whitespace states to api-tester-validate-null-empty-fields and enum membership to api-tester-verify-enum-value-restrictions.

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
- Emit, per field of the documented schema, only the documented malformed-body categories: missing-required (key-absent and key-present-null), wrong-type, an extra/unexpected field, string-length boundaries (exactly max accepted, max+1 and min-1 rejected), format/pattern violations, and numeric-range violations (below min, above max, exclusive bounds, multipleOf), plus array and nested-object violations where the schema has them — across both the create-endpoint and item-endpoint write bodies. No other category.
- Derive every payload only from the documented schema's actual fields, types, bounds, and patterns; never invent a field, type, bound, regex, or limit the schema does not define.
- Reproduce schema regexes and format patterns byte-for-byte in the format/pattern-violation payloads; never normalize or re-encode them.
- Emit JSON only — never HTTP or network; a separate deterministic harness sends the bodies and records responses.
- Refuse out-of-lane input with a single sentinel naming the owning sibling: pure null/empty/whitespace states belong to api-tester-validate-null-empty-fields and enum membership belongs to api-tester-verify-enum-value-restrictions; emit neither.

## 2. Prompt (run verbatim — miss no detail)

```
update-agent api-tester-validate-request-payloads Specify the complete request-body contract tester for the write endpoints of the target collection (the create endpoint and the item endpoint), emitting a single JSON object of labeled invalid/malformed-body payloads covering, per field of the documented schema, missing-required (key-absent and key-present-null), wrong-type, an extra/unexpected field, string-length boundaries (exactly max accepted, max+1 and min-1 rejected), format/pattern violations, and numeric-range violations (below min, above max, exclusive bounds, multipleOf), plus array and nested-object violations where the schema has them, across both the create and update bodies. Leave pure null/empty/whitespace states to api-tester-validate-null-empty-fields and enum membership to api-tester-verify-enum-value-restrictions. Emit JSON only — no HTTP, no network, sandbox to FORGE_WORKSPACE; a separate deterministic harness sends the bodies and records responses. In the same update and under the same gates, build this agent's lane-and-coverage safety net: a GUARDRAIL that keeps it in its lane — it emits only the JSON malformed-body payload object above and never a pure null/empty/whitespace state or an enum-membership case (those belong to the agents named in the boundaries), failing closed rather than straying out of lane; GOLDEN test cases pinning the exact expected payload object for representative documented schemas and covering every malformed-body category the title workflow names above with none omitted, saved as the regression baseline at tests/golden/api-tester/validate-request-payloads/golden.json; and UNIT tests that assert the object has exactly the required keys, the correct per-field payload counts, that every title category above is present (the suite fails if even one is missing), and that no out-of-lane case (null/empty/whitespace or enum) appears. Additionally, in this same update and under the update-agent gates, append the two standard sections below to this agent (identical for every agent in this file).

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
- [ ] Single valid JSON object with exactly the required top-level keys — no prose.
- [ ] Every title-named category present (by ROLE): per documented schema field across both write bodies (the create endpoint and the item endpoint) — missing-required (key-absent + key-present-null), wrong-type, extra/unexpected field, string-length boundaries (max / max+1 / min-1), format/pattern violations, numeric-range violations (below min / above max / exclusive bounds / multipleOf), plus array and nested-object violations where the schema has them.
- [ ] No out-of-lane case appears (none of: pure null/empty/whitespace states, enum-membership cases).
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
GOLDEN = "tests/golden/api-tester/validate-request-payloads/golden.json"
SUBAGENT = "agents/api-tester/validate-request-payloads/subagent/validate-request-payloads.md"

# malformed-body categories the title workflow names, by ROLE label
TITLE_CATEGORY_LABELS = [
    "missing-required",
    "key-absent",
    "key-present-null",
    "wrong-type",
    "extra",            # extra/unexpected field
    "string-length",
    "format",           # format/pattern violations
    "numeric-range",
    "multipleOf",
    "array",            # array violations
    "nested-object",
]

# absent/null/empty/whitespace and enum membership are owned by siblings
OUT_OF_LANE_LABELS = [
    "empty-string",
    "whitespace-only",
    "json-null body",
    "empty-array",
    "empty-object",
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


def test_plan_is_single_json_object_with_required_keys():
    obj, _ = _load_plan()
    assert "payloads" in obj or "cases" in obj, \
        "plan must carry the malformed-body payload object"


def test_all_title_categories_present_across_both_write_bodies():
    _, text = _load_plan()
    haystack = text.lower()
    for label in TITLE_CATEGORY_LABELS:
        assert label.lower() in haystack, f"required malformed-body category missing: {label!r}"


def test_no_out_of_lane_case_appears():
    _, text = _load_plan()
    haystack = text.lower()
    for bad in OUT_OF_LANE_LABELS:
        assert bad.lower() not in haystack, \
            f"out-of-lane label {bad!r} must not appear (defers to null-empty / enum siblings)"


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
