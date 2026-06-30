# Implementation Plan — api-tester-verify-audit-log-generation

- **Agent:** api-tester-verify-audit-log-generation
- **Workflow:** Audit-log tester — perform create/update/delete operations as the provided test user and query the audit log, asserting create/update/delete entries with the required fields, a read audit, a failed-action audit, login/logout audits, before/after capture on the update entry, and audit immutability.
- **Rating:** now 6/10 → 10
- **Source prompt:** agent-foundry/agents/api-tester/api-tester-update-agent-prompts.md
- **Lane:** owns the JSON audit-log request-and-query plan (CRUD audit entries with the required fields, read audit, failed-action audit, login/logout audits, before/after capture, audit immutability) for the collection supplied at runtime; defers correlation/trace log propagation to api-tester-validate-correlation-id-propagation.

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
- Use only the inputs the brief literally provides — the collection path, the id field, and the test user supplied at runtime; never invent an endpoint, audit field, or user.
- Assert exactly the documented required audit fields — user_id, action_type, resource_id, timestamp, ip_address — within the documented time window and tolerance; never add, rename, or drop a required field.
- Closed case vocabulary only: create/update/delete entries (three) with the required fields; a read entry if sensitive GETs are audited; a failed-action entry for a denied or unauthenticated attempt; auth-event entries for login and logout; before/after values captured on the update entry; and immutability (an API attempt to modify or delete an audit entry is rejected) — no other audit case.
- Plan the operations and the audit-log query only; never fabricate the audit entries, their field values, the timestamps, or any verdict — a separate deterministic harness authenticates, runs the operations, captures the log, and queries it.
- Refuse correlation/trace log propagation: that concern is owned by api-tester-validate-correlation-id-propagation; on such input emit the out-of-lane sentinel naming it in `out_of_scope` and nothing else.

## 2. Prompt (run verbatim — miss no detail)

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

## 3. Test (verify the job was done correctly)

### Verification checklist
- [ ] Single valid JSON object with exactly the required top-level keys and audit_query fields — no prose.
- [ ] Every title-named case present (by ROLE): create/update/delete entries with the required fields, read audit, failed-action audit, login/logout audits, before/after on update, immutability.
- [ ] No out-of-lane case appears (none of: correlation/trace log propagation — owned by api-tester-validate-correlation-id-propagation).
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
GOLDEN = "tests/golden/api-tester/verify-audit-log-generation/golden.json"
SUBAGENT = "agents/api-tester/verify-audit-log-generation/subagent/verify-audit-log-generation.md"

REQUIRED_AUDIT_FIELDS = ["user_id", "action_type", "resource_id", "timestamp", "ip_address"]
# title cases named by role — no specific URL/feature
TITLE_CASE_LABELS = [
    "create_entry",
    "update_entry",
    "delete_entry",
    "read_audit",
    "failed_action_audit",
    "login_audit",
    "logout_audit",
    "before_after_on_update",
    "immutability",
]
OUT_OF_LANE_LABELS = ["correlation_id", "trace_propagation", "traceparent"]  # owned by validate-correlation-id-propagation

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
    blob = json.dumps(plan).lower()
    assert "audit_query" in blob, "plan must carry the audit_query fields"


def test_required_audit_fields_present():
    blob = json.dumps(_load_plan())
    for field in REQUIRED_AUDIT_FIELDS:
        assert field in blob, f"audit_query must assert the required audit field: {field}"


def test_every_title_case_present():
    blob = json.dumps(_load_plan())
    for label in TITLE_CASE_LABELS:
        assert label in blob, f"required title case missing from plan: {label}"


def test_no_out_of_lane_case():
    blob = json.dumps(_load_plan()).lower()
    for label in OUT_OF_LANE_LABELS:
        assert label not in blob, \
            f"out-of-lane case must not appear (owned by validate-correlation-id-propagation): {label}"


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
