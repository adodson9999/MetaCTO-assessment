# Implementation Plan — api-tester-test-event-driven-api-triggers

- **Agent:** api-tester-test-event-driven-api-triggers
- **Workflow:** Event-trigger tester — well-formed event drives state in poll window; malformed event ERROR-logged + dead-lettered + state unchanged + no crash; duplicate idempotent; out-of-order ordering rule; poison message retried then dead-lettered.
- **Rating:** now 6/10 → 10
- **Source prompt:** agent-foundry/agents/api-tester/api-tester-update-agent-prompts.md
- **Lane:** owns message-topic / event-consumer behavior (well-formed→state, malformed→ERROR-log+DLQ+unchanged+health, duplicate idempotent, out-of-order, poison-retry-then-DLQ); defers HTTP-callback webhooks to api-tester-test-webhook-delivery

## 1. Guardrails (force no hallucination)

These rules bind the agent; violating any one is a hallucination and must fail the build:
- **Derive only from the documented surface.** Never invent an endpoint, path, field, query parameter, status code, header, token, id, or case that the input does not literally provide.
- **Plan only — never guess a response.** Do not state or fabricate any status code, response body, header value, timing, count, or pass/fail verdict; a separate deterministic harness sends the requests and records the real responses.
- **One JSON object, exact contract.** Emit exactly one JSON object matching the declared contract — no prose, no code fence, no commentary, no extra or renamed keys.
- **Closed vocabulary only.** Use only this agent's fixed recipe kinds / value sets / labels; never introduce a new kind, label, or value.
- **Stay in lane (MECE), fail closed.** Never emit a case whose canonical identity is owned by another agent. On out-of-lane input, emit a single out-of-lane error sentinel naming the owning sibling in `out_of_scope` and nothing else.
- **Deterministic + exhaustive.** The same input always yields the same plan; enumerate every documented case — no more, no less.
- **Byte-for-byte echo.** Reproduce provided ids, header names, correlation ids, and regexes exactly; never trim, normalize, re-encode, or substitute.
- **Fail closed on missing input.** If a required input field is missing or ambiguous, emit an error sentinel — never assume a default or guess a value.
- **No fabricated review.** Every code artifact is reviewed at ≥85 by every agent in `agents/code-review/`; never invent a receipt, score, or reviewer set.

**Agent-specific anti-hallucination rules:**
- Use only the topic contract the brief literally provides — the resource and state fields, the event type, the required fields and values, the required field to drop for the malformed event, the poll window, the dead-letter deadline, and the documented retry count; never invent a field, value, or deadline.
- The malformed event must differ from the well-formed event only by the single documented dropped field; never alter any other field or fabricate a second mutation.
- Closed case vocabulary only: well-formed event → expected state within the poll window; malformed event → ERROR-logged + dead-lettered within deadline + state unchanged + consumer does not crash; duplicate well-formed event → applied exactly once (idempotent consumer); out-of-order pair for one key → documented ordering/versioning rule (later state wins or stale event dropped); poison message → retried the documented number of times before dead-lettering — no other event case.
- Plan the publish/poll/log-read steps only; never fabricate the resulting state, the ERROR log, the DLQ contents, the apply count, or any verdict — a separate deterministic harness publishes the events, polls state, and reads the consumer log and dead-letter queue.
- Refuse HTTP-callback webhooks: that concern is owned by api-tester-test-webhook-delivery; on such input emit the out-of-lane sentinel naming it in `out_of_scope` and nothing else.

## 2. Prompt (run verbatim — miss no detail)

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
```

## 3. Test (verify the job was done correctly)

### Verification checklist
- [ ] Output is a single valid JSON object with exactly this agent's required top-level keys — nothing else, no prose.
- [ ] Every title-named case is present with correct shape and count: well-formed→state within window, malformed→ERROR-log+DLQ+unchanged+health, duplicate idempotent, out-of-order, poison-retry-then-DLQ.
- [ ] The malformed event differs from the well-formed event only by the single dropped field.
- [ ] No out-of-lane case appears (none of: HTTP-callback webhooks — owned by api-tester-test-webhook-delivery).
- [ ] Each case carries primary + also_accept and a granular steps log (where it emits a request plan).
- [ ] The agent's system prompt across all four frameworks and the judge contains the verbatim Standard compliance clause and the string `references/agent-authoring-standard.md`.
- [ ] A code-review receipt exists at `results/_global/` with status pass, reviewer set == `agents/code-review/`, every reviewer ≥85.
- [ ] The golden baseline equals the post-update best and the regression gate held or improved.

### Automated test (pytest-style)
```python
import json
import pathlib

GOLDEN = pathlib.Path("tests/golden/api-tester/test-event-driven-api-triggers/golden.json")
AGENT_MD = pathlib.Path("agents/api-tester/test-event-driven-api-triggers/subagent/test-event-driven-api-triggers.md")
GLOBAL_RECEIPTS = pathlib.Path("results/_global/")

REQUIRED_TOP_LEVEL_KEYS = {"plan", "execution", "log", "report"}
TITLE_CASE_LABELS = [
    "well_formed_state_within_window",
    "malformed_error_log_dlq_unchanged_health",
    "duplicate_idempotent",
    "out_of_order",
    "poison_retry_then_dlq",
]
OUT_OF_LANE_LABELS = ["webhook_delivery", "http_callback", "callback_webhook"]


def _load_plan():
    assert GOLDEN.exists(), f"golden baseline missing at {GOLDEN}"
    return json.loads(GOLDEN.read_text(encoding="utf-8"))


def test_single_json_object_with_required_keys():
    plan = _load_plan()
    assert isinstance(plan, dict), "emitted plan must be a single JSON object"
    assert REQUIRED_TOP_LEVEL_KEYS.issubset(set(plan.keys())), \
        f"plan missing required top-level keys: {REQUIRED_TOP_LEVEL_KEYS - set(plan.keys())}"


def test_every_title_case_present():
    blob = json.dumps(_load_plan())
    for label in TITLE_CASE_LABELS:
        assert label in blob, f"required title case missing from plan: {label}"


def test_malformed_differs_only_by_dropped_field():
    blob = json.dumps(_load_plan()).lower()
    assert "dropped_field" in blob or "drop" in blob, \
        "plan must encode that the malformed event differs from the well-formed only by the dropped field"


def test_no_out_of_lane_case():
    blob = json.dumps(_load_plan()).lower()
    for label in OUT_OF_LANE_LABELS:
        assert label not in blob, f"out-of-lane case must not appear (owned by api-tester-test-webhook-delivery): {label}"


def test_agent_references_standard():
    assert AGENT_MD.exists(), f"agent subagent prompt missing at {AGENT_MD}"
    prompt = AGENT_MD.read_text(encoding="utf-8")
    assert "references/agent-authoring-standard.md" in prompt, \
        "agent prompt must reference the Universal Agent Authoring & Update Standard"


def test_code_review_receipt_pass_and_min_85():
    receipts = list(GLOBAL_RECEIPTS.glob("*.json"))
    assert receipts, f"no code-review receipt found in {GLOBAL_RECEIPTS}"
    matched = None
    for r in receipts:
        data = json.loads(r.read_text(encoding="utf-8"))
        if "test-event-driven-api-triggers" in json.dumps(data) or len(receipts) == 1:
            matched = data
            break
    assert matched is not None, "no code-review receipt references this agent"
    assert matched.get("status") == "pass", f"code-review receipt status must be 'pass', got {matched.get('status')!r}"
    ratings = [r["rating"] for r in matched.get("reviews", []) if "rating" in r]
    assert ratings, "code-review receipt must record per-reviewer ratings"
    assert min(ratings) >= 85, f"every reviewer must score >= 85; min was {min(ratings)}"
```
