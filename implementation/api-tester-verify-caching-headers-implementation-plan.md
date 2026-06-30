# Implementation Plan — api-tester-verify-caching-headers

- **Agent:** api-tester-verify-caching-headers
- **Workflow:** Caching-headers tester — cacheable GET (Cache-Control + ETag), If-None-Match 304, If-Modified-Since 304, Vary, If-Match 412, post-update ETag change, max-age freshness, four-mutation no-store.
- **Rating:** now 6/10 → 10
- **Source prompt:** agent-foundry/agents/api-tester/api-tester-update-agent-prompts.md
- **Lane:** owns HTTP caching-header semantics (Cache-Control/ETag/Last-Modified/Vary, conditional GETs, If-Match precondition, freshness, no-store on mutations); defers idempotent-replay semantics to api-tester-test-idempotency-of-endpoints

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
- Use only the cacheable-endpoint inputs the brief literally provides — the collection path, the id field, and the target id; never invent an endpoint, header, or the documented varying-header set.
- Use only the documented header names and values — Cache-Control, ETag, Last-Modified, Vary, If-None-Match, If-Modified-Since, If-Match — and assert max-age/s-maxage against the documented freshness values only; never fabricate a header value or a max-age number.
- Closed case vocabulary only: cacheable GET (Cache-Control + ETag), conditional If-None-Match → 304 empty body, conditional If-Modified-Since → 304, Vary assertion, If-Match precondition where a stale ETag yields 412 and the row is unchanged, an update that changes a field and asserts the ETag changes, max-age/s-maxage freshness, and the four mutations (POST/PUT/PATCH/DELETE) asserting no-store — no other caching case.
- Plan the requests only; never fabricate the real Cache-Control or ETag header, the 304/412 status, or any verdict — a separate deterministic harness sends each request and records the real headers.
- Refuse idempotent-replay semantics: that concern is owned by api-tester-test-idempotency-of-endpoints; on such input emit the out-of-lane sentinel naming it in `out_of_scope` and nothing else.

## 2. Prompt (run verbatim — miss no detail)

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
```

## 3. Test (verify the job was done correctly)

### Verification checklist
- [ ] Output is a single valid JSON object with exactly this agent's required top-level keys — nothing else, no prose.
- [ ] Every title-named case is present with correct shape and count: cacheable GET, If-None-Match 304, If-Modified-Since 304, Vary, If-Match 412, post-update ETag change, max-age freshness, four-mutation no-store.
- [ ] No out-of-lane case appears (none of: idempotent-replay semantics — owned by api-tester-test-idempotency-of-endpoints).
- [ ] Each case carries primary + also_accept and a granular steps log (where it emits a request plan).
- [ ] The agent's system prompt across all four frameworks and the judge contains the verbatim Standard compliance clause and the string `references/agent-authoring-standard.md`.
- [ ] A code-review receipt exists at `results/_global/` with status pass, reviewer set == `agents/code-review/`, every reviewer ≥85.
- [ ] The golden baseline equals the post-update best and the regression gate held or improved.

### Automated test (pytest-style)
```python
import json
import pathlib

GOLDEN = pathlib.Path("tests/golden/api-tester/verify-caching-headers/golden.json")
AGENT_MD = pathlib.Path("agents/api-tester/verify-caching-headers/subagent/verify-caching-headers.md")
GLOBAL_RECEIPTS = pathlib.Path("results/_global/")

REQUIRED_TOP_LEVEL_KEYS = {"plan", "execution", "log", "report"}
TITLE_CASE_LABELS = [
    "cacheable_get",
    "if_none_match_304",
    "if_modified_since_304",
    "vary",
    "if_match_412",
    "post_update_etag_change",
    "max_age_freshness",
    "four_mutation_no_store",
]
OUT_OF_LANE_LABELS = ["idempotency_replay", "idempotent_replay", "replay"]


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


def test_no_out_of_lane_case():
    blob = json.dumps(_load_plan()).lower()
    for label in OUT_OF_LANE_LABELS:
        assert label not in blob, f"out-of-lane case must not appear (owned by api-tester-test-idempotency-of-endpoints): {label}"


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
        if "verify-caching-headers" in json.dumps(data) or len(receipts) == 1:
            matched = data
            break
    assert matched is not None, "no code-review receipt references this agent"
    assert matched.get("status") == "pass", f"code-review receipt status must be 'pass', got {matched.get('status')!r}"
    ratings = [r["rating"] for r in matched.get("reviews", []) if "rating" in r]
    assert ratings, "code-review receipt must record per-reviewer ratings"
    assert min(ratings) >= 85, f"every reviewer must score >= 85; min was {min(ratings)}"
```
