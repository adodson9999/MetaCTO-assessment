# Implementation Plan — api-tester-test-long-polling-support

- **Agent:** api-tester-test-long-polling-support
- **Workflow:** Complete long-polling tester — given a channel's contract (poll/trigger paths, poll timeout, expected event type), plan no-event / event / multiple-events / resume-after-gap / concurrent-pollers / connection-drop cases.
- **Rating:** now 6/10 → 10
- **Source prompt:** agent-foundry/agents/api-tester/api-tester-update-agent-prompts.md
- **Lane:** owns the long-polling JSON plan contract (poll/trigger lifecycle: no-event 204-empty, event 200-within-2s, multiple-events queued, resume-after-gap via Last-Event-ID, concurrent-pollers, connection-drop); defers broker/topic semantics to api-tester-test-event-driven-api-triggers.

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
- Compute `client_max_time` strictly as `poll_timeout + 5` from the supplied channel contract; never invent or round a different window.
- Echo the channel's poll path, trigger path, and `event_type` byte-for-byte; never substitute a synthesized event type or path.
- Never connect, open a socket, trigger an event, or hit the network — the separate harness opens connections, triggers events, and records responses.
- Emit only the long-polling lifecycle cases; never emit a broker/topic-semantics case (those belong to api-tester-test-event-driven-api-triggers).
- Reproduce the documented cursor / `Last-Event-ID` exactly for the resume-after-gap case; do not fabricate a cursor value or delivery timing.

## 2. Prompt (run verbatim — miss no detail)

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
```

## 3. Test (verify the job was done correctly)

### Verification checklist
- [ ] Output is a single valid JSON object with exactly this agent's required top-level keys — nothing else, no prose.
- [ ] Every title-named case/field is present with correct shape and count: no-event 204-empty, event 200-within-2s correct-type, multiple-events queued, resume-after-gap via Last-Event-ID, concurrent-pollers, connection-drop; plus `client_max_time = poll_timeout + 5`.
- [ ] No out-of-lane case appears (no broker/topic semantics — owned by api-tester-test-event-driven-api-triggers); the agent makes no connection/trigger/socket/network call.
- [ ] Each case carries primary + also_accept and a granular steps log.
- [ ] The agent's system prompt across all four frameworks and the judge contains the verbatim Standard compliance clause and the string `references/agent-authoring-standard.md`.
- [ ] A code-review receipt exists at `results/_global/` with status pass, reviewer set == `agents/code-review/`, every reviewer ≥85.
- [ ] The golden baseline equals the post-update best and the regression gate held or improved.

### Automated test (pytest-style)
```python
import json
import pathlib
import glob

AGENT = "test-long-polling-support"
TITLE_CASES = [
    "no_event", "event", "multiple_events",
    "resume_after_gap", "concurrent_pollers", "connection_drop",
]
OUT_OF_LANE = ["broker", "topic"]  # owned by test-event-driven-api-triggers


def _load_emitted_plan():
    # Emitted plan for a representative channel-contract brief.
    path = pathlib.Path(
        f"tests/golden/api-tester/{AGENT}/golden.json"
    )
    assert path.exists(), f"missing emitted/golden plan for {AGENT}"
    return json.loads(path.read_text(encoding="utf-8"))


def test_single_json_object_required_keys():
    plan = _load_emitted_plan()
    assert isinstance(plan, dict), "plan must be a single JSON object"
    for key in ("channel", "client_max_time", "cases"):
        assert key in plan, f"missing required top-level key: {key}"


def test_client_max_time_equals_poll_timeout_plus_5():
    plan = _load_emitted_plan()
    poll_timeout = plan["channel"]["poll_timeout"]
    assert plan["client_max_time"] == poll_timeout + 5, (
        f"client_max_time must equal poll_timeout + 5; "
        f"got {plan['client_max_time']} vs {poll_timeout} + 5"
    )


def test_every_title_case_present():
    plan = _load_emitted_plan()
    names = {c.get("name") or c.get("case") for c in plan["cases"]}
    for case in TITLE_CASES:
        assert case in names, f"missing title-named case: {case}"
    assert len(plan["cases"]) == len(TITLE_CASES), (
        f"expected exactly {len(TITLE_CASES)} cases, got {len(plan['cases'])}"
    )


def test_no_out_of_lane_case():
    plan = _load_emitted_plan()
    blob = json.dumps(plan).lower()
    for token in OUT_OF_LANE:
        for c in plan["cases"]:
            cid = (c.get("name") or c.get("case") or "").lower()
            assert token not in cid, (
                f"out-of-lane case '{cid}' contains '{token}' "
                f"(owned by test-event-driven-api-triggers)"
            )


def test_each_case_has_expectation_and_steps():
    plan = _load_emitted_plan()
    for c in plan["cases"]:
        assert "primary" in c, f"case {c} missing primary expectation"
        assert "also_accept" in c, f"case {c} missing also_accept"
        assert isinstance(c.get("steps"), list) and c["steps"], (
            f"case {c} missing granular steps log"
        )


def test_subagent_prompt_references_standard():
    prompt = pathlib.Path(
        f"agents/api-tester/{AGENT}/subagent/{AGENT}.md"
    ).read_text(encoding="utf-8")
    assert "references/agent-authoring-standard.md" in prompt, (
        "agent prompt must reference the Universal Agent Authoring & Update Standard"
    )


def test_code_review_receipt_pass_min_85():
    receipts = glob.glob("results/_global/*.json")
    assert receipts, "no code-review receipt found in results/_global/"
    matched = []
    for r in receipts:
        data = json.loads(pathlib.Path(r).read_text(encoding="utf-8"))
        if AGENT in json.dumps(data):
            matched.append(data)
    assert matched, f"no code-review receipt referencing {AGENT}"
    for data in matched:
        assert data.get("status") == "pass", f"receipt status not pass: {data}"
        ratings = [rv["rating"] for rv in data.get("reviewers", [])]
        assert ratings, "receipt has no reviewer ratings"
        assert min(ratings) >= 85, f"a reviewer scored below 85: {ratings}"
```
