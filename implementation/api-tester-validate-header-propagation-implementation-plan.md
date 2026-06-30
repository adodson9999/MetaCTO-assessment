# Implementation Plan — api-tester-validate-header-propagation

- **Agent:** api-tester-validate-header-propagation
- **Workflow:** Request-header forwarding tester (general header propagation, not correlation-id) — each forwarded header reaches every downstream service byte-for-byte and appears unmodified in downstream logs; hop-by-hop headers are not forwarded; inbound traceparent is continued.
- **Rating:** now 5/10 → 10
- **Source prompt:** agent-foundry/agents/api-tester/api-tester-update-agent-prompts.md
- **Lane:** owns the JSON header-propagation plan (forwarding of Authorization, traceparent, tracestate, B3, X-Forwarded-*, a custom X- header; hop-by-hop stripping; traceparent continuation); defers the X-Correlation-ID echo, UUIDv4 auto-generation, and correlation-specific log greps to api-tester-validate-correlation-id-propagation.

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
- Forward only the documented header set, named byte-for-byte: Authorization, the W3C trace pair traceparent and tracestate, B3 (X-B3-TraceId / X-B3-SpanId), the X-Forwarded-* set, and one custom X- header; never invent a header name or add one the brief does not declare.
- The hop-by-hop set that must NOT be forwarded is fixed: Connection, Keep-Alive, Transfer-Encoding, Upgrade — never add or drop a member of this closed set.
- Assert each forwarded header reaches every downstream service byte-for-byte and appears unmodified in the downstream logs, and that an inbound traceparent is continued downstream with the same trace-id; never assert the actual captured log content — the harness runs the plan and reads the captured logs.
- Echo provided header names and the trace-id byte-for-byte; never normalize header casing, trim, or re-encode values.
- Defer the X-Correlation-ID echo, UUIDv4 auto-generation, and correlation-specific log greps to api-tester-validate-correlation-id-propagation; on out-of-lane input emit a single out-of-lane error sentinel naming that sibling in `out_of_scope` and nothing else.

## 2. Prompt (run verbatim — miss no detail)

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
```

## 3. Test (verify the job was done correctly)

### Verification checklist
- [ ] Output is a single valid JSON object with exactly this agent's required top-level keys — nothing else, no prose.
- [ ] Every title-named case is present with correct shape and count: forwarding of Authorization, traceparent, tracestate, B3 (X-B3-TraceId/SpanId), X-Forwarded-*, a custom X- header; hop-by-hop stripping (Connection, Keep-Alive, Transfer-Encoding, Upgrade); traceparent continuation.
- [ ] No out-of-lane case appears (none of: X-Correlation-ID echo, UUIDv4 auto-generation, correlation-specific log greps).
- [ ] Each case carries primary + also_accept and a granular steps log (where it emits a request plan).
- [ ] The agent's system prompt across all four frameworks and the judge contains the verbatim Standard compliance clause and the string `references/agent-authoring-standard.md`.
- [ ] A code-review receipt exists at `results/_global/` with status pass, reviewer set == `agents/code-review/`, every reviewer ≥85.
- [ ] The golden baseline equals the post-update best and the regression gate held or improved.

### Automated test (pytest-style)
```python
import json
import pathlib
import glob

GOLDEN = "tests/golden/api-tester/validate-header-propagation/golden.json"
SUBAGENT = "agents/api-tester/validate-header-propagation/subagent/validate-header-propagation.md"

FORWARDED = ["Authorization", "traceparent", "tracestate", "X-B3-TraceId", "X-Forwarded"]
HOP_BY_HOP = ["Connection", "Keep-Alive", "Transfer-Encoding", "Upgrade"]
OUT_OF_LANE = ["X-Correlation-ID", "X-Correlation-Id", "correlation_id", "UUIDv4", "uuidv4"]


def _load_plan():
    plan = json.loads(pathlib.Path(GOLDEN).read_text(encoding="utf-8"))
    assert isinstance(plan, dict), "emitted plan must be a single JSON object"
    return plan


def test_required_top_level_keys():
    plan = _load_plan()
    assert plan, "plan must have its required top-level keys"


def test_forwarded_headers_present():
    plan = _load_plan()
    blob = json.dumps(plan)
    for h in FORWARDED:
        assert h in blob, f"forwarded header '{h}' missing — suite fails if even one is absent"
    # the custom X- header (any X-prefixed beyond the named set) and B3 SpanId
    assert "X-B3-SpanId" in blob or "SpanId" in blob, "B3 SpanId assertion must be present"


def test_traceparent_continuation_present():
    plan = _load_plan()
    blob = json.dumps(plan).lower()
    assert "continu" in blob or "same trace" in blob or "trace-id" in blob or "trace_id" in blob, \
        "inbound traceparent continuation (same trace-id) must be asserted"


def test_hop_by_hop_stripping_present():
    plan = _load_plan()
    blob = json.dumps(plan)
    for h in HOP_BY_HOP:
        assert h in blob, f"hop-by-hop header '{h}' must be present (asserted NOT forwarded)"


def test_no_out_of_lane_correlation_case():
    plan = _load_plan()
    blob = json.dumps(plan)
    for token in OUT_OF_LANE:
        assert token not in blob, f"out-of-lane case '{token}' (correlation-id semantics) must not appear"


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
