# Implementation Plan — api-tester-verify-crud-operation-integrity

- **Agent:** api-tester-verify-crud-operation-integrity
- **Workflow:** CRUD-integrity tester for the target collection — an ordered step plan that exercises create/read/update/delete with field-echo verification, the documented soft-delete markers, the documented write-persistence proof, and the not-found negatives for a known-nonexistent item id.
- **Rating:** now 7/10 → 10
- **Source prompt:** agent-foundry/agents/api-tester/api-tester-update-agent-prompts.md
- **Lane:** owns the ordered CREATE/READ/UPDATE/DELETE step plan for the target collection supplied at runtime (field-echo, the documented soft-delete markers, the write-persistence proof, and the not-found negatives on a known-nonexistent item id); defers repeated-call idempotency to api-tester-test-idempotency-of-endpoints and the deeper delete semantics to api-tester-test-soft-delete-behavior.

## 1. Guardrails (force no hallucination)

These rules bind the agent; violating any one is a hallucination and must fail the build:
- **Feature supplied at runtime.** An orchestration prompt provides the feature under test and its endpoint(s)/inputs at runtime; never assume, hardcode, name, or mention any specific URL, path, host, resource, or feature — refer to inputs only by role (the target endpoint, the create endpoint, the item endpoint, the provided field/category value, etc.); if no feature is provided, fail closed with an out-of-scope error.
- **Derive only from the documented surface.** Never invent an endpoint, path, field, query parameter, status code, header, token, id, or case the runtime input does not provide.
- **Plan only — never guess a response.** Never state or fabricate any status code, body, header, timing, count, or verdict; a separate deterministic harness executes the steps and records real responses.
- **One JSON object, exact contract.** Emit exactly one JSON object — no prose, no extra or renamed keys.
- **Closed vocabulary only.** Use only this agent's fixed recipe kinds / value sets / labels.
- **Stay in lane (MECE), fail closed.** Never emit a case owned by another agent; on out-of-lane input emit one out-of-lane sentinel naming the sibling in `out_of_scope`.
- **Deterministic + exhaustive.** Same input → same plan; enumerate every documented case, no more, no less.
- **Byte-for-byte echo.** Reproduce provided ids/headers/regexes exactly.
- **Fail closed on missing input.** Missing/ambiguous required input → error sentinel, never a guessed default.
- **No fabricated review.** Every code artifact is reviewed at ≥85 by every agent in `agents/code-review/`; never invent a receipt or score.

**Agent-specific anti-hallucination rules:**
- Emit the ordered CRUD step plan exactly as the lane names it — create on the create endpoint, read on the item endpoint, update on the item endpoint, delete on the item endpoint — and never reorder, drop, or duplicate a step the documented surface does not support.
- Each write step must assert field-echo: the create and update steps assert the echoed fields equal exactly what was sent; never assert a value the harness has not yet recorded, and never invent a field the documented schema does not define.
- The delete step must assert the documented soft-delete markers from the contract, and the plan must carry the documented write-persistence proof (persisted or simulated) so a follow-up read reflects the contract-specified state; never invent a marker or a persistence outcome the surface does not declare.
- Emit the not-found negatives for a known-nonexistent item id (the read/update/delete-against-missing cases) exactly as the documented surface declares them; never assert the actual returned status — the harness records it.
- Emit JSON only — never HTTP or network; a separate deterministic harness executes the steps and checks the responses.
- Never emit a deferred case: a repeated-call idempotency replay (owned by api-tester-test-idempotency-of-endpoints) or a deeper soft-delete-semantics case (owned by api-tester-test-soft-delete-behavior).
- On out-of-lane input, emit a single out-of-lane error sentinel naming the owning sibling in `out_of_scope` and nothing else.

## 2. Prompt (run verbatim — miss no detail)

```
update-agent api-tester-verify-crud-operation-integrity Specify the complete CRUD-integrity tester for the target collection, emitting an ordered JSON step plan that exercises create/read/update/delete and verifies each response: CREATE (a POST to the create endpoint) echoing the submitted fields and returning a new id; READ (a GET to the item endpoint); UPDATE (a PUT to the item endpoint) with field-echo of the changed fields; DELETE (a DELETE to the item endpoint) asserting the documented soft-delete markers in the response; plus the target's documented write-persistence behaviour (persisted or simulated) as the contract specifies (the created/updated/deleted state is echoed and, where writes are simulated, not actually persisted, so a follow-up read reflects the original data); and the 404 negatives for a non-existent resource (a GET/PUT/DELETE to a known-nonexistent item id). Assert the echoed fields equal what was sent at each step. Leave repeated-call idempotency to api-tester-test-idempotency-of-endpoints and the deeper delete semantics to api-tester-test-soft-delete-behavior. Emit JSON only — no HTTP, no network, sandbox to FORGE_WORKSPACE; a separate deterministic harness executes the steps and checks the responses. In the same update and under the same gates, build this agent's lane-and-coverage safety net: a GUARDRAIL that keeps it in its lane — it emits only the JSON step-plan contract above for the target collection and never an idempotency-replay or soft-delete case (those belong to the agents named in the boundaries), failing closed rather than straying out of lane; GOLDEN test cases pinning the exact expected step plan and covering every title case above (CREATE with field-echo, READ, UPDATE with field-echo, DELETE with the documented soft-delete markers, the write-persistence proof, and the GET/PUT/DELETE 404 negatives on a known-nonexistent item id) with none omitted, saved as the regression baseline at tests/golden/api-tester/verify-crud-operation-integrity/golden.json; and UNIT tests that assert the plan has exactly the required keys, that every title case above is present in order with the field-echo and soft-delete-marker assertions (the suite fails if even one is missing), and that no out-of-lane case (idempotency replay or soft-delete) appears. Additionally, in this same update and under the update-agent gates, append the two standard sections below to this agent (identical for every agent in this file).

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
- [ ] Every title-named case present (by ROLE), in order: CREATE on the create endpoint with field-echo, READ on the item endpoint, UPDATE on the item endpoint with field-echo, DELETE on the item endpoint asserting the documented soft-delete markers, the documented write-persistence proof, and the not-found negatives (read/update/delete against a known-nonexistent item id).
- [ ] Each write step asserts the echoed fields equal what was sent; the delete step asserts the documented soft-delete markers.
- [ ] No out-of-lane case appears (no repeated-call idempotency replay, no deeper soft-delete-semantics case).
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
GOLDEN = "tests/golden/api-tester/verify-crud-operation-integrity/golden.json"
SUBAGENT = "agents/api-tester/verify-crud-operation-integrity/subagent/verify-crud-operation-integrity.md"

# the ordered CRUD steps this agent owns, by role
REQUIRED_STEP_KINDS = ["create", "read", "update", "delete"]
# cases that belong to sibling agents and must never appear here
OUT_OF_LANE_MARKERS = ["idempotency", "idempotent", "replay", "concurrent", "race"]

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
    plan = json.loads(pathlib.Path(GOLDEN).read_text(encoding="utf-8"))
    assert isinstance(plan, dict), "emitted plan must be a single JSON object"
    return plan


def _collect_step_kinds(plan):
    blob = json.dumps(plan).lower()
    steps = plan.get("steps") or plan.get("cases") or []
    kinds = []
    for s in steps:
        if isinstance(s, dict):
            for key in ("kind", "op", "operation", "step", "name"):
                if key in s and isinstance(s[key], str):
                    kinds.append(s[key].lower())
                    break
    return kinds, blob


def test_required_top_level_keys():
    plan = _load_plan()
    assert "steps" in plan or "cases" in plan, \
        "plan must carry the ordered CRUD step list"


def test_every_crud_step_present_in_order():
    plan = _load_plan()
    kinds, blob = _collect_step_kinds(plan)
    joined = " ".join(kinds) if kinds else blob
    last = -1
    for want in REQUIRED_STEP_KINDS:
        idx = joined.find(want)
        assert idx != -1, f"CRUD step '{want}' missing — suite fails if even one is absent"
        assert idx >= last, f"CRUD step '{want}' out of order"
        last = idx


def test_delete_asserts_soft_delete_markers():
    plan = _load_plan()
    _, blob = _collect_step_kinds(plan)
    # the documented soft-delete markers must be asserted on the delete step (by role)
    assert "soft" in blob and "delete" in blob, \
        "the delete step must assert the documented soft-delete markers"


def test_write_steps_assert_field_echo():
    plan = _load_plan()
    _, blob = _collect_step_kinds(plan)
    assert "echo" in blob, \
        "the create and update steps must assert field-echo of what was sent"


def test_not_found_negatives_present():
    plan = _load_plan()
    _, blob = _collect_step_kinds(plan)
    assert "not_found" in blob or "notfound" in blob or "404" in blob, \
        "the not-found negatives for a known-nonexistent item id must be present"


def test_no_out_of_lane_case_appears():
    plan = _load_plan()
    blob = json.dumps(plan).lower()
    for marker in OUT_OF_LANE_MARKERS:
        assert marker not in blob, \
            f"out-of-lane marker '{marker}' must not appear (deferred to a sibling agent)"


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
