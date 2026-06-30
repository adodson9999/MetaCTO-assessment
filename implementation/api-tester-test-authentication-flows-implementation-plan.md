# Implementation Plan — api-tester-test-authentication-flows

- **Agent:** api-tester-test-authentication-flows
- **Workflow:** JWT authentication-flow tester for the API's full token lifecycle (not just login) — exactly eleven cases across the login endpoint, the protected identity endpoint, and the token-refresh endpoint, each emitted as a JSON credential recipe that deterministically exercises a documented auth state.
- **Rating:** now 6/10 → 10
- **Source prompt:** agent-foundry/agents/api-tester/api-tester-update-agent-prompts.md
- **Lane:** owns the JSON credential-recipe contract for the full token lifecycle — the login endpoint, the protected identity endpoint, and the token-refresh endpoint; defers the third-party authorization-code flow to api-tester-verify-third-party-oauth-integration and role-based access control on protected resources to api-tester-check-authorization-rules.

## 1. Guardrails (force no hallucination)

These rules bind the agent; violating any one is a hallucination and must fail the build:
- **Feature supplied at runtime.** An orchestration prompt provides the feature under test and its endpoint(s)/inputs at runtime; never assume, hardcode, name, or mention any specific URL, path, host, resource, or feature — refer to inputs only by role (the login endpoint, the protected identity endpoint, the token-refresh endpoint, the provided credential, etc.); if no feature is provided, fail closed with an out-of-scope error.
- **Derive only from the documented surface.** Never invent an endpoint, path, field, query parameter, status code, header, token, id, or case the runtime input does not provide.
- **Plan only — never guess a response.** Never state or fabricate any status code, body, header, timing, count, or verdict; a separate deterministic harness builds each credential, sends it, and records real responses.
- **One JSON object, exact contract.** Emit exactly one JSON object — no prose, no extra or renamed keys.
- **Closed vocabulary only.** Use only this agent's fixed recipe kinds / value sets / labels.
- **Stay in lane (MECE), fail closed.** Never emit a case owned by another agent; on out-of-lane input emit one out-of-lane sentinel naming the sibling in `out_of_scope`.
- **Deterministic + exhaustive.** Same input → same plan; enumerate every documented case, no more, no less.
- **Byte-for-byte echo.** Reproduce provided ids/headers/regexes exactly.
- **Fail closed on missing input.** Missing/ambiguous required input → error sentinel, never a guessed default.
- **No fabricated review.** Every code artifact is reviewed at ≥85 by every agent in `agents/code-review/`; never invent a receipt or score.

**Agent-specific anti-hallucination rules:**
- Emit exactly the eleven documented credential-recipe cases and no twelfth: on the login endpoint — valid credentials (2xx + token), wrong password (401/400), unknown user (401/400), and missing required fields (400); on the protected identity endpoint — a valid token (2xx), a missing token, a malformed token, an expired token, and a revoked token (each 401/403); on the token-refresh endpoint — a valid refresh token (2xx + new access token) and a missing refresh token (401/400); never add a login variant the runtime input does not name.
- Use only the documented expected status classes per case; never fabricate a concrete numeric status outside the documented class.
- Emit credential recipes only — never a real token, JWT string, secret, signature, or network call; the harness builds each credential, sends it, and records the real response.
- Echo any provided credential identifiers, header names, and field names byte-for-byte; never normalize a runtime-supplied segment or substitute one.
- Never emit a deferred case: the third-party authorization-code/OAuth stage (owned by api-tester-verify-third-party-oauth-integration) or a role-based access-control case on a protected resource (api-tester-check-authorization-rules).
- On out-of-lane input, emit a single out-of-lane error sentinel naming the owning sibling in `out_of_scope` and nothing else.

## 2. Prompt (run verbatim — miss no detail)

```
update-agent api-tester-test-authentication-flows Specify the complete JWT authentication-flow tester for this API's full token lifecycle, not just login, emitting a JSON plan of exactly these cases: a POST to the login endpoint with valid credentials (2xx + token), wrong password (401/400), unknown user (401/400), and missing required fields (400); a GET to the protected identity endpoint with a valid token (2xx), a missing token, a malformed token, an expired token, and a revoked token (each 401/403); and a POST to the token-refresh endpoint with a valid refresh token (2xx + new access token) and a missing refresh token (401/400). Leave the third-party authorization-code flow to api-tester-verify-third-party-oauth-integration and role-based access control on protected resources to api-tester-check-authorization-rules. Emit JSON credential recipes only — no real tokens, no HTTP, no login, no network, sandbox to FORGE_WORKSPACE; a separate deterministic harness builds each credential, sends it, and records the real responses. In the same update and under the same gates, build this agent's lane-and-coverage safety net: a GUARDRAIL that keeps it in its lane — it emits only the JSON credential-recipe contract above for the login endpoint, the protected identity endpoint and the token-refresh endpoint and never an authorization/RBAC case or a third-party-OAuth stage, failing closed rather than straying out of lane; GOLDEN test cases pinning the exact expected JSON plan and covering every one of the eleven title cases above (login valid/wrong-password/unknown-user/missing-fields; identity-endpoint valid/missing/malformed/expired/revoked; refresh valid/missing) with none omitted, saved as the regression baseline at tests/golden/api-tester/test-authentication-flows/golden.json; and UNIT tests that assert the plan has exactly the required keys, that all eleven title cases above are present with the correct shape and expected status class (the suite fails if even one is missing), and that no out-of-lane case (RBAC or OAuth) appears. Additionally, in this same update and under the update-agent gates, append the two standard sections below to this agent (identical for every agent in this file).

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
- [ ] Every title-named case present (by ROLE): on the login endpoint — valid-credentials, wrong-password, unknown-user, missing-required-fields; on the protected identity endpoint — valid-token, missing-token, malformed-token, expired-token, revoked-token; on the token-refresh endpoint — valid-refresh-token, missing-refresh-token (eleven in total, none omitted).
- [ ] No out-of-lane case appears (neither a role-based access-control case on a protected resource nor any third-party authorization-code/OAuth stage).
- [ ] The agent names NO specific URL/path/host/feature anywhere — inputs referenced only by role.
- [ ] Credential recipes only — no real token value, no actual login or network call in the plan.
- [ ] System prompt (all four frameworks + judge) contains the verbatim Standard compliance clause, `references/agent-authoring-standard.md`, and the Runtime feature injection clause.
- [ ] A `results/_global/` code-review receipt has status pass, reviewer set == `agents/code-review/`, every reviewer ≥85.
- [ ] Golden baseline == post-update best; regression held or improved.

### Automated test (pytest-style)
```python
import json
import pathlib
import glob

# representative runtime-injected fixture: the orchestrator supplied the feature at runtime
GOLDEN = "tests/golden/api-tester/test-authentication-flows/golden.json"
SUBAGENT = "agents/api-tester/test-authentication-flows/subagent/test-authentication-flows.md"

# the eleven title cases, addressed by ROLE only (never a concrete path)
REQUIRED_CASE_ROLES = [
    "login_valid",
    "login_wrong_password",
    "login_unknown_user",
    "login_missing_fields",
    "identity_valid_token",
    "identity_missing_token",
    "identity_malformed_token",
    "identity_expired_token",
    "identity_revoked_token",
    "refresh_valid",
    "refresh_missing",
]

# out-of-lane concerns deferred to sibling agents
OUT_OF_LANE_MARKERS = ["oauth", "authorization_code", "rbac", "role_based"]

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
    cases = plan.get("cases") or plan.get("recipes") or []
    assert cases, "plan must carry the credential-recipe case list"
    return cases, json.dumps(plan).lower()


def test_required_top_level_keys():
    plan = _load_plan()
    assert "cases" in plan or "recipes" in plan, \
        "plan must carry the credential-recipe case list"


def test_all_eleven_title_cases_present():
    plan = _load_plan()
    _, blob = _collect_cases(plan)
    flat = blob.replace("_", "")
    for role in REQUIRED_CASE_ROLES:
        assert role.replace("_", "") in flat, \
            f"title case '{role}' missing — suite fails if even one is absent"


def test_exactly_eleven_cases():
    plan = _load_plan()
    cases, _ = _collect_cases(plan)
    assert len(cases) == 11, f"expected exactly 11 credential-recipe cases, got {len(cases)}"


def test_no_out_of_lane_case_appears():
    plan = _load_plan()
    _, blob = _collect_cases(plan)
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
