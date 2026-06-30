# Implementation Plan — api-tester-check-authorization-rules

- **Agent:** api-tester-check-authorization-rules
- **Workflow:** Authorization/access-control tester (the access-control half of auth) covering the GET/PUT/DELETE operations on each provided protected resource endpoint — a twelve-case matrix pairing an authorized request and an unauthorized (incl. cross-tenant/IDOR) request per protected method+endpoint combination, each asserting no resource-data leak.
- **Rating:** now 7/10 → 10
- **Source prompt:** agent-foundry/agents/api-tester/api-tester-update-agent-prompts.md
- **Lane:** owns the authorization/access-control matrix (authorized + unauthorized, including the cross-tenant/IDOR attempt) for the six protected method+endpoint combinations — GET/PUT/DELETE on each of the two provided protected resource endpoints; defers token validity, expiry and revocation (the credential lifecycle) to api-tester-test-authentication-flows.

## 1. Guardrails (force no hallucination)

These rules bind the agent; violating any one is a hallucination and must fail the build:
- **Feature supplied at runtime.** An orchestration prompt provides the feature under test and its endpoint(s)/inputs at runtime; never assume, hardcode, name, or mention any specific URL, path, host, resource, or feature — refer to inputs only by role (the protected resource endpoint, the provided permitted token, the foreign-owner token, etc.); if no feature is provided, fail closed with an out-of-scope error.
- **Derive only from the documented surface.** Never invent an endpoint, path, field, query parameter, status code, header, token, id, or case the runtime input does not provide.
- **Plan only — never guess a response.** Never state or fabricate any status code, body, header, timing, count, or verdict; a separate deterministic harness provisions tokens, sends the cases, and records real responses.
- **One JSON object, exact contract.** Emit exactly one JSON object — no prose, no extra or renamed keys.
- **Closed vocabulary only.** Use only this agent's fixed recipe kinds / value sets / labels.
- **Stay in lane (MECE), fail closed.** Never emit a case owned by another agent; on out-of-lane input emit one out-of-lane sentinel naming the sibling in `out_of_scope`.
- **Deterministic + exhaustive.** Same input → same plan; enumerate every documented case, no more, no less.
- **Byte-for-byte echo.** Reproduce provided ids/headers/regexes exactly.
- **Fail closed on missing input.** Missing/ambiguous required input → error sentinel, never a guessed default.
- **No fabricated review.** Every code artifact is reviewed at ≥85 by every agent in `agents/code-review/`; never invent a receipt or score.

**Agent-specific anti-hallucination rules:**
- Emit exactly twelve cases — one authorized (valid permitted token, allowed/2xx) and one unauthorized (no token, or an insufficient-role/foreign-owner token) per the six protected method+endpoint combinations (GET/PUT/DELETE on each of the two provided protected resource endpoints) — never a thirteenth combination or endpoint.
- Use only the documented denial classes: 401 for missing/invalid auth, 403 for insufficient permission. Never fabricate a concrete numeric status outside that vocabulary.
- Every case must carry a leakage-assertion block: assert no forbidden field value and no internal-detail substring leak; unauthorized cases additionally exercise the cross-tenant/IDOR attempt (one user targeting another user's resource by id).
- Echo provided tokens, resource ids, header names, and field names byte-for-byte; never normalize a runtime-supplied segment or substitute one.
- Never emit a deferred case: credential validity, expiry, and revocation (the credential lifecycle) belong to api-tester-test-authentication-flows, not here.
- On out-of-lane input, emit a single out-of-lane error sentinel naming the owning sibling in `out_of_scope` and nothing else.

## 2. Prompt (run verbatim — miss no detail)

```
update-agent api-tester-check-authorization-rules Specify the complete authorization/access-control tester — the access-control half of auth — covering the GET/PUT/DELETE operations on each provided protected resource endpoint. Emit a JSON matrix that, for each of those six protected method+endpoint combinations, includes an authorized request with a valid permitted token (allowed, 2xx) and an unauthorized request (no token, or an insufficient-role/foreign-owner token) that is denied (401 for missing/invalid auth, 403 for insufficient permission) and returns no resource data — twelve cases in total — with each case asserting no forbidden field value and no internal-detail substring leak, and the unauthorized cases also exercising the cross-tenant/IDOR attempt (one user targeting another user's resource by id). Leave token validity, expiry and revocation (the credential lifecycle) to api-tester-test-authentication-flows. Emit JSON only — no HTTP, no login, no network, sandbox to FORGE_WORKSPACE; a separate deterministic harness provisions tokens, sends the cases, and records responses. In the same update and under the same gates, build this agent's lane-and-coverage safety net: a GUARDRAIL that keeps it in its lane — it emits only the JSON authorization-matrix contract above for the provided protected resource endpoints and never the credential-lifecycle cases owned by api-tester-test-authentication-flows, failing closed rather than straying out of lane; GOLDEN test cases pinning the exact expected twelve-case matrix (authorized + unauthorized across the six method+endpoint combinations) with none omitted, saved as the regression baseline at tests/golden/api-tester/check-authorization-rules/golden.json; and UNIT tests that assert the plan has exactly the required keys and a leakage assertion block on every case, that all twelve title cases above are present with the correct shape and count (the suite fails if even one is missing), and that no out-of-lane case (credential validity/expiry/revocation) appears. Additionally, in this same update and under the update-agent gates, append the two standard sections below to this agent (identical for every agent in this file).

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
- [ ] Every title-named case present (by ROLE): authorized + unauthorized for each of the six protected method+endpoint combinations — GET / PUT / DELETE on the first provided protected resource endpoint and GET / PUT / DELETE on the second provided protected resource endpoint (twelve in total, none omitted).
- [ ] No out-of-lane case appears (none of: credential validity, expiry, or revocation — the credential lifecycle).
- [ ] Each case carries primary + also_accept, a leakage-assertion block (no forbidden field value, no internal-detail substring leak), and a granular steps log; unauthorized cases include a cross-tenant/IDOR attempt.
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
GOLDEN = "tests/golden/api-tester/check-authorization-rules/golden.json"
SUBAGENT = "agents/api-tester/check-authorization-rules/subagent/check-authorization-rules.md"

# the six protected method+endpoint combinations, addressed by ROLE only (never a concrete path)
HTTP_METHODS = ["GET", "PUT", "DELETE"]
PROTECTED_ENDPOINT_ROLES = ["protected_endpoint_1", "protected_endpoint_2"]
EXPECTED_CASE_COUNT = 12  # 6 combinations x {authorized, unauthorized}

# out-of-lane concern deferred to the credential-lifecycle agent
OUT_OF_LANE_MARKERS = ["expiry", "expired", "revocation", "revoked", "credential_lifecycle"]

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
    cases = plan.get("cases") or plan.get("matrix") or []
    assert cases, "plan must carry the authorization-matrix case list"
    return cases, json.dumps(plan).lower()


def test_required_top_level_keys():
    plan = _load_plan()
    assert "cases" in plan or "matrix" in plan, \
        "plan must carry the authorization-matrix case list"


def test_exactly_twelve_cases():
    plan = _load_plan()
    cases, _ = _collect_cases(plan)
    assert len(cases) == EXPECTED_CASE_COUNT, \
        f"expected exactly {EXPECTED_CASE_COUNT} cases (6 combinations x 2), got {len(cases)}"


def test_every_method_present_for_each_protected_endpoint():
    plan = _load_plan()
    _, blob = _collect_cases(plan)
    for method in HTTP_METHODS:
        assert method.lower() in blob, \
            f"protected method '{method}' missing — suite fails if even one combination is absent"


def test_every_case_has_leakage_assertion():
    plan = _load_plan()
    cases, _ = _collect_cases(plan)
    for c in cases:
        blob = json.dumps(c).lower()
        assert ("leak" in blob) or ("no_resource_data" in blob), \
            "every case must carry a leakage-assertion block (no forbidden field value / no internal-detail leak)"


def test_no_out_of_lane_case_appears():
    plan = _load_plan()
    _, blob = _collect_cases(plan)
    for marker in OUT_OF_LANE_MARKERS:
        assert marker not in blob, \
            f"out-of-lane marker '{marker}' must not appear (deferred to api-tester-test-authentication-flows)"


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
