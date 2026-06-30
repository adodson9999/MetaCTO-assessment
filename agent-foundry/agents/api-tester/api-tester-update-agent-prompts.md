# api-tester — update-agent build-spec prompts

One prompt per agent (39 total). Each is the **specification you would hand the forge-agents skill**
— what the agent should fully test — but passed to **`update-agent`** so it runs the brownfield,
regression-protected flow (re-author + re-judge + gates, never drop the baseline).

Each prompt: (1) specifies the **full title workflow** with scope boundaries so no two agents test
the same thing, and (2) orders the three companion artifacts — a **guardrail** (stay in lane),
**golden test cases**, and **unit tests** that fail if a single title-named case is missing or any
out-of-lane case appears.

The agents are **feature-agnostic**: an orchestration prompt supplies the feature under test and its
endpoint(s)/inputs at runtime, and no agent names or hardcodes any specific URL, path, host, or
feature (see **Runtime feature injection** below). The prompts are grouped only for review convenience
(primary, case count); the grouping implies no fixed target. Format is the skill invocation:
`update-agent <agent_name> <spec…>`. Paste one block at a time.
Each heading shows the agent's **current coverage rating out of 10** — the baseline these prompts raise toward 10/10 (ratings from the ownership map in `api-tester-update-plan.md`).

---

# Standard compliance & lane-ownership clause (inserted into every agent)

Every `update-agent` prompt in this file additionally instructs the update to insert the clause
below **verbatim** into the agent's system prompt — across all four frameworks and the judge —
**directly beside the existing self-awareness clause**, and to add the per-agent reference-check
unit test. The clause binds each agent to the foundry's Universal Agent Authoring & Update Standard
(`agent-foundry/references/agent-authoring-standard.md`, Articles G1–G11). The MECE gate
reference-check hard-halts any affected agent whose system prompt does not cite that standard.

**Clause — paste verbatim (beside the self-awareness clause):**

```
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
```

**Per-agent unit test (alongside the G10 safety net):**

```python
import pathlib
def test_agent_references_standard():
    prompt = pathlib.Path(
        "agents/<group>/<name>/subagent/<name>.md"
    ).read_text(encoding="utf-8")
    assert "references/agent-authoring-standard.md" in prompt, \
        "agent prompt must reference the Universal Agent Authoring & Update Standard"
```

**Verify (run in your terminal — bash is unavailable in this session):**

```bash
# list any agent prompt missing the reference (empty output = all compliant)
grep -rL "references/agent-authoring-standard.md" agent-foundry/agents/*/*/subagent/*.md

# count agents that do reference it
grep -rl "references/agent-authoring-standard.md" agent-foundry/agents/*/*/subagent/*.md | wc -l
```

---

# Code review (applied to every agent)

Every `update-agent` prompt in this file also runs the **code-review gate** on all code created by or
related to the agent — its four framework `run.py` runners (LangGraph, CrewAI, Claude Code subagent,
Claude Agent SDK), the judge `score.py`, and any code the agent itself produces. Every such file must
score **≥85 from every agent discovered in `agents/code-review/`** (the full reviewer set, no exception,
no hardcoded count). Any reviewer below 85 hard-halts the update; the file is rewritten and the full
reviewer set re-runs in a loop with no cap until every reviewer is ≥85. The pass receipt is recorded to
`results/_global/` and the run to `references/memory-everos.md` before the update may complete (the
no-bypass completion contract). This mirrors the update-agent flow's Phase 2 and Phase 4 code-review
gates and the Phase 5 receipt contract. Each agent prompt below carries this as its own **Code review**
section, alongside the **Standard compliance & lane-ownership clause** section.

---

# Runtime feature injection (applies to every agent)

Every agent in this file is **feature-agnostic**. An orchestration prompt supplies the feature under
test and its endpoint(s)/inputs at runtime; the agent derives its entire plan only from those
runtime-provided inputs and must **never assume, hardcode, name, or mention any specific URL, path,
host, resource, or feature** — in its system prompt or its output. It refers to inputs only by role
(the target endpoint, the create endpoint, the item endpoint, the provided field/category value,
etc.). If the orchestrator provides no feature, the agent fails closed with an out-of-scope error
requesting the feature. Each agent prompt below carries this as its own **Runtime feature injection**
section, alongside the **Standard compliance & lane-ownership clause** and **Code review** sections.

---

# Priority workflows

## Authentication (JWT)

### test-authentication-flows — primary · 11 cases · now 6/10 → 10

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

### check-authorization-rules — 12 cases · now 7/10 → 10

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

## CRUD (products)

### verify-crud-operation-integrity — primary · 9 cases · now 7/10 → 10

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

### test-idempotency-of-endpoints — 33 cases · now 6/10 → 10

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

### test-soft-delete-behavior — 18 cases · now 7/10 → 10

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

## Search & filtering

### validate-search-and-filter-queries — primary · 7 cases · now 6/10 → 10

```
update-agent api-tester-validate-search-and-filter-queries Specify the complete search-and-filter tester for the target collection, emitting a JSON plan covering keyword search (a GET to the search endpoint with the provided query term returns only matching records), category filter (a GET to the category-filter endpoint with the provided category value returns only that category), the categories-list endpoint (a GET to the categories-list endpoint returns the known category set), field selection (select= returns only the requested fields), and ordering (sortBy + order return correctly ordered results). Assert every returned record matches the applied filter and the result set matches the known expected set. Leave generic query-parameter mechanics (type coercion, encoding, unknown-param policy) to api-tester-validate-query-parameter-handling and page-size and offset page math to api-tester-test-pagination-behavior. Emit JSON only — no HTTP, no network, sandbox to FORGE_WORKSPACE; a separate deterministic harness runs read-only GETs and records responses. In the same update and under the same gates, build this agent's lane-and-coverage safety net: a GUARDRAIL that keeps it in its lane — it emits only the JSON search/filter contract above for the search endpoint and the category-filter endpoint and never generic param-mechanics or pagination cases, failing closed rather than straying out of lane; GOLDEN test cases pinning the exact expected JSON plan and covering every one of the title cases above (keyword search, category filter, categories list, select fields, sortBy/order) with none omitted, saved as the regression baseline at tests/golden/api-tester/validate-search-and-filter-queries/golden.json; and UNIT tests that assert the plan has exactly the required keys, that every title case above is present with the correct shape and count (the suite fails if even one is missing), and that no out-of-lane case (generic param mechanics or page math) appears. Additionally, in this same update and under the update-agent gates, append the two standard sections below to this agent (identical for every agent in this file).

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

### test-pagination-behavior — 66 cases · now 5/10 → 10

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

### validate-query-parameter-handling — 48 cases · now 6/10 → 10

```
update-agent api-tester-validate-query-parameter-handling Specify the complete query-parameter mechanics tester across the target collection and the search endpoint, emitting a JSON plan that exercises generic parameter handling: a missing-required probe (e.g. the search endpoint with no query term); wrong-type coercion probes (non-numeric page-size/offset); valid single-parameter probes (the documented page-size and offset query parameters, select, the query term); an undocumented-parameter probe (ignored per policy); a URL-encoding probe (a query-term value with spaces and reserved characters percent-encoded); a default-application probe (a defaulted param omitted); a parameter-name-case probe; and a duplicate-same-key probe (first/last-wins). Leave the filtering/search semantics to api-tester-validate-search-and-filter-queries and the page-size and offset page math to api-tester-test-pagination-behavior. Emit JSON only — no HTTP, no network, sandbox to FORGE_WORKSPACE; a separate deterministic harness runs read-only GETs and records responses. In the same update and under the same gates, build this agent's lane-and-coverage safety net: a GUARDRAIL that keeps it in its lane — it emits only the JSON param-mechanics contract above for the target collection and the search endpoint and never filtering/search or page-math cases, failing closed rather than straying out of lane; GOLDEN test cases pinning the exact expected JSON plan and covering every param-mechanics case the title workflow names above (missing-required, wrong-type, valid single, undocumented-ignored, URL-encoding, default-application, name-case, duplicate-key) with none omitted, saved as the regression baseline at tests/golden/api-tester/validate-query-parameter-handling/golden.json; and UNIT tests that assert the plan has exactly the required keys, that every title case above is present with the correct shape and count (the suite fails if even one is missing), and that no out-of-lane case (filtering or page math) appears. Additionally, in this same update and under the update-agent gates, append the two standard sections below to this agent (identical for every agent in this file).

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

## Error handling

### validate-request-payloads — 1083 cases · now 6/10 → 10

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

### validate-null-empty-fields — 873 cases · now 8/10 → 10

```
update-agent api-tester-validate-null-empty-fields Specify the complete null/empty/absent tester for the target collection's write bodies (the sole owner of these states), emitting a JSON matrix covering, per field of the documented schema, the absent-or-empty states key-absent, json-null, empty-string, integer-zero, boolean-false, empty-array, empty-object, and whitespace-only; an all-required-null body; an each-required-null array; a combo of multiple required nulls; the four-character string "null" in string fields; and, for object/array fields, a null in a required sub-field and a null first array element. api-tester-validate-request-payloads defers all absent/null/empty/whitespace states here, so keep this matrix authoritative; leave wrong-type values to api-tester-validate-request-payloads and enum membership to api-tester-verify-enum-value-restrictions. Emit JSON only — no HTTP, no network, sandbox to FORGE_WORKSPACE; a separate deterministic harness sends each body and records responses. In the same update and under the same gates, build this agent's lane-and-coverage safety net: a GUARDRAIL that keeps it in its lane — it emits only the JSON null/empty/absent matrix above and never type/format/range cases (api-tester-validate-request-payloads) or enum cases (api-tester-verify-enum-value-restrictions), failing closed rather than straying out of lane; GOLDEN test cases pinning the exact expected matrix and covering every state the title workflow names above with none omitted, saved as the regression baseline at tests/golden/api-tester/validate-null-empty-fields/golden.json; and UNIT tests that assert the matrix has exactly the six required keys and the correct per-field state counts, that every title state above is present (the suite fails if even one is missing), and that no out-of-lane case (type/format/range or enum) appears. Additionally, in this same update and under the update-agent gates, append the two standard sections below to this agent (identical for every agent in this file).

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

### verify-response-status-codes — 44 cases · now 6/10 → 10

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

### verify-error-message-clarity — 24 cases · now 6/10 → 10

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

### verify-enum-value-restrictions — 92 cases · now 7/10 → 10

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

---

# Remaining agents

### api-tester-validate-json-schema-responses — now 5/10 → 10

```
update-agent api-tester-validate-json-schema-responses Specify the complete response-schema validation tester: given one endpoint (operationId, method, path, auth, the documented response status keys with whether each has a JSON schema, and a valid body), emit a JSON object with one request descriptor per documented response code (the success code and each documented 4xx/5xx) plus the documented response-schema map, so the harness validates every response body — not just the happy 2xx — against its documented schema with ajv v8. Require strict validation: additionalProperties:false rejects undocumented response fields, every required field is present and correctly typed, a list response validates every item against the item schema and asserts the list is non-empty, and the response Content-Type is application/json. Leave error-message wording and internal-leak checks to api-tester-verify-error-message-clarity. Emit JSON only — no HTTP, no network, sandbox to FORGE_WORKSPACE; a separate deterministic harness sends the requests and validates the real bodies. In the same update and under the same gates, build this agent's lane-and-coverage safety net: a GUARDRAIL that keeps it in its lane — it emits only the JSON contract above and never a case owned by the agents named in the "leave … to …" boundaries, failing closed rather than straying out of lane; GOLDEN test cases pinning the exact expected JSON plan for representative endpoint briefs and covering every single case the title workflow names above (a descriptor per documented response code, the schema map, strict-validation flags, list-item validation, content-type) with none omitted, saved as the regression baseline at tests/golden/api-tester/validate-json-schema-responses/golden.json; and UNIT tests that, per golden brief, assert the plan has exactly the required top-level keys, that every title-named case above is present with the correct shape and count (the suite fails if even one is missing), and that no out-of-lane case (error-message clarity) appears. Additionally, in this same update and under the update-agent gates, append the two standard sections below to this agent (identical for every agent in this file).

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

### api-tester-validate-header-propagation — now 5/10 → 10

```
update-agent api-tester-validate-header-propagation Specify the complete request-header forwarding tester (general header propagation, not correlation-id): given an endpoint and its downstream services, emit a JSON plan with a with-headers request and assertions that each forwarded header — Authorization, the W3C trace pair traceparent and tracestate, B3 (X-B3-TraceId/SpanId), the X-Forwarded-* set, and one custom X- header — reaches every downstream service byte-for-byte and appears unmodified in the downstream logs; that hop-by-hop headers (Connection, Keep-Alive, Transfer-Encoding, Upgrade) are NOT forwarded; and that an inbound traceparent is continued downstream with the same trace-id. Leave the X-Correlation-ID echo, UUIDv4 auto-generation, and correlation-specific log greps to api-tester-validate-correlation-id-propagation. Emit JSON only — no HTTP, no network, sandbox to FORGE_WORKSPACE; a separate deterministic harness runs the plan and reads the captured logs. In the same update and under the same gates, build this agent's lane-and-coverage safety net: a GUARDRAIL that keeps it in its lane — it emits only the JSON contract above and never a case owned by the agents named in the "leave … to …" boundaries, failing closed rather than straying out of lane; GOLDEN test cases pinning the exact expected JSON plan and covering every single case the title workflow names above (forwarding of Authorization, traceparent, tracestate, B3, X-Forwarded-*, a custom header; hop-by-hop stripping; traceparent continuation) with none omitted, saved as the regression baseline at tests/golden/api-tester/validate-header-propagation/golden.json; and UNIT tests that, per golden brief, assert the plan has exactly the required top-level keys, that every title-named case above is present with the correct shape and count (the suite fails if even one is missing), and that no out-of-lane case (correlation-id semantics) appears. Additionally, in this same update and under the update-agent gates, append the two standard sections below to this agent (identical for every agent in this file).

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

### api-tester-test-rate-limit-enforcement — now 6/10 → 10

```
update-agent api-tester-test-rate-limit-enforcement Specify the complete rate-limit enforcement tester: given an endpoint's rate-limit contract (limit N per window, key header and value, success code, window seconds, retry-after header name), emit a JSON plan covering an at-limit burst of exactly N requests (all succeed); one over-limit request (throttled); two wall-clock probes (just before the window closes still limited, just after it opens succeeds); per-key isolation (a second key runs its own full allowance unaffected by the first key's exhaustion); the documented limit scope (per-endpoint vs global counted correctly); and the RateLimit-Limit/Remaining/Reset (or X-RateLimit-*) headers present and decrementing correctly across the burst. Leave the 429 Retry-After header's presence, format and honoring to api-tester-validate-retry-after-header-compliance. Emit JSON only — no HTTP, no network, sandbox to FORGE_WORKSPACE; a separate deterministic harness runs read-only GETs at real wall-clock timing and records the real responses. In the same update and under the same gates, build this agent's lane-and-coverage safety net: a GUARDRAIL that keeps it in its lane — it emits only the JSON contract above and never a case owned by the agents named in the "leave … to …" boundaries, failing closed rather than straying out of lane; GOLDEN test cases pinning the exact expected JSON plan and covering every single case the title workflow names above (at-limit burst, over-limit, both window probes, per-key isolation, limit scope, RateLimit-* header decrement) with none omitted, saved as the regression baseline at tests/golden/api-tester/test-rate-limit-enforcement/golden.json; and UNIT tests that, per golden brief, assert the plan has exactly the required top-level keys, that every title-named case above is present with the correct shape and count (the suite fails if even one is missing), and that no out-of-lane case (Retry-After header verification) appears. Additionally, in this same update and under the update-agent gates, append the two standard sections below to this agent (identical for every agent in this file).

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

### api-tester-verify-content-type-negotiation — now 6/10 → 10

```
update-agent api-tester-verify-content-type-negotiation Specify the complete content-negotiation tester: given an endpoint and a kind, emit a JSON plan covering, for response negotiation, an Accept probe for each supported media type, an unsupported Accept (406), a wildcard Accept, a charset probe (application/json; charset=utf-8 asserting a correct echoed charset), a q-value preference probe (the higher-q supported format is chosen), and an Accept-Encoding probe (gzip/br with a matching Content-Encoding); and for request negotiation a supported Content-Type (accepted), unsupported Content-Types (415), a missing Content-Type (documented default or 415), and a charset-in-Content-Type probe. Add an Accept-Language probe only if localization is documented. Emit JSON only — no HTTP, no network, sandbox to FORGE_WORKSPACE; a separate deterministic harness sends each probe and records the real status and response headers. In the same update and under the same gates, build this agent's lane-and-coverage safety net: a GUARDRAIL that keeps it in its lane — it emits only the JSON contract above (Accept/Content-Type negotiation) and never version negotiation or other header concerns, failing closed rather than straying out of lane; GOLDEN test cases pinning the exact expected JSON plan and covering every single case the title workflow names above (per-format Accept, 406 unsupported, wildcard, charset, q-value, Accept-Encoding; supported and unsupported Content-Type, missing Content-Type, charset-in-Content-Type) with none omitted, saved as the regression baseline at tests/golden/api-tester/verify-content-type-negotiation/golden.json; and UNIT tests that, per golden brief, assert the plan has exactly the required top-level keys, that every title-named probe above is present in order with the correct shape (the suite fails if even one is missing), and that no out-of-lane case appears. Additionally, in this same update and under the update-agent gates, append the two standard sections below to this agent (identical for every agent in this file).

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

### api-tester-validate-api-versioning-behavior — now 6/10 → 10

```
update-agent api-tester-validate-api-versioning-behavior Specify the complete versioning tester: given an endpoint's versioning contract (supported versions with current/deprecated status, unsupported versions, the v2-vs-v1 schema-diff field), emit a JSON plan covering path-based versions (current returns 200 with its schema and no Deprecation header; deprecated returns 200 with its schema plus a future-dated Deprecation header, a Sunset header, and a successor Link; unsupported returns 404, or 400 for a non-numeric version); header/media-type versioning (Accept: application/vnd.api.v2+json current, v1 deprecated, v0/v99 unsupported); query-parameter versioning if documented; and a default-version case (no version supplied returns the documented default or an explicit error). Validate each response body per version with ajv v8. Emit JSON only — no HTTP, no network, sandbox to FORGE_WORKSPACE; a separate deterministic harness runs read-only GETs and records the real responses. In the same update and under the same gates, build this agent's lane-and-coverage safety net: a GUARDRAIL that keeps it in its lane — it emits only the JSON versioning contract above and never generic Accept/Content-Type negotiation, failing closed rather than straying out of lane; GOLDEN test cases pinning the exact expected JSON plan and covering every single case the title workflow names above (current, deprecated with Deprecation+Sunset+successor Link, unsupported 404/400; header/media-type versions; query-param version; default-version) with none omitted, saved as the regression baseline at tests/golden/api-tester/validate-api-versioning-behavior/golden.json; and UNIT tests that, per golden brief, assert the plan has exactly the required top-level keys, that every title-named case above is present with the correct shape and count (the suite fails if even one is missing), and that no out-of-lane case (general content negotiation) appears. Additionally, in this same update and under the update-agent gates, append the two standard sections below to this agent (identical for every agent in this file).

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

### api-tester-test-webhook-delivery — now 6/10 → 10

```
update-agent api-tester-test-webhook-delivery Specify the complete webhook-delivery tester: given a resource's webhook contract (register and resource paths, receiver url, event type, signature scheme, deadlines, retry policy), emit a JSON plan covering register a receiver, trigger a resource event, poll a local receiver, and assert delivery within the deadline with the exact event_type and resource_id, an ISO-8601 timestamp, and a valid HMAC-SHA256 signature; event filtering (only subscribed event types are delivered); multi-retry backoff on repeated 500s following the documented increasing schedule with dead-letter/disable after the max attempts; a non-retryable 4xx receiver response that is not retried; and a tamper-negative (an altered payload fails signature verification at the consumer). Leave message-broker/topic semantics to api-tester-test-event-driven-api-triggers. Emit JSON only — no servers, no sockets, no HTTP, no signature computation, sandbox to FORGE_WORKSPACE; a separate deterministic harness runs the receiver, computes signatures, and records results. In the same update and under the same gates, build this agent's lane-and-coverage safety net: a GUARDRAIL that keeps it in its lane — it emits only the JSON contract above and never a case owned by api-tester-test-event-driven-api-triggers, failing closed rather than straying out of lane; GOLDEN test cases pinning the exact expected JSON plan and covering every single case the title workflow names above (register, trigger, poll, payload+timestamp+HMAC assertions, event filtering, multi-retry backoff, dead-letter after max, non-retryable 4xx, tamper-negative) with none omitted, saved as the regression baseline at tests/golden/api-tester/test-webhook-delivery/golden.json; and UNIT tests that, per golden brief, assert the plan has exactly the required top-level keys, that every title-named case above is present with the correct shape and count (the suite fails if even one is missing), and that no out-of-lane case (broker/topic delivery) appears. Additionally, in this same update and under the update-agent gates, append the two standard sections below to this agent (identical for every agent in this file).

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

### api-tester-test-timeout-handling — now 6/10 → 10

```
update-agent api-tester-test-timeout-handling Specify the complete timeout tester: given a service's upstream-timeout contract (upstream timeout, buffer, restore budget) and its upstream-dependent endpoints, emit a JSON plan covering, under an injected upstream delay, each endpoint returning a gateway timeout (504/408) within max_wait = upstream_timeout + buffer with a clean error body that leaks no upstream URL, host, or stack, and recovering within the restore budget after the delay clears; a slow-client/slowloris case (the client dribbles the body slower than the read budget, asserting the documented 408-class response and no hang); a connect-timeout vs read-timeout distinction; and a retry-on-timeout assertion if the contract documents upstream retry. Leave gateway routing to api-tester-test-api-gateway-routing. Emit JSON only — no HTTP, no delay injection, no sockets, sandbox to FORGE_WORKSPACE; a separate deterministic harness injects the delay and records the real timing and responses. In the same update and under the same gates, build this agent's lane-and-coverage safety net: a GUARDRAIL that keeps it in its lane — it emits only the JSON contract above and never a case owned by api-tester-test-api-gateway-routing, failing closed rather than straying out of lane; GOLDEN test cases pinning the exact expected JSON plan and covering every single case the title workflow names above (per-endpoint delayed timeout within max_wait, safe error body, restore within budget, slow-client/slowloris, connect-vs-read distinction, retry-on-timeout) with none omitted, saved as the regression baseline at tests/golden/api-tester/test-timeout-handling/golden.json; and UNIT tests that, per golden brief, assert the plan has exactly the required top-level keys, max_wait = upstream_timeout + buffer, that every title-named case above is present with the correct shape and count (the suite fails if even one is missing), and that no out-of-lane case (gateway routing) appears. Additionally, in this same update and under the update-agent gates, append the two standard sections below to this agent (identical for every agent in this file).

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

### api-tester-test-concurrent-request-handling — now 6/10 → 10

```
update-agent api-tester-test-concurrent-request-handling Specify the complete concurrency tester: given read and write endpoints with their expected statuses, a concurrency count, and a per-VU unique-id template, emit a JSON plan covering N simultaneous GETs returning identical bodies; N simultaneous POSTs each carrying a unique id, verified by a direct database query for exact count delta, zero duplicates and zero missing; N simultaneous updates to one resource (optimistic locking rejects stale writers with 409/412 with exactly one winner and no lost update); N simultaneous creates with an identical unique key (exactly one 201, the rest 409, exactly one DB row); and zero 500s throughout. Leave sequential idempotent replay to api-tester-test-idempotency-of-endpoints. Emit JSON only — no HTTP, no network, sandbox to FORGE_WORKSPACE; a separate deterministic harness fires the simultaneous requests and queries the database directly. In the same update and under the same gates, build this agent's lane-and-coverage safety net: a GUARDRAIL that keeps it in its lane — it emits only the JSON contract above and never a case owned by api-tester-test-idempotency-of-endpoints, failing closed rather than straying out of lane; GOLDEN test cases pinning the exact expected JSON plan and covering every single case the title workflow names above (concurrent read identical-bodies, concurrent write unique-id with DB count/dup/missing asserts, concurrent update optimistic-lock, concurrent create same-unique-key, assert-zero-500) with none omitted, saved as the regression baseline at tests/golden/api-tester/test-concurrent-request-handling/golden.json; and UNIT tests that, per golden brief, assert the plan has exactly the required top-level keys, the [VU_ID] template preserved, that every title-named case above is present with the correct shape and count (the suite fails if even one is missing), and that no out-of-lane case (sequential replay) appears. Additionally, in this same update and under the update-agent gates, append the two standard sections below to this agent (identical for every agent in this file).

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

### api-tester-verify-sorting-behavior — now 6/10 → 10

```
update-agent api-tester-verify-sorting-behavior Specify the complete sorting tester: given a collection's sort contract (sortable string, numeric and timestamp fields), emit a JSON plan that seeds about twenty records with deliberately unordered values and covers ascending and descending order by a string field, a numeric field (numeric order so 9 sorts before 100, not lexicographic), and a timestamp field; a multi-field/secondary sort with a stability assertion that equal primary keys keep their secondary order; null-value ordering (documented nulls-first or nulls-last); string collation/case sensitivity; sort combined with pagination (stable and correct across page boundaries); and invalid-sort-field and invalid-order-direction probes (400). Assert every adjacent record pair is correctly ordered. Leave generic param coercion to api-tester-validate-query-parameter-handling. Emit JSON only — no HTTP, no seeding, no network, sandbox to FORGE_WORKSPACE; a separate deterministic harness seeds an isolated reference resource and runs read-only GETs. In the same update and under the same gates, build this agent's lane-and-coverage safety net: a GUARDRAIL that keeps it in its lane — it emits only the JSON contract above and never a case owned by api-tester-validate-query-parameter-handling, failing closed rather than straying out of lane; GOLDEN test cases pinning the exact expected JSON plan (seed records plus sort cases) and covering every single case the title workflow names above (asc/desc by string, numeric, timestamp; multi-field secondary with stability; null ordering; collation/case; sort+pagination; invalid-field 400; invalid-order 400) with none omitted, saved as the regression baseline at tests/golden/api-tester/verify-sorting-behavior/golden.json; and UNIT tests that, per golden brief, assert the plan has exactly the required top-level keys, the documented seed-record count, that every title-named case above is present with the correct shape and count (the suite fails if even one is missing), and that no out-of-lane case (generic param coercion) appears. Additionally, in this same update and under the update-agent gates, append the two standard sections below to this agent (identical for every agent in this file).

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

### api-tester-verify-third-party-oauth-integration — now 6/10 → 10

```
update-agent api-tester-verify-third-party-oauth-integration Specify the complete OAuth2 authorization-code tester: given a provider's flow (authorize/callback/token/userinfo/refresh endpoints, client_id, redirect_uri, scope, state minimum length), emit a JSON staged plan covering the happy path — redirect (302 carrying client_id, redirect_uri, scope, a CSRF state of sufficient length, and an https location), code receipt (state matches), token exchange (200 with access token, refresh token, bearer type, positive expiry), userinfo (200 with a non-empty profile field), and refresh (200 with a new access token) — plus the security negatives: a mismatched state is rejected (CSRF), a redirect_uri different from the registered one is rejected, a replayed or expired authorization code is rejected, a wrong client_secret is rejected, a PKCE code_verifier mismatch is rejected if PKCE is documented, and a denied-consent error redirect (access_denied) is handled. Leave first-party credential validity to api-tester-test-authentication-flows. Emit JSON only — no HTTP, no network, sandbox to FORGE_WORKSPACE; a separate deterministic harness drives the real flow and records responses. In the same update and under the same gates, build this agent's lane-and-coverage safety net: a GUARDRAIL that keeps it in its lane — it emits only the JSON staged-flow contract above and never a case owned by api-tester-test-authentication-flows, failing closed rather than straying out of lane; GOLDEN test cases pinning the exact expected staged JSON plan and covering every single case the title workflow names above (the five happy-path stages with their asserts, plus state-CSRF, bad-redirect-uri, replayed/expired code, wrong client_secret, PKCE mismatch, denied-consent) with none omitted, saved as the regression baseline at tests/golden/api-tester/verify-third-party-oauth-integration/golden.json; and UNIT tests that, per golden brief, assert the plan has exactly the required top-level keys and the staged structure, that every title-named stage and negative above is present with the correct shape and count (the suite fails if even one is missing), and that no out-of-lane case (first-party credential validity) appears. Additionally, in this same update and under the update-agent gates, append the two standard sections below to this agent (identical for every agent in this file).

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

### api-tester-validate-correlation-id-propagation — now 6/10 → 10

```
update-agent api-tester-validate-correlation-id-propagation Specify the complete correlation-ID tester (the sole owner of correlation-id semantics): given an endpoint, a header name, downstream services, and a UUIDv4 regex, emit a JSON plan with a with-header request carrying a known X-Correlation-ID and a no-header request, plus assertions that the response echoes the id exactly; the id appears unmodified in the API log and each downstream log; a no-header request auto-generates a valid UUIDv4 that flows to all logs; two no-header requests generate two different UUIDv4s; an error response on the endpoint still echoes the id; and a malformed correlation-id (over-long, containing CRLF/control characters, or injection metacharacters) is rejected or sanitized and never reflected raw into logs. Leave generic header forwarding (Authorization, traceparent/tracestate, X-Forwarded-*, custom headers, hop-by-hop stripping) to api-tester-validate-header-propagation. Emit JSON only — no HTTP, no network, no log reading, sandbox to FORGE_WORKSPACE; a separate deterministic harness runs the plan and greps the captured logs. In the same update and under the same gates, build this agent's lane-and-coverage safety net: a GUARDRAIL that keeps it in its lane — it emits only the correlation-id JSON contract above and never the generic header-forwarding cases owned by api-tester-validate-header-propagation, failing closed rather than straying out of lane; GOLDEN test cases pinning the exact expected JSON plan and covering every single case the title workflow names above (with-header echo, log-present/unmodified across downstreams, no-header UUIDv4 auto-gen in all logs, uniqueness across two no-header requests, id-in-error, malformed-id handling) with none omitted, saved as the regression baseline at tests/golden/api-tester/validate-correlation-id-propagation/golden.json; and UNIT tests that, per golden brief, assert the plan has exactly the required top-level keys and the fixed assertion list, that every title-named case above is present with the correct shape and count (the suite fails if even one is missing), and that no out-of-lane case (generic header forwarding) appears. Additionally, in this same update and under the update-agent gates, append the two standard sections below to this agent (identical for every agent in this file).

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

### api-tester-verify-caching-headers — now 6/10 → 10

```
update-agent api-tester-verify-caching-headers Specify the complete caching-headers tester: given a cacheable endpoint (collection path, id field, target id), emit a JSON plan covering a cacheable GET returning Cache-Control and ETag; a conditional GET with If-None-Match returning 304 with an empty body; a conditional GET with If-Modified-Since against Last-Modified returning 304; a Vary-header assertion for the documented varying headers; an If-Match precondition on update where a stale ETag yields 412 and the row is unchanged; an update that changes a field and asserts the ETag changes; a freshness assertion that Cache-Control max-age/s-maxage match the documented values; and the four mutations (POST/PUT/PATCH/DELETE) asserting no-store. Leave idempotent-replay semantics to api-tester-test-idempotency-of-endpoints. Emit JSON only — no HTTP, no network, sandbox to FORGE_WORKSPACE; a separate deterministic harness sends each request and records the real Cache-Control and ETag headers. In the same update and under the same gates, build this agent's lane-and-coverage safety net: a GUARDRAIL that keeps it in its lane — it emits only the JSON contract above and never a case owned by api-tester-test-idempotency-of-endpoints, failing closed rather than straying out of lane; GOLDEN test cases pinning the exact expected JSON plan and covering every single case the title workflow names above (cacheable GET, If-None-Match 304, If-Modified-Since 304, Vary, If-Match 412, post-update ETag change, max-age freshness, four-mutation no-store) with none omitted, saved as the regression baseline at tests/golden/api-tester/verify-caching-headers/golden.json; and UNIT tests that, per golden brief, assert the plan has exactly the required top-level keys, that every title-named case above is present with the correct shape and count (the suite fails if even one is missing), and that no out-of-lane case (idempotent replay) appears. Additionally, in this same update and under the update-agent gates, append the two standard sections below to this agent (identical for every agent in this file).

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

### api-tester-test-event-driven-api-triggers — now 6/10 → 10

```
update-agent api-tester-test-event-driven-api-triggers Specify the complete event-trigger tester: given a message topic's contract (resource and state fields, event type, required fields and values, and the required field to drop for a malformed event), emit a JSON plan covering a well-formed event that drives the resource to its expected state within the poll window; a malformed event (one required field dropped) that is ERROR-logged, dead-lettered within the deadline, leaves state unchanged, and does not crash the consumer; a duplicate well-formed event (the idempotent consumer applies it exactly once); an out-of-order pair for one key (the documented ordering/versioning rule — later state wins or the stale event is dropped); and a poison message retried the documented number of times before dead-lettering. Leave HTTP-callback webhooks to api-tester-test-webhook-delivery. Emit JSON only — no publishing, no broker contact, no network, sandbox to FORGE_WORKSPACE; a separate deterministic harness publishes the events, polls state, and reads the consumer log and dead-letter queue. In the same update and under the same gates, build this agent's lane-and-coverage safety net: a GUARDRAIL that keeps it in its lane — it emits only the JSON contract above and never a case owned by api-tester-test-webhook-delivery, failing closed rather than straying out of lane; GOLDEN test cases pinning the exact expected JSON plan and covering every single case the title workflow names above (well-formed→state within window, malformed→ERROR-log+DLQ+unchanged+health, duplicate idempotent, out-of-order, poison-retry-then-DLQ) with none omitted, saved as the regression baseline at tests/golden/api-tester/test-event-driven-api-triggers/golden.json; and UNIT tests that, per golden brief, assert the plan has exactly the required top-level keys and that the malformed event differs from the well-formed only by the dropped field, that every title-named case above is present with the correct shape and count (the suite fails if even one is missing), and that no out-of-lane case (HTTP-callback webhooks) appears. Additionally, in this same update and under the update-agent gates, append the two standard sections below to this agent (identical for every agent in this file).

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

### api-tester-verify-audit-log-generation — now 6/10 → 10

```
update-agent api-tester-verify-audit-log-generation Specify the complete audit-log tester: given a collection (path, id field, a test user), emit a JSON plan that performs create/update/delete operations as that user and queries the audit log, asserting three entries with the required fields user_id, action_type, resource_id, timestamp and ip_address within a time window and tolerance; a read entry if sensitive GETs are audited; a failed-action entry for a denied (403) or unauthenticated (401) attempt; auth-event entries for login and logout; before/after values captured on the update entry; and immutability (an attempt to modify or delete an audit entry via the API is rejected). Leave correlation/trace log propagation to api-tester-validate-correlation-id-propagation. Emit JSON only — no HTTP, no login, no network, sandbox to FORGE_WORKSPACE; a separate deterministic harness authenticates, runs the operations, captures the log, and queries it. In the same update and under the same gates, build this agent's lane-and-coverage safety net: a GUARDRAIL that keeps it in its lane — it emits only the JSON contract above and never a case owned by api-tester-validate-correlation-id-propagation, failing closed rather than straying out of lane; GOLDEN test cases pinning the exact expected JSON plan and covering every single case the title workflow names above (create/update/delete entries with required fields, read audit, failed-action audit, login/logout audit, before/after on update, immutability) with none omitted, saved as the regression baseline at tests/golden/api-tester/verify-audit-log-generation/golden.json; and UNIT tests that, per golden brief, assert the plan has exactly the required top-level keys and audit_query fields, that every title-named case above is present with the correct shape and count (the suite fails if even one is missing), and that no out-of-lane case (correlation/trace propagation) appears. Additionally, in this same update and under the update-agent gates, append the two standard sections below to this agent (identical for every agent in this file).

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

### api-tester-test-api-gateway-routing — now 6/10 → 10

```
update-agent api-tester-test-api-gateway-routing Specify the complete gateway-routing tester: given a route's contract (path, method, headers, body, expected backend, the full backend list, a down flag), emit a JSON plan covering the request reaching exactly the correct single backend with path, method, headers and body unchanged and the response returned unchanged while no other backend receives it; a path-rewrite/prefix-strip case asserting the backend sees the rewritten path; an unknown-route case (the gateway returns 404 itself with no backend hit) and a method-not-allowed-at-gateway case; a load-balancing/weighting case across multiple instances per the documented policy; a gateway-injected-header assertion (X-Forwarded-For/Proto and X-Request-ID added before the backend sees the request); and a service-down case (503). Leave upstream timeout behavior to api-tester-test-timeout-handling. Emit JSON only — no HTTP, no gateway/backend contact, no network, sandbox to FORGE_WORKSPACE; a separate deterministic harness routes the request and queries each backend's journal. In the same update and under the same gates, build this agent's lane-and-coverage safety net: a GUARDRAIL that keeps it in its lane — it emits only the JSON contract above and never a case owned by api-tester-test-timeout-handling, failing closed rather than straying out of lane; GOLDEN test cases pinning the exact expected JSON plan and covering every single case the title workflow names above (correct-single-backend with unchanged path/method/headers/body, other-backends-untouched, path-rewrite, unknown-route 404, method-not-allowed, load-balancing/weighting, gateway-injected headers, service-down 503) with none omitted, saved as the regression baseline at tests/golden/api-tester/test-api-gateway-routing/golden.json; and UNIT tests that, per golden brief, assert the plan has exactly the required top-level keys and that other_backends excludes the expected backend, that every title-named case above is present with the correct shape and count (the suite fails if even one is missing), and that no out-of-lane case (upstream timeout) appears. Additionally, in this same update and under the update-agent gates, append the two standard sections below to this agent (identical for every agent in this file).

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

### api-tester-validate-retry-after-header-compliance — now 6/10 → 10

```
update-agent api-tester-validate-retry-after-header-compliance Specify the complete Retry-After compliance tester (the sole owner of the Retry-After header): given an endpoint's rate-limit contract, emit a JSON plan that elicits a throttled response and verifies the Retry-After header — an at-limit burst then an over-limit request returning 429 carrying Retry-After; two probes anchored to the advertised deadline (one second before it is still limited, one second after it succeeds); coverage of both header forms (a positive-integer seconds value and a valid future RFC 7231 HTTP-date, each honored); a 503 case that also advertises Retry-After under maintenance/overload; and a sanity bound that the advertised delay is within a documented reasonable maximum. Leave limit counting, window reset, per-key isolation and RateLimit-* headers to api-tester-test-rate-limit-enforcement. Emit JSON only — no HTTP, no header parsing, no network, sandbox to FORGE_WORKSPACE; a separate deterministic harness reads the real header, computes the deadline, and measures timing. In the same update and under the same gates, build this agent's lane-and-coverage safety net: a GUARDRAIL that keeps it in its lane — it emits only the JSON Retry-After contract above and never the enforcement cases owned by api-tester-test-rate-limit-enforcement, failing closed rather than straying out of lane; GOLDEN test cases pinning the exact expected JSON plan and covering every single case the title workflow names above (at-limit burst, over-limit 429-with-Retry-After, both deadline-anchored probes, integer-seconds and HTTP-date forms, 503 Retry-After, sanity bound) with none omitted, saved as the regression baseline at tests/golden/api-tester/validate-retry-after-header-compliance/golden.json; and UNIT tests that, per golden brief, assert the plan has exactly the required top-level keys and the deadline-anchored probe offsets, that every title-named case above is present with the correct shape and count (the suite fails if even one is missing), and that no out-of-lane case (limit counting, window reset, isolation, RateLimit-* headers) appears. Additionally, in this same update and under the update-agent gates, append the two standard sections below to this agent (identical for every agent in this file).

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

### api-tester-validate-graphql-depth-limits — now 6/10 → 10

```
update-agent api-tester-validate-graphql-depth-limits Specify the complete GraphQL query-protection tester: given a GraphQL endpoint and its documented maximum query depth, emit a JSON plan covering a depth-3 query accepted; an at-limit query at exactly max depth accepted; a one-over query at max+1 rejected with a depth/complexity error; a very deep query rejected quickly (within one second); a complexity/cost case (a shallow but very broad query exceeding the documented complexity budget, rejected); an alias-amplification case (the same expensive field under many aliases, rejected); a fragment-cycle case (a circular fragment rejected rather than expanded infinitely); an introspection case (the documented production introspection policy enforced); and a batched-query case (an array of operations capped at the documented batch limit). Depth means nested field selection sets, not characters or tokens. Emit JSON only — no query strings, no HTTP, no network, sandbox to FORGE_WORKSPACE; a separate deterministic harness builds each query at the requested depth and records the real responses and timing. In the same update and under the same gates, build this agent's lane-and-coverage safety net: a GUARDRAIL that keeps it in its lane — it emits only the JSON depth/complexity contract above and never general rate-limiting, failing closed rather than straying out of lane; GOLDEN test cases pinning the exact expected JSON plan and covering every single case the title workflow names above (depth-3 accept, at-limit accept, one-over reject, deep timed reject, complexity/cost, alias-amplification, fragment-cycle, introspection, batched-query) with none omitted, saved as the regression baseline at tests/golden/api-tester/validate-graphql-depth-limits/golden.json; and UNIT tests that, per golden brief, assert the plan has exactly the required top-level keys and that depth integers equal 3, max_depth, max_depth+1 and 15 respectively, that every title-named case above is present with the correct shape and count (the suite fails if even one is missing), and that no out-of-lane case appears. Additionally, in this same update and under the update-agent gates, append the two standard sections below to this agent (identical for every agent in this file).

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

### api-tester-test-long-polling-support — now 6/10 → 10

```
update-agent api-tester-test-long-polling-support Specify the complete long-polling tester: given a channel's contract (poll and trigger paths, poll timeout, expected event type), emit a JSON plan with client_max_time = poll_timeout + 5 covering a no-event case (the connection returns 204 with an empty body within the window); an event case (an event triggered mid-poll returns 200 within two seconds of the trigger with the correct event_type); a multiple-events case (two events during one window are both delivered, queued not dropped); a resume-after-gap case using the documented cursor/Last-Event-ID (an event published between polls is not lost); a concurrent-pollers case (two clients receive a broadcast event, or behave per the documented single-consumer rule); and a connection-drop case (a client disconnecting mid-poll does not wedge the channel). Leave broker/topic semantics to api-tester-test-event-driven-api-triggers. Emit JSON only — no connections, no triggering, no sockets, sandbox to FORGE_WORKSPACE; a separate deterministic harness opens the connections, triggers the event, and records responses. In the same update and under the same gates, build this agent's lane-and-coverage safety net: a GUARDRAIL that keeps it in its lane — it emits only the JSON contract above and never a case owned by api-tester-test-event-driven-api-triggers, failing closed rather than straying out of lane; GOLDEN test cases pinning the exact expected JSON plan and covering every single case the title workflow names above (no-event 204-empty, event 200-within-2s correct-type, multiple-events queued, resume-after-gap via Last-Event-ID, concurrent-pollers, connection-drop) with none omitted, saved as the regression baseline at tests/golden/api-tester/test-long-polling-support/golden.json; and UNIT tests that, per golden brief, assert the plan has exactly the required top-level keys and client_max_time = poll_timeout + 5, that every title-named case above is present with the correct shape and count (the suite fails if even one is missing), and that no out-of-lane case (broker/topic semantics) appears. Additionally, in this same update and under the update-agent gates, append the two standard sections below to this agent (identical for every agent in this file).

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

### api-tester-test-file-upload-and-download — now 6/10 → 10

```
update-agent api-tester-test-file-upload-and-download Specify the complete file-handling tester (file semantics and security, complementing the multipart agent): given an upload endpoint's contract (max size, allowed MIME types, status codes), emit a JSON plan covering uploads of 1KB, exactly the max size, and max+1 (rejected); a 0-byte file (documented accept or reject); a disallowed-MIME file; a magic-byte-vs-declared-MIME mismatch (declared image/jpeg but non-JPEG bytes, rejected by content sniffing); a path-traversal filename (../../evil.sh sanitized with no traversal); downloads with a byte-for-byte MD5 round-trip and a Content-Disposition filename; a download of a nonexistent or already-deleted file (404, no bytes); and a download-authorization case (a second user cannot fetch the first user's file, 403/404, no bytes). Leave multipart parsing mechanics to api-tester-test-multipart-form-data-handling. Emit JSON only — no HTTP, no file building, no hashing, no network, sandbox to FORGE_WORKSPACE; a separate deterministic harness builds the files, runs the plan, and compares MD5. In the same update and under the same gates, build this agent's lane-and-coverage safety net: a GUARDRAIL that keeps it in its lane — it emits only the JSON file-handling contract above and never the multipart-encoding cases owned by api-tester-test-multipart-form-data-handling, failing closed rather than straying out of lane; GOLDEN test cases pinning the exact expected JSON plan and covering every single case the title workflow names above (1KB, max, max+1 reject, 0-byte, disallowed-MIME, magic-byte mismatch, path-traversal filename, MD5 round-trip downloads, download-404, download-authorization) with none omitted, saved as the regression baseline at tests/golden/api-tester/test-file-upload-and-download/golden.json; and UNIT tests that, per golden brief, assert the plan has exactly the required top-level keys and the size integers (1024, max, max+1), that every title-named case above is present with the correct shape and count (the suite fails if even one is missing), and that no out-of-lane case (multipart parsing) appears. Additionally, in this same update and under the update-agent gates, append the two standard sections below to this agent (identical for every agent in this file).

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

### api-tester-test-multipart-form-data-handling — now 6/10 → 10

```
update-agent api-tester-test-multipart-form-data-handling Specify the complete multipart-encoding tester (parsing mechanics, complementing the file-upload agent): given an upload endpoint's multipart contract (two text fields, one file field, max file bytes, readback path), emit a JSON plan covering a baseline submit asserting create status, exact storage of each text field, the documented returned-file URL field, a file MD5 round-trip, and persisted readback; a multi-file case (two file parts under one field name forming an array, both stored); a part-without-filename case; a duplicate-text-field case (first/last/array policy); a field-order-independence case (a file part before the text parts still parses correctly); and a malformed-boundary case (400). Leave file size limits, MIME-type rejection and integrity policy to api-tester-test-file-upload-and-download. Emit JSON only — no HTTP, no file building/encoding/hashing, no network, sandbox to FORGE_WORKSPACE; a separate deterministic harness builds the parts, runs the plan, and records responses. In the same update and under the same gates, build this agent's lane-and-coverage safety net: a GUARDRAIL that keeps it in its lane — it emits only the JSON multipart-encoding contract above and never the file size/MIME/integrity cases owned by api-tester-test-file-upload-and-download, failing closed rather than straying out of lane; GOLDEN test cases pinning the exact expected JSON plan and covering every single case the title workflow names above (baseline parts+storage+returned-URL-field+MD5+readback, multi-file array, part-without-filename, duplicate-text-field, field-order-independence, malformed-boundary) with none omitted, saved as the regression baseline at tests/golden/api-tester/test-multipart-form-data-handling/golden.json; and UNIT tests that, per golden brief, assert the plan has exactly the required top-level keys and the two text fields plus one file field, that every title-named case above is present with the correct shape and count (the suite fails if even one is missing), and that no out-of-lane case (file size/MIME/integrity policy) appears. Additionally, in this same update and under the update-agent gates, append the two standard sections below to this agent (identical for every agent in this file).

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

### api-tester-track-defect-density — now 7/10 → 10

```
update-agent api-tester-track-defect-density Specify the complete defect-density reporter (a pure deterministic calculator over the supplied brief — no Jira or git calls): given a sprint's Jira issues with priorities, a git numstat diff, and the three preceding densities, emit a JSON report containing sprint_name, defect_density (defects per 1000 changed lines, excluding test files), a severity-weighted density (P1=8/P2=4/P3=2/P4=1), per-area densities grouped by a component label, the rolling three-sprint average, the deviation percent, an alert flag when deviation exceeds 20 percent, the P1–P4 counts, and the trend versus the most recent sprint, with all arithmetic rounded half-up. Emit JSON only — no Jira, no git, no network, sandbox to FORGE_WORKSPACE; every value is derived solely from the brief. In the same update and under the same gates, build this agent's lane-and-coverage safety net: a GUARDRAIL that keeps it in its lane — it emits only the JSON report contract above, computes solely from the brief, and never calls Jira/git/network, failing closed rather than straying out of lane; GOLDEN test cases pinning the exact expected JSON report for representative sprint briefs and covering every single field and rule the title workflow names above (raw density with test-file exclusion, severity-weighted density, per-area densities, rolling 3-sprint average, deviation percent, 20% alert flag, P1–P4 counts, trend, half-up rounding) with none omitted, saved as the regression baseline at tests/golden/api-tester/track-defect-density/golden.json; and UNIT tests that, per golden brief, assert the report has exactly the required keys and that each computed value matches the hand-derived expected number (the suite fails if even one field or rule is wrong or missing), and that no out-of-lane behavior (any external call) appears. Additionally, in this same update and under the update-agent gates, append the two standard sections below to this agent (identical for every agent in this file).

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

### api-tester-test-ip-allowlist-enforcement — now 7/10 → 10

```
update-agent api-tester-test-ip-allowlist-enforcement Specify the complete IP-allowlist tester: given a restricted endpoint's contract (allow and block IPs, the edge-IP and X-Forwarded-For header names, the allowlist management path, success and forbidden codes), emit a JSON plan covering an allowlisted IP allowed (200 with data); a non-allowlisted IP blocked (403, no data); an X-Forwarded-For spoof from a blocked IP still blocked (the decision ignores the client-supplied header); a CIDR/subnet case (an IP inside an allowed range allowed, a sibling just outside blocked); an IPv6 case if supported; a multi-hop X-Forwarded-For case honoring only the trusted-proxy-depth client IP; a denylist-precedence case if a denylist coexists with the allowlist; and allowlist add and remove via the management API taking effect. Emit JSON only — no HTTP, no allowlist changes, no network, sandbox to FORGE_WORKSPACE; a separate deterministic harness sets the source IP, headers and allowlist actions and records responses. In the same update and under the same gates, build this agent's lane-and-coverage safety net: a GUARDRAIL that keeps it in its lane — it emits only the JSON IP-allowlist contract above and never role-based authorization, failing closed rather than straying out of lane; GOLDEN test cases pinning the exact expected JSON plan and covering every single case the title workflow names above (allowlisted-200, non-allowlisted-403, XFF-spoof-403, CIDR/subnet, IPv6, multi-hop XFF depth, denylist-precedence, allowlist add-allows, allowlist remove-blocks) with none omitted, saved as the regression baseline at tests/golden/api-tester/test-ip-allowlist-enforcement/golden.json; and UNIT tests that, per golden brief, assert the plan has exactly the required top-level keys and the no-data-on-block assertion, that every title-named case above is present with the correct shape and count (the suite fails if even one is missing), and that no out-of-lane case (role-based authorization) appears. Additionally, in this same update and under the update-agent gates, append the two standard sections below to this agent (identical for every agent in this file).

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

### api-tester-run-regression-suite — now 7/10 → 10

```
update-agent api-tester-run-regression-suite Specify the complete regression-suite reporter (a pure two-artifact comparator — no test execution or deployment actions): given a previous build's and a current build's automated-test result artifacts (JUnit XML, Jest --json, pytest-json, plus TAP and TRX/NUnit) and the two build ids, emit a JSON report listing the total tests, the previously-passing count, the regressions (passed in N-1, failed in N — already-failing, skipped and removed tests are never regressions) each with its failure message, the newly-passing tests, a flaky array (tests that both pass and fail across repeated runs of build N, excluded from regressions) when repeated runs are supplied, a slowed array (tests whose runtime grew beyond a documented multiple), and an overall status that is fail whenever any regression exists. Emit JSON only — no test runs, no deployment, no network, sandbox to FORGE_WORKSPACE; every value derives solely from the two artifacts. In the same update and under the same gates, build this agent's lane-and-coverage safety net: a GUARDRAIL that keeps it in its lane — it emits only the JSON report contract above, derives solely from the two artifacts, and never runs tests or touches deployment, failing closed rather than straying out of lane; GOLDEN test cases pinning the exact expected report for representative artifact pairs across each supported format and covering every single rule the title workflow names above (total, prev-passed, regression definition, newly-passing, flaky, slowed, overall status; already-failing/skipped/removed never count as regressions) with none omitted, saved as the regression baseline at tests/golden/api-tester/run-regression-suite/golden.json; and UNIT tests that, per golden pair, assert the report has exactly the required keys and that each derived value matches the hand-derived expectation (the suite fails if even one rule is wrong or missing), and that no out-of-lane behavior (test execution or deployment action) appears. Additionally, in this same update and under the update-agent gates, append the two standard sections below to this agent (identical for every agent in this file).

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

### api-tester-test-ssl-tls-enforcement — now 7/10 → 10

```
update-agent api-tester-test-ssl-tls-enforcement Specify the complete TLS-enforcement tester: given a target (https and http ports, an endpoint, the minimum TLS version), emit a JSON plan covering protocol probes (plain HTTP rejected or redirected, TLS 1.0 and 1.1 rejected, TLS 1.2 and 1.3 accepted and serving the endpoint); certificate assertions (not expired, CN/SAN match, valid chain of trust, not self-signed, and OCSP/revocation not revoked); an HSTS assertion (Strict-Transport-Security with the documented max-age and includeSubDomains/preload if required); a forward-secrecy/cipher-order assertion (the negotiated suite uses ECDHE and the server enforces its own order); the forbidden weak-cipher families RC4, DES, 3DES, EXPORT and NULL not offered; and an SNI case (correct SNI succeeds, wrong or empty behaves per contract) with wildcard scope if applicable. Emit JSON only — no connections, no TLS or HTTP requests, no network, sandbox to FORGE_WORKSPACE; a separate deterministic harness performs the handshakes and read-only GETs. In the same update and under the same gates, build this agent's lane-and-coverage safety net: a GUARDRAIL that keeps it in its lane — it emits only the JSON TLS contract above and never application-layer auth, failing closed rather than straying out of lane; GOLDEN test cases pinning the exact expected JSON plan and covering every single case the title workflow names above (five protocol probes with correct accept/reject, certificate assertions including OCSP, HSTS, forward-secrecy/cipher-order, the five forbidden weak-cipher families, SNI/wildcard) with none omitted, saved as the regression baseline at tests/golden/api-tester/test-ssl-tls-enforcement/golden.json; and UNIT tests that, per golden brief, assert the plan has exactly the required top-level keys and the exact protocol-probe expect values, that every title-named case above is present with the correct shape and count (the suite fails if even one is missing), and that no out-of-lane case appears. Additionally, in this same update and under the update-agent gates, append the two standard sections below to this agent (identical for every agent in this file).

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

### api-tester-test-bulk-operation-endpoints — now 7/10 → 10

```
update-agent api-tester-test-bulk-operation-endpoints Specify the complete bulk-operation tester: given a bulk endpoint's contract (max batch size, required fields, a valid item template, the defect selectors, the expected statuses), emit a JSON plan covering an all-valid batch (every item 2xx, DB delta equals the batch size); a mixed batch of valid items plus one missing-required and one wrong-type item (207 Multi-Status, per-item 2xx and 400 naming the offending field, DB delta equals the valid count); an all-invalid batch; an empty batch ([]) and a single-item batch; a duplicate-within-batch (one succeeds, one 409); an oversize batch (greater than max, rejected); an atomicity case if a transactional mode is documented (one invalid item rolls back the whole batch, DB delta 0); and bulk-update and bulk-delete variants if supported. Emit JSON only — no HTTP, no network, sandbox to FORGE_WORKSPACE; a separate deterministic harness materializes the batches, sends them, and queries the database. In the same update and under the same gates, build this agent's lane-and-coverage safety net: a GUARDRAIL that keeps it in its lane — it emits only the JSON bulk-operation contract above and never a case owned by api-tester-test-concurrent-request-handling, failing closed rather than straying out of lane; GOLDEN test cases pinning the exact expected JSON plan and covering every single case the title workflow names above (all-valid, mixed 207 with offending-field naming, all-invalid, empty, single-item, duplicate-within-batch, oversize reject, atomicity rollback, bulk-update, bulk-delete) with none omitted, saved as the regression baseline at tests/golden/api-tester/test-bulk-operation-endpoints/golden.json; and UNIT tests that, per golden brief, assert the plan has exactly the required keys, the [N] item template preserved, and the expected_* integers, that every title-named case above is present with the correct shape and count (the suite fails if even one is missing), and that no out-of-lane case (concurrency) appears. Additionally, in this same update and under the update-agent gates, append the two standard sections below to this agent (identical for every agent in this file).

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

### api-tester-measure-api-consumer-satisfaction — now 7/10 → 10

```
update-agent api-tester-measure-api-consumer-satisfaction Specify the complete consumer-satisfaction measurement plan (plan-only over a local fixture): emit a JSON plan defining a 90-day recipient window (distinct users with at least one API call); the survey questions including the 0–10 NPS scale, a 1–5 CSAT item with a top-2-box formula, a CES ease-of-use item, and the open-text pain-point, improvement and other questions; a 14-day collection window; the promoter/passive/detractor bands and the round(promoter_pct − detractor_pct) NPS formula; a 30 percent response-rate validity threshold; per-segment NPS and CSAT (by plan tier or call-volume band); a quarter-over-quarter trend (current versus prior with a delta); a k-means/TF-IDF top-3-themes clustering config over the combined open text; and the dashboard fields. Emit JSON only — no database, no email, no survey delivery, no clustering, no network, sandbox to FORGE_WORKSPACE; a separate deterministic harness runs the plan against the fixture and publishes the real numbers. In the same update and under the same gates, build this agent's lane-and-coverage safety net: a GUARDRAIL that keeps it in its lane — it emits only the JSON measurement-plan contract above and never executes the survey/clustering itself, failing closed rather than straying out of lane; GOLDEN test cases pinning the exact expected JSON plan and covering every single element the title workflow names above (90-day window, NPS+CSAT+CES+open-text questions verbatim, 14-day window, bands, NPS formula, 30% validity, per-segment, quarter-over-quarter trend, clustering config, dashboard fields) with none omitted, saved as the regression baseline at tests/golden/api-tester/measure-api-consumer-satisfaction/golden.json; and UNIT tests that assert the plan has exactly the required top-level keys and the exact fixed constants and question text, that every title-named element above is present with the correct shape (the suite fails if even one is missing), and that no out-of-lane behavior (executing the survey) appears. Additionally, in this same update and under the update-agent gates, append the two standard sections below to this agent (identical for every agent in this file).

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

---

**Note on scope:** every spec keeps each agent's existing emit contract (JSON plan only; a separate
harness executes) and only specifies the fuller case set plus its guardrail, golden, and unit tests,
so `update-agent` applies it under regression protection — the judged baseline can hold or improve,
never silently drop. The guardrail + unit tests enforce "stays in its lane" and "no missing a single
test case its title mentions." Case counts in the headings are illustrative coverage targets, not a
fixed surface — the orchestrator supplies the real feature and its endpoints at runtime; the scope
boundaries match the ownership map in `api-tester-update-plan.md` (scores and overlap rationale).
