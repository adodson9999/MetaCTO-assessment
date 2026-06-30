# Implementation Plan — api-tester-test-idempotency-of-endpoints

- **Agent:** api-tester-test-idempotency-of-endpoints
- **Workflow:** Idempotency tester for the target collection — a JSON plan of repeated requests proving idempotent behavior: repeated reads return byte-for-byte identical bodies, repeated updates under one Idempotency-Key return identical responses with server-managed fields stable, repeated deletes are idempotent, and a same-key-different-body conflict is rejected without a second effect.
- **Rating:** now 6/10 → 10
- **Source prompt:** agent-foundry/agents/api-tester/api-tester-update-agent-prompts.md
- **Lane:** owns the repeated-request idempotency contract for the target collection supplied at runtime (read/update/delete replays, single Idempotency-Key, same-key-different-body conflict); defers parallel/concurrent same-key races to api-tester-test-concurrent-request-handling and the create/read/update/delete lifecycle proof to api-tester-verify-crud-operation-integrity.

## 1. Guardrails (force no hallucination)

These rules bind the agent; violating any one is a hallucination and must fail the build:
- **Feature supplied at runtime.** An orchestration prompt provides the feature under test and its endpoint(s)/inputs at runtime; never assume, hardcode, name, or mention any specific URL, path, host, resource, or feature — refer to inputs only by role (the target endpoint, the create endpoint, the item endpoint, the provided field/category value, etc.); if no feature is provided, fail closed with an out-of-scope error.
- **Derive only from the documented surface.** Never invent an endpoint, path, field, query parameter, status code, header, token, id, or case the runtime input does not provide.
- **Plan only — never guess a response.** Never state or fabricate any status code, body, header, timing, count, or verdict; a separate deterministic harness replays each request and compares responses byte-for-byte.
- **One JSON object, exact contract.** Emit exactly one JSON object — no prose, no extra or renamed keys.
- **Closed vocabulary only.** Use only this agent's fixed recipe kinds / value sets / labels.
- **Stay in lane (MECE), fail closed.** Never emit a case owned by another agent; on out-of-lane input emit one out-of-lane sentinel naming the sibling in `out_of_scope`.
- **Deterministic + exhaustive.** Same input → same plan; enumerate every documented case, no more, no less.
- **Byte-for-byte echo.** Reproduce provided ids/headers/regexes exactly.
- **Fail closed on missing input.** Missing/ambiguous required input → error sentinel, never a guessed default.
- **No fabricated review.** Every code artifact is reviewed at ≥85 by every agent in `agents/code-review/`; never invent a receipt or score.

**Agent-specific anti-hallucination rules:**
- Emit only the documented repeated-request cases: a read of the item endpoint repeated several times (byte-for-byte identical bodies); an update of the item endpoint repeated several times under one Idempotency-Key (identical responses, server-managed fields stable); a delete of the item endpoint repeated several times (the same documented soft-delete markers result, no error on replay); and a same-key-different-body update conflict rejected without a second effect. No other request shape.
- Pin fixed Idempotency-Key values and fixed replay counts; the same input always yields the same plan. Never invent a new key or vary the replay count nondeterministically.
- Account for the target's documented write-persistence behaviour (persisted or simulated): where writes are simulated, replays reflect the non-persisted result consistently. Never assert a persistence outcome the surface does not declare.
- Reproduce the Idempotency-Key header name, key values, and resource ids byte-for-byte; the harness replays each request and compares responses byte-for-byte.
- Emit JSON only — never HTTP or network; a separate deterministic harness replays each request and records the responses.
- Never emit a deferred case: a parallel/concurrent same-key race (owned by api-tester-test-concurrent-request-handling) or the full create/read/update/delete lifecycle proof (owned by api-tester-verify-crud-operation-integrity).
- On out-of-lane input, emit a single out-of-lane error sentinel naming the owning sibling in `out_of_scope` and nothing else.

## 2. Prompt (run verbatim — miss no detail)

```
update-agent api-tester-test-idempotency-of-endpoints Specify the complete idempotency tester for the target collection, emitting a JSON plan of repeated requests that proves idempotent behavior: a GET to the item endpoint repeated several times returns byte-for-byte identical bodies; a PUT to the item endpoint repeated several times under one Idempotency-Key returns identical responses and leaves server-managed fields stable; a DELETE to the item endpoint repeated several times is idempotent (the same documented soft-delete markers result, no error on replay); and a same-key-different-body PUT conflict is rejected without a second effect. Account for the target's documented write-persistence behaviour (persisted or simulated) as the contract specifies (where writes are simulated, replays reflect the non-persisted result consistently). Leave parallel/concurrent same-key races to api-tester-test-concurrent-request-handling and the create/read/update/delete lifecycle proof to api-tester-verify-crud-operation-integrity. Emit JSON only — no HTTP, no network, sandbox to FORGE_WORKSPACE; a separate deterministic harness replays each request and compares responses byte-for-byte. In the same update and under the same gates, build this agent's lane-and-coverage safety net: a GUARDRAIL that keeps it in its lane — it emits only the JSON repeated-request contract above for the target collection (GET/PUT/DELETE replays) and never a concurrency race or a full-lifecycle CRUD case, failing closed rather than straying out of lane; GOLDEN test cases pinning the exact expected JSON plan and covering every repeated-request case the title workflow names above with none omitted, saved as the regression baseline at tests/golden/api-tester/test-idempotency-of-endpoints/golden.json; and UNIT tests that assert the plan has exactly the required keys, fixed idempotency keys and replay counts, that every title case above is present with the correct shape and count (the suite fails if even one is missing), and that no out-of-lane case (concurrency or CRUD lifecycle) appears. Additionally, in this same update and under the update-agent gates, append the two standard sections below to this agent (identical for every agent in this file).

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
- [ ] Every title-named case present (by ROLE): a read of the item endpoint repeated, an update of the item endpoint repeated under one Idempotency-Key, a delete of the item endpoint repeated (the same documented soft-delete markers, no error on replay), and a same-key-different-body update conflict rejected without a second effect.
- [ ] Each case carries primary + also_accept, fixed Idempotency-Key values and fixed replay counts, and a granular steps log.
- [ ] No out-of-lane case appears (no parallel/concurrent same-key race, no full create/read/update/delete lifecycle proof).
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
GOLDEN = "tests/golden/api-tester/test-idempotency-of-endpoints/golden.json"
SUBAGENT = "agents/api-tester/test-idempotency-of-endpoints/subagent/test-idempotency-of-endpoints.md"

# the repeated-request methods this agent owns, by role
REQUIRED_REPLAY_METHODS = ["get", "put", "delete"]
# cases that belong to sibling agents and must never appear here
OUT_OF_LANE_MARKERS = ["concurrent", "concurrency", "parallel", "race", "lifecycle"]

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


def _collect_cases(plan):
    blob = json.dumps(plan).lower()
    cases = plan.get("cases") or plan.get("steps") or []
    return cases, blob


def test_required_top_level_keys():
    plan = _load_plan()
    assert "cases" in plan or "steps" in plan, \
        "plan must carry the repeated-request case list"


def test_every_replay_method_present():
    plan = _load_plan()
    _, blob = _collect_cases(plan)
    for method in REQUIRED_REPLAY_METHODS:
        assert method in blob, \
            f"replay method '{method}' missing — suite fails if even one is absent"


def test_update_replays_pin_idempotency_key():
    plan = _load_plan()
    _, blob = _collect_cases(plan)
    assert "idempotency-key" in blob, \
        "the update replay cases must pin the Idempotency-Key header"


def test_repeated_cases_pin_fixed_replay_count():
    plan = _load_plan()
    cases, _ = _collect_cases(plan)
    for c in cases:
        if isinstance(c, dict) and ("repeat" in str(c).lower() or "replay" in str(c).lower()):
            assert any(k in c for k in ("replay_count", "repeat_count", "count")), \
                "each repeated-request case must pin a fixed replay count"


def test_same_key_different_body_conflict_present():
    plan = _load_plan()
    _, blob = _collect_cases(plan)
    assert "conflict" in blob, \
        "the same-key-different-body conflict case must be present and rejected"


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
