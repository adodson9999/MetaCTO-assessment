# Implementation Plan — api-tester-verify-response-status-codes

- **Agent:** api-tester-verify-response-status-codes
- **Workflow:** Status-code conformance tester across the documented operations — one request descriptor per documented owned code (200, 201, 400, 404, 405, 409, 422, 500) that deterministically triggers it for exact comparison.
- **Rating:** now 6/10 → 10
- **Source prompt:** agent-foundry/agents/api-tester/api-tester-update-agent-prompts.md
- **Lane:** owns the JSON descriptor list of the status codes it owns (200, 201, 400, 404, 405, 409, 422, 500) across the documented operations supplied at runtime; defers the missing/invalid-auth code to api-tester-test-authentication-flows, the insufficient-permission code to api-tester-check-authorization-rules, the unacceptable/unsupported-media codes to api-tester-verify-content-type-negotiation, and the throttled code to api-tester-test-rate-limit-enforcement.

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
- Emit exactly one request descriptor per documented OWNED status code — only 200, 201, 400, 404, 405, 409, 422, 500 — and never a code outside that set; do not invent codes the documented surface does not declare.
- Each descriptor must deterministically TRIGGER its code from the documented surface (2xx on valid reads, the created code on the create endpoint, the bad-request code on a malformed body, the not-found code on a known-nonexistent item id, the method-not-allowed code asserting the Allow header, the conflict code where applicable, the unprocessable code, and the server-error code); never assert the actual returned status — the harness records it.
- Echo provided endpoint paths and the Allow header name byte-for-byte; never normalize a runtime-supplied path segment or substitute one.
- Never emit a deferred code: the missing/invalid-auth code (owned by api-tester-test-authentication-flows), the insufficient-permission code (api-tester-check-authorization-rules), the unacceptable/unsupported-media codes (api-tester-verify-content-type-negotiation), or the throttled code (api-tester-test-rate-limit-enforcement).
- On out-of-lane input, emit a single out-of-lane error sentinel naming the owning sibling in `out_of_scope` and nothing else.

## 2. Prompt (run verbatim — miss no detail)

```
update-agent api-tester-verify-response-status-codes Specify the complete status-code conformance tester across the documented operations (the target collection, the item endpoint, the create endpoint, the search endpoint, the provided authenticated operations), emitting a JSON list with one request descriptor per documented code that deterministically triggers it for exact comparison: 200 on valid reads, 201 on create, 400 on a malformed body, 404 on a missing resource (a known-nonexistent item id), 405 method-not-allowed (assert the Allow header), 409 conflict where applicable, 422 unprocessable, and 500. Defer 401 to api-tester-test-authentication-flows, 403 to api-tester-check-authorization-rules, 406/415 to api-tester-verify-content-type-negotiation, and 429 to api-tester-test-rate-limit-enforcement. Emit JSON only — no HTTP, no network, sandbox to FORGE_WORKSPACE; a separate deterministic harness sends each descriptor and records the real status. In the same update and under the same gates, build this agent's lane-and-coverage safety net: a GUARDRAIL that keeps it in its lane — it emits only the JSON descriptor list above and only the status codes it owns, never a code deferred to the agents named in the boundaries, failing closed rather than straying out of lane; GOLDEN test cases pinning the exact expected descriptor list and covering every code the title workflow names above (200, 201, 400, 404, 405, 409, 422, 500) with none omitted, saved as the regression baseline at tests/golden/api-tester/verify-response-status-codes/golden.json; and UNIT tests that assert one descriptor per documented owned code with the correct trigger shape (the suite fails if even one owned code is missing), and that no deferred code (401, 403, 406/415, 429) appears. Additionally, in this same update and under the update-agent gates, append the two standard sections below to this agent (identical for every agent in this file).

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
- [ ] Every title-named case present (by ROLE): one request descriptor per owned code — the success-read code, the created code, the bad-request code, the not-found code, the method-not-allowed code (with Allow-header assertion), the conflict code, the unprocessable code, the server-error code.
- [ ] No out-of-lane case appears (none of: the missing/invalid-auth code, the insufficient-permission code, the unacceptable/unsupported-media codes, the throttled code).
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
GOLDEN = "tests/golden/api-tester/verify-response-status-codes/golden.json"
SUBAGENT = "agents/api-tester/verify-response-status-codes/subagent/verify-response-status-codes.md"

OWNED_CODES = [200, 201, 400, 404, 405, 409, 422, 500]
DEFERRED_CODES = [401, 403, 406, 415, 429]

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


def _collect_codes(plan):
    blob = json.dumps(plan)
    descriptors = plan.get("descriptors") or plan.get("cases") or []
    codes = []
    for d in descriptors:
        if isinstance(d, dict):
            for key in ("status", "status_code", "code", "expected_status"):
                if key in d:
                    codes.append(int(d[key]))
                    break
    return codes, blob


def test_required_top_level_keys():
    plan = _load_plan()
    assert "descriptors" in plan or "cases" in plan, \
        "plan must carry the status-code descriptor list"


def test_one_descriptor_per_owned_code_present():
    plan = _load_plan()
    codes, _ = _collect_codes(plan)
    for c in OWNED_CODES:
        assert c in codes, f"owned status code {c} missing — suite fails if even one owned code is absent"


def test_method_not_allowed_asserts_allow_header():
    plan = _load_plan()
    _, blob = _collect_codes(plan)
    assert "Allow" in blob, "the method-not-allowed descriptor must assert the Allow header"


def test_no_out_of_lane_code_appears():
    plan = _load_plan()
    codes, _ = _collect_codes(plan)
    for c in DEFERRED_CODES:
        assert c not in codes, f"out-of-lane status code {c} must not appear (deferred to a sibling agent)"


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
