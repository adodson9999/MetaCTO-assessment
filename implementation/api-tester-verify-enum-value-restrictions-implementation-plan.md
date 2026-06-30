# Implementation Plan — api-tester-verify-enum-value-restrictions

- **Agent:** api-tester-verify-enum-value-restrictions
- **Workflow:** Enum-restriction tester for the enum-constrained fields of the request body — a matrix of one body per valid enum value (accepted) plus, per enum field, the off-enum probes (unknown-string, empty-string, null, wrong-type, case-variant, numeric-enum, array/multi-select, whitespace-padded, unicode-look-alike), every invalid enum value expected to be rejected.
- **Rating:** now 7/10 → 10
- **Source prompt:** agent-foundry/agents/api-tester/api-tester-update-agent-prompts.md
- **Lane:** owns the JSON request-body enum matrix over the enum-constrained fields of the create endpoint (and the item endpoint) body supplied at runtime; defers enum-in-query-parameter probes to api-tester-validate-query-parameter-handling and api-tester-verify-sorting-behavior.

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
- Enumerate one body per valid enum value drawn from the documented enum set of each enum-constrained field; never invent an enum value or field the documented surface does not declare.
- Per enum field, emit exactly the closed off-enum probe set — unknown-string, empty-string, null (acceptance judged elsewhere by nullability), wrong-type, a case-variant of an uppercase-only value, numeric-enum (an out-of-set number and a stringified number), an array/multi-select case (a valid multi-select accepted, one off-enum member rejected), a whitespace-padded value, and a unicode-look-alike value — every invalid enum value expected to be rejected; never add, rename, or drop a probe.
- Operate only on the request body of the create endpoint (and the item endpoint); never emit an enum-in-query-parameter probe (owned by api-tester-validate-query-parameter-handling and api-tester-verify-sorting-behavior).
- Never assert the actual acceptance/rejection status — the separate harness sends each body and records responses.
- On out-of-lane input, emit a single out-of-lane error sentinel naming the owning sibling in `out_of_scope` and nothing else.

## 2. Prompt (run verbatim — miss no detail)

```
update-agent api-tester-verify-enum-value-restrictions Specify the complete enum-restriction tester for the enum-constrained fields of the create endpoint (and the item endpoint) body, emitting a JSON matrix covering one body per valid enum value (accepted, 2xx) and, per enum field, the off-enum probes unknown-string, empty-string, null (acceptance judged elsewhere by nullability), wrong-type, and a case-variant of an uppercase-only value, plus numeric-enum support (an out-of-set number and a stringified number), an array/multi-select case (a valid multi-select accepted, one off-enum member rejected), a whitespace-padded value, and a unicode-look-alike value — every invalid enum value expected to be rejected. Leave enum-in-query-parameter probes to api-tester-validate-query-parameter-handling and api-tester-verify-sorting-behavior. Emit JSON only — no HTTP, no network, sandbox to FORGE_WORKSPACE; a separate deterministic harness sends each body and records responses. In the same update and under the same gates, build this agent's lane-and-coverage safety net: a GUARDRAIL that keeps it in its lane — it emits only the JSON request-body enum contract above for the create endpoint and never query-parameter enum probes owned by the agents named in the boundaries, failing closed rather than straying out of lane; GOLDEN test cases pinning the exact expected matrix and covering every case the title workflow names above (valid-values, unknown-string, empty-string, null, wrong-type, case-variant, numeric-enum, array/multi-select, whitespace-padded, unicode-look-alike) with none omitted, saved as the regression baseline at tests/golden/api-tester/verify-enum-value-restrictions/golden.json; and UNIT tests that, per golden brief, assert the matrix has exactly the required keys and one body per valid enum value, that every title case above is present with the correct shape and count (the suite fails if even one is missing), and that no out-of-lane case (query-parameter enums) appears. Additionally, in this same update and under the update-agent gates, append the two standard sections below to this agent (identical for every agent in this file).

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
- [ ] Single valid JSON object with exactly the required top-level keys and one body per valid enum value — no prose.
- [ ] Every title-named case present (by ROLE): valid-values, unknown-string, empty-string, null, wrong-type, case-variant, numeric-enum, array/multi-select, whitespace-padded, unicode-look-alike.
- [ ] No out-of-lane case appears (none of: query-parameter enum probes — owned by api-tester-validate-query-parameter-handling and api-tester-verify-sorting-behavior).
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
GOLDEN = "tests/golden/api-tester/verify-enum-value-restrictions/golden.json"
SUBAGENT = "agents/api-tester/verify-enum-value-restrictions/subagent/verify-enum-value-restrictions.md"

# probe labels named by role — no specific URL/feature/value
TITLE_CASES = [
    "valid_values",
    "unknown_string",
    "empty_string",
    "null",
    "wrong_type",
    "case_variant",
    "numeric_enum",
    "array_multi_select",
    "whitespace_padded",
    "unicode_look_alike",
]
OUT_OF_LANE = ["query_param", "querystring", "sort_by"]  # owned by validate-query-parameter-handling / verify-sorting-behavior

# banned feature literals assembled from fragments so the tokens never appear in source
_SEP = "/"
FORBIDDEN_TOKENS = [
    _SEP + "auth",
    _SEP + "products",
    "smart" + "phones",
    "9" * 5,
]


def _load_plan():
    plan = json.loads(pathlib.Path(GOLDEN).read_text(encoding="utf-8"))
    assert isinstance(plan, dict), "emitted plan must be a single JSON object"
    return plan


def test_required_top_level_keys_and_valid_bodies():
    plan = _load_plan()
    assert "matrix" in plan or "cases" in plan, \
        "plan must carry the enum probe matrix"
    blob = json.dumps(plan).lower()
    assert "valid_values" in blob or "valid_value" in blob, \
        "matrix must include one body per valid enum value"


def test_every_title_case_present():
    blob = json.dumps(_load_plan()).lower()
    for case in TITLE_CASES:
        assert case in blob, f"required enum probe missing from plan: {case}"


def test_no_out_of_lane_case():
    blob = json.dumps(_load_plan()).lower()
    for token in OUT_OF_LANE:
        assert token not in blob, \
            f"out-of-lane query-parameter enum probe must not appear: {token}"


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
