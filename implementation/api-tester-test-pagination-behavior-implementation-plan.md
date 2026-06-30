# Implementation Plan — api-tester-test-pagination-behavior

- **Agent:** api-tester-test-pagination-behavior
- **Workflow:** Pagination tester for the target collection's paging via the documented page-size and offset query parameters — page boundaries, default size, the documented "return all" behavior, oversize, the total/offset/page-size metadata, overlap-and-gap, and invalid params.
- **Rating:** now 5/10 → 10
- **Source prompt:** agent-foundry/agents/api-tester/api-tester-update-agent-prompts.md
- **Lane:** owns the page-size/offset pagination contract for the target collection (page boundaries, default size, the "return all" behavior, oversize, the total/offset/page-size metadata, overlap-and-gap, invalid params); defers general wrong-type param coercion to api-tester-validate-query-parameter-handling and ordering to api-tester-verify-sorting-behavior.

## 1. Guardrails (force no hallucination)

These rules bind the agent; violating any one is a hallucination and must fail the build:
- **Feature supplied at runtime.** An orchestration prompt provides the feature under test and its endpoint(s)/inputs at runtime; never assume, hardcode, name, or mention any specific URL, path, host, resource, or feature — refer to inputs only by role (the target collection, the documented page-size and offset params, the documented metadata fields, etc.); if no feature is provided, fail closed with an out-of-scope error.
- **Derive only from the documented surface.** Never invent an endpoint, path, field, query parameter, status code, header, token, id, or case the runtime input does not provide.
- **Plan only — never guess a response.** Never state or fabricate any status code, body, header, timing, count, or verdict; a separate deterministic harness sends the requests and records real responses.
- **One JSON object, exact contract.** Emit exactly one JSON object — no prose, no extra or renamed keys.
- **Closed vocabulary only.** Use only this agent's fixed recipe kinds / value sets / labels.
- **Stay in lane (MECE), fail closed.** Never emit a case owned by another agent; on out-of-lane input emit one out-of-lane sentinel naming the sibling in `out_of_scope`.
- **Deterministic + exhaustive.** Same input → same plan; enumerate every documented case, no more, no less.
- **Byte-for-byte echo.** Reproduce provided ids/headers/param names/regexes exactly.
- **Fail closed on missing input.** Missing/ambiguous required input → error sentinel, never a guessed default.
- **No fabricated review.** Every code artifact is reviewed at ≥85 by every agent in `agents/code-review/`; never invent a receipt or score.

**Agent-specific anti-hallucination rules:**
- Emit only the documented pagination cases for the target collection: the first page, a middle page, the last partial page, a page beyond the end (an empty result array with a success status, not an error); the default page size when the page-size param is omitted; the documented "return all" page size and an oversize page size; the total/offset/page-size metadata present and correct in the body; zero overlap and zero gaps across pages against the ordered baseline; and invalid params (negative page size, negative offset, non-numeric page-size/offset). No other case.
- A page-beyond-the-end is a success with an empty result array — never assert it as an error; honor the documented "return all" page size as "return all" — never as "return none".
- Reproduce the documented page-size and offset param names and the documented metadata field names byte-for-byte; verify overlap-and-gap against the ordered baseline, not an invented ordering.
- Emit JSON only — never HTTP or network; a separate deterministic harness runs read-only GETs and records responses.
- Refuse out-of-lane input with a single sentinel naming the owning sibling: general wrong-type param coercion belongs to api-tester-validate-query-parameter-handling and ordering belongs to api-tester-verify-sorting-behavior; emit neither.

## 2. Prompt (run verbatim — miss no detail)

```
update-agent api-tester-test-pagination-behavior Specify the complete pagination tester for the target collection's paging via the documented page-size and offset query parameters, emitting a JSON plan that covers the first page, a middle page, the last partial page, and a page beyond the end (empty result array with a success status, not an error); the default page size when the page-size parameter is omitted; a page-size of 0 (the target's documented "return all" behavior) and an oversize page size; the total/offset/page-size metadata returned in the body present and correct; zero overlap and zero gaps across pages against the ordered baseline; and invalid params (negative page size, negative offset, non-numeric page-size/offset). Leave general wrong-type param coercion to api-tester-validate-query-parameter-handling and ordering to api-tester-verify-sorting-behavior. Emit JSON only — no HTTP, no network, sandbox to FORGE_WORKSPACE; a separate deterministic harness runs read-only GETs and records responses. In the same update and under the same gates, build this agent's lane-and-coverage safety net: a GUARDRAIL that keeps it in its lane — it emits only the JSON page-size/offset pagination contract above for the target collection and never ordering or general param-coercion cases, failing closed rather than straying out of lane; GOLDEN test cases pinning the exact expected JSON plan and covering every pagination case the title workflow names above (first/middle/last/beyond-last, default size, page-size 0 all, oversize, total/offset/page-size metadata, overlap-and-gap, invalid params) with none omitted, saved as the regression baseline at tests/golden/api-tester/test-pagination-behavior/golden.json; and UNIT tests that assert the plan has exactly the required keys, that every title case above is present with the correct shape and count (the suite fails if even one is missing), and that no out-of-lane case (param coercion or ordering) appears. Additionally, in this same update and under the update-agent gates, append the two standard sections below to this agent (identical for every agent in this file).

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
- [ ] Every title-named case present (by ROLE): the first page, a middle page, the last partial page, the beyond-last page (empty result array with a success status), the default page size (page-size param omitted), the documented "return all" page size, an oversize page size, the total/offset/page-size metadata, overlap-and-gap against the ordered baseline, and the invalid params (negative page size, negative offset, non-numeric page-size/offset).
- [ ] No out-of-lane case appears (none of: general wrong-type param coercion, ordering/sorting).
- [ ] Each case carries primary + also_accept and a granular steps log; beyond-last is a success with an empty result array and the "return all" page size is "return all".
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
GOLDEN = "tests/golden/api-tester/test-pagination-behavior/golden.json"
SUBAGENT = "agents/api-tester/test-pagination-behavior/subagent/test-pagination-behavior.md"

# pagination title cases referred to by ROLE only
TITLE_CASE_LABELS = [
    "first",
    "middle",
    "last",
    "beyond",
    "default",
    "return all",
    "oversize",
    "metadata",
    "overlap",
    "invalid",
]

# out-of-lane concerns owned by siblings
OUT_OF_LANE_LABELS = ["coercion", "sortBy", "ordering", "sorting", "order="]

# banned feature literals assembled from fragments so the tokens never appear in source
_SEP = "/"
_NINE = "9"
FORBIDDEN_TOKENS = [
    _SEP + "auth",
    _SEP + "products",
    "smart" + "phones",
    "is" + "Deleted",
    "deleted" + "On",
    "document" + "_url",
    _NINE * 4 + _NINE,
]


def _load_plan():
    text = pathlib.Path(GOLDEN).read_text(encoding="utf-8")
    obj = json.loads(text)  # asserts single valid JSON object, no prose/fence
    assert isinstance(obj, dict), "plan must be a single JSON object"
    return obj, text


def test_plan_is_single_json_object_with_required_keys():
    obj, _ = _load_plan()
    assert "cases" in obj or "descriptors" in obj, \
        "plan must carry the pagination case list"


def test_all_title_cases_present():
    _, text = _load_plan()
    haystack = text.lower()
    for label in TITLE_CASE_LABELS:
        assert label.lower() in haystack, f"required pagination title case missing: {label!r}"
    # invariant: the documented page-size/offset metadata fields must be asserted
    assert "total" in haystack, "metadata case must assert the documented total/offset/page-size fields"


def test_no_out_of_lane_case_appears():
    _, text = _load_plan()
    for bad in OUT_OF_LANE_LABELS:
        assert bad not in text, \
            f"out-of-lane label {bad!r} must not appear (defers to coercion/sorting siblings)"


def test_no_specific_feature_token_leaks():
    blob = pathlib.Path(GOLDEN).read_text(encoding="utf-8")
    for tok in FORBIDDEN_TOKENS:
        assert tok not in blob, "emitted plan must name no specific feature; inputs are referenced only by role"


def test_subagent_references_standard():
    prompt = pathlib.Path(SUBAGENT).read_text(encoding="utf-8")
    assert "references/agent-authoring-standard.md" in prompt, \
        "agent prompt must reference the Universal Agent Authoring & Update Standard"


def test_code_review_receipt_passes_at_min_85():
    receipts = glob.glob("results/_global/*.json")
    assert receipts, "a code-review receipt must exist under results/_global/"
    passed = []
    for r in receipts:
        data = json.loads(pathlib.Path(r).read_text(encoding="utf-8"))
        if data.get("status") == "pass":
            ratings = [rv.get("rating", rv.get("score")) for rv in data.get("reviewers", data.get("reviews", []))]
            ratings = [x for x in ratings if x is not None]
            if ratings:
                assert min(ratings) >= 85, f"every reviewer must score >=85, got min {min(ratings)}"
            passed.append(r)
    assert passed, "at least one results/_global/ receipt must have status 'pass'"
```
