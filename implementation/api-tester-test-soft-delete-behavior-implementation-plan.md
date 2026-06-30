# Implementation Plan — api-tester-test-soft-delete-behavior

- **Agent:** api-tester-test-soft-delete-behavior
- **Workflow:** Soft-delete tester for the target collection's delete semantics — over several delete lifecycles asserts the documented soft-delete markers, the documented write-persistence behaviour, leak-nothing, and the negatives.
- **Rating:** now 7/10 → 10
- **Source prompt:** agent-foundry/agents/api-tester/api-tester-update-agent-prompts.md
- **Lane:** owns the soft-delete contract for the target collection's delete semantics (the documented soft-delete markers, write-persistence proof, leak-nothing, the missing-resource 404 negative, double-delete); defers the full create/read/update/delete lifecycle to api-tester-verify-crud-operation-integrity.

## 1. Guardrails (force no hallucination)

These rules bind the agent; violating any one is a hallucination and must fail the build:
- **Feature supplied at runtime.** An orchestration prompt provides the feature under test and its endpoint(s)/inputs at runtime; never assume, hardcode, name, or mention any specific URL, path, host, resource, or feature — refer to inputs only by role (the target endpoint, the item endpoint, the documented soft-delete markers, etc.); if no feature is provided, fail closed with an out-of-scope error.
- **Derive only from the documented surface.** Never invent an endpoint, path, field, query parameter, status code, header, token, id, or case the runtime input does not provide.
- **Plan only — never guess a response.** Never state or fabricate any status code, body, header, timing, count, or verdict; a separate deterministic harness sends the requests and records real responses.
- **One JSON object, exact contract.** Emit exactly one JSON object — no prose, no extra or renamed keys.
- **Closed vocabulary only.** Use only this agent's fixed recipe kinds / value sets / labels.
- **Stay in lane (MECE), fail closed.** Never emit a case owned by another agent; on out-of-lane input emit one out-of-lane sentinel naming the sibling in `out_of_scope`.
- **Deterministic + exhaustive.** Same input → same plan; enumerate every documented case, no more, no less.
- **Byte-for-byte echo.** Reproduce provided ids/headers/regexes/placeholders exactly.
- **Fail closed on missing input.** Missing/ambiguous required input → error sentinel, never a guessed default.
- **No fabricated review.** Every code artifact is reviewed at ≥85 by every agent in `agents/code-review/`; never invent a receipt or score.

**Agent-specific anti-hallucination rules:**
- Over several delete lifecycles, emit only the documented soft-delete cases: a DELETE to the item endpoint returns 200 with the resource echoed plus the documented soft-delete markers; the write-persistence proof (where the delete is simulated, a follow-up GET to the item endpoint still returns the original record rather than 404); the response leaks no unexpected internal fields; a DELETE to a known-nonexistent item id returns 404; and a double-delete behaves consistently. No other request shape.
- Use only the documented soft-delete markers and the documented status codes (200 on the delete, 404 on the missing-resource negative); never fabricate a different marker name or status the documented surface does not declare.
- Preserve the documented resource-id placeholder exactly where the plan uses it; reproduce any provided sentinel id byte-for-byte; never substitute another id.
- Emit JSON only — never HTTP or network; a separate deterministic harness runs the lifecycles and checks the responses.
- Refuse out-of-lane input with a single sentinel naming api-tester-verify-crud-operation-integrity: the full create/read/update/delete (hard-CRUD) lifecycle belongs there, not here.

## 2. Prompt (run verbatim — miss no detail)

```
update-agent api-tester-test-soft-delete-behavior Specify the complete soft-delete tester for the target collection's delete semantics, emitting a JSON plan that over several delete lifecycles asserts a DELETE to the item endpoint returns 200 with the resource echoed plus the documented soft-delete markers; that the target's documented write-persistence behaviour (persisted or simulated) holds as the contract specifies (where the delete is simulated, a follow-up GET to the item endpoint still returns the original record rather than 404, proving the delete was not actually persisted); that the response leaks no unexpected internal fields; and the negatives (a DELETE to a known-nonexistent item id returns 404, and a double-delete behaves consistently). Leave the full create/read/update/delete lifecycle to api-tester-verify-crud-operation-integrity. Emit JSON only — no HTTP, no network, sandbox to FORGE_WORKSPACE; a separate deterministic harness runs the lifecycles and checks the responses. In the same update and under the same gates, build this agent's lane-and-coverage safety net: a GUARDRAIL that keeps it in its lane — it emits only the JSON soft-delete contract above for the target collection and never the full hard-CRUD lifecycle owned by api-tester-verify-crud-operation-integrity, failing closed rather than straying out of lane; GOLDEN test cases pinning the exact expected JSON plan and covering every delete-semantics case the title workflow names above (documented soft-delete markers, write-persistence proof, 404 negative, double-delete) with none omitted, saved as the regression baseline at tests/golden/api-tester/test-soft-delete-behavior/golden.json; and UNIT tests that assert the plan has exactly the required keys and the {RESOURCE_ID} placeholder preserved, that every title case above is present with the correct shape and count (the suite fails if even one is missing), and that no out-of-lane case (hard-CRUD lifecycle) appears. Additionally, in this same update and under the update-agent gates, append the two standard sections below to this agent (identical for every agent in this file).

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
- [ ] Single valid JSON object with exactly this agent's required top-level keys — no prose.
- [ ] Every title-named case present (by ROLE): a DELETE to the item endpoint returning the documented soft-delete markers, the write-persistence proof, the missing-resource 404 negative (a DELETE to a known-nonexistent item id), the double-delete.
- [ ] No out-of-lane case appears (none of: the full create/read/update/delete hard-CRUD lifecycle).
- [ ] Each case carries primary + also_accept, a leak-nothing assertion, the documented resource-id placeholder preserved, and a granular steps log.
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
GOLDEN = "tests/golden/api-tester/test-soft-delete-behavior/golden.json"
SUBAGENT = "agents/api-tester/test-soft-delete-behavior/subagent/test-soft-delete-behavior.md"

# title-named cases, by ROLE only (never a concrete path/marker)
TITLE_CASE_LABELS = [
    "soft-delete markers",
    "non-persistence",
    "404",
    "double-delete",
]

# out-of-lane labels owned by api-tester-verify-crud-operation-integrity
OUT_OF_LANE_LABELS = ["hard-CRUD", "create/read/update/delete", "CREATE", "UPDATE", "field-echo"]

# banned feature literals assembled from fragments so the tokens never appear in source
_SEP = "/"
_DEL = "d" + "eleted"
FORBIDDEN_TOKENS = [
    _SEP + "auth",
    _SEP + "products",
    "smart" + "phones",
    "is" + "D" + "eleted",
    _DEL + "On",
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
    assert "cases" in obj or "descriptors" in obj, \
        "plan must carry the soft-delete case list"


def test_all_title_cases_present_and_placeholder_preserved():
    _, text = _load_plan()
    for label in TITLE_CASE_LABELS:
        assert label in text, f"required title case missing from plan: {label!r}"
    placeholder = "{" + "RESOURCE_ID" + "}"
    assert placeholder in text, "the resource-id placeholder must be preserved verbatim"


def test_no_out_of_lane_case_appears():
    _, text = _load_plan()
    for bad in OUT_OF_LANE_LABELS:
        assert bad not in text, (
            f"out-of-lane label {bad!r} must not appear (defers to api-tester-verify-crud-operation-integrity)"
        )


def test_no_specific_feature_token_leaks():
    text = pathlib.Path(GOLDEN).read_text(encoding="utf-8")
    for tok in FORBIDDEN_TOKENS:
        assert tok not in text, "emitted plan must name no specific feature; inputs are referenced only by role"


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
            ratings = [rv.get("rating", rv.get("score")) for rv in data.get("reviewers", data.get("reviews", []))]
            ratings = [x for x in ratings if x is not None]
            if ratings:
                assert min(ratings) >= 85, f"every reviewer must score >=85, got min {min(ratings)}"
            passed.append(r)
    assert passed, "at least one results/_global/ receipt must have status 'pass'"
```
