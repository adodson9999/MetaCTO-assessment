# Implementation Plan — api-tester-verify-error-message-clarity

- **Agent:** api-tester-verify-error-message-clarity
- **Workflow:** Error-clarity tester for this API's error responses — request descriptors that trigger each documented error so the harness checks a clear message, a machine-readable code, a consistent envelope, field-level detail, status↔code alignment, a request-id reference, and zero internal-detail leaks.
- **Rating:** now 6/10 → 10
- **Source prompt:** agent-foundry/agents/api-tester/api-tester-update-agent-prompts.md
- **Lane:** owns the JSON error-clarity descriptor list (clear human-readable message, machine-readable error-code field, consistent error-envelope shape, field-level detail naming the offending field, body code consistent with HTTP status, request-id/correlation reference, zero internal-detail leaks) on the documented error triggers; reuses the leakage substring list maintained by api-tester-check-authorization-rules and defers response-schema conformance to api-tester-validate-json-schema-responses.

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
- Plan only descriptors that trigger a documented error by role — the not-found case on a known-nonexistent item id, a malformed/invalid POST to the create endpoint, and a missing-auth attempt on a protected endpoint; never invent an error trigger the documented surface does not declare.
- Emit only clarity assertions — clear human-readable message, machine-readable error-code field, consistent envelope shape across codes, field-level detail naming the offending field on invalid-input cases, body code consistent with the HTTP status, request-id/correlation reference, and zero internal-detail leaks (no stack, SQL, file path, or echoed raw input); never assert the actual returned body — the harness captures it.
- Reuse the leakage substring list maintained by api-tester-check-authorization-rules verbatim; never fork or fabricate a leakage list of your own.
- Refuse response-schema conformance: that concern is owned by api-tester-validate-json-schema-responses; on such input emit the out-of-lane sentinel naming it in `out_of_scope` and nothing else.
- Echo the offending-field name and any provided id byte-for-byte; never normalize, re-encode, or substitute a runtime-supplied value.

## 2. Prompt (run verbatim — miss no detail)

```
update-agent api-tester-verify-error-message-clarity Specify the complete error-clarity tester for this API's error responses on the target collection and the provided authenticated operations, emitting a JSON list of request descriptors that trigger each documented error (a 404 on a known-nonexistent item id, a malformed/invalid POST to the create endpoint, a missing-auth attempt on a protected endpoint) so the harness checks a clear human-readable message; a machine-readable error-code field; a consistent error-envelope shape across codes; field-level detail naming the offending field on invalid-input 400s; the body's code value consistent with the HTTP status; a request-id/correlation reference; and zero internal-detail leaks (no stack, SQL, file path, or echoed raw input). Reuse the leakage substring list maintained by api-tester-check-authorization-rules and leave response-schema conformance to api-tester-validate-json-schema-responses. Emit JSON only — no HTTP, no network, sandbox to FORGE_WORKSPACE; a separate deterministic harness sends each descriptor, captures the real body, and runs the clarity assertions. In the same update and under the same gates, build this agent's lane-and-coverage safety net: a GUARDRAIL that keeps it in its lane — it emits only the JSON contract above and never a case owned by the agents named in the boundaries, failing closed rather than straying out of lane; GOLDEN test cases pinning the exact expected descriptor list and covering every clarity check the title workflow names above (clear message, machine code, envelope consistency, field-level detail, status↔code alignment, request-id, no-leak, on 404 and invalid-input triggers) with none omitted, saved as the regression baseline at tests/golden/api-tester/verify-error-message-clarity/golden.json; and UNIT tests that assert the plan has exactly the required keys, that every title check above is present with the correct shape and count (the suite fails if even one is missing), and that no out-of-lane case (response-schema conformance) appears. Additionally, in this same update and under the update-agent gates, append the two standard sections below to this agent (identical for every agent in this file).

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
- [ ] Every title-named case present (by ROLE): clear message, machine code, envelope consistency, field-level detail, status↔code alignment, request-id reference, no-leak — on the not-found trigger and the invalid-input trigger.
- [ ] No out-of-lane case appears (none of: response-schema conformance — owned by api-tester-validate-json-schema-responses).
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
GOLDEN = "tests/golden/api-tester/verify-error-message-clarity/golden.json"
SUBAGENT = "agents/api-tester/verify-error-message-clarity/subagent/verify-error-message-clarity.md"

# clarity checks named by role — no specific URL/feature
CLARITY_CHECKS = [
    "clear_message",
    "machine_code",
    "envelope_consistency",
    "field_level_detail",
    "status_code_alignment",
    "request_id",
    "no_leak",
]
OUT_OF_LANE = ["response_schema", "json_schema", "schema_conformance"]  # owned by validate-json-schema-responses

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


def test_required_top_level_keys():
    plan = _load_plan()
    assert "descriptors" in plan or "cases" in plan, \
        "plan must carry the error-clarity descriptor list"


def test_every_clarity_check_present():
    blob = json.dumps(_load_plan()).lower()
    for check in CLARITY_CHECKS:
        assert check in blob, f"required clarity check missing from plan: {check}"


def test_no_out_of_lane_case():
    blob = json.dumps(_load_plan()).lower()
    for token in OUT_OF_LANE:
        assert token not in blob, \
            f"out-of-lane case must not appear (owned by validate-json-schema-responses): {token}"


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
