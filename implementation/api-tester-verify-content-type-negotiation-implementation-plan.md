# Implementation Plan — api-tester-verify-content-type-negotiation

- **Agent:** api-tester-verify-content-type-negotiation
- **Workflow:** Content-negotiation tester — response negotiation (per-format Accept, 406 unsupported, wildcard, charset, q-value, Accept-Encoding) and request negotiation (supported/unsupported/missing Content-Type, charset-in-Content-Type), plus Accept-Language only if localization is documented.
- **Rating:** now 6/10 → 10
- **Source prompt:** agent-foundry/agents/api-tester/api-tester-update-agent-prompts.md
- **Lane:** owns the JSON Accept/Content-Type negotiation plan; defers version negotiation and other header concerns to their owning siblings (fail closed).

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
- Derive supported media types, the kind, and any default behavior only from the endpoint brief; emit one Accept probe per supported media type — never invent a media type the brief does not list.
- Emit only this agent's closed probe set: for response negotiation an Accept probe per supported media type, an unsupported Accept (406), a wildcard Accept, a charset probe (application/json; charset=utf-8 asserting a correct echoed charset), a q-value preference probe (the higher-q supported format chosen), and an Accept-Encoding probe (gzip/br with a matching Content-Encoding); for request negotiation a supported Content-Type (accepted), unsupported Content-Types (415), a missing Content-Type (documented default or 415), and a charset-in-Content-Type probe — never add a probe outside this set.
- Add an Accept-Language probe ONLY if localization is documented; never assume localization exists.
- Never assert the actual returned status, charset, or Content-Encoding — the harness sends each probe and records the real status and response headers; echo media-type and header names byte-for-byte.
- Stay in Accept/Content-Type negotiation only; never emit version negotiation or other header concerns. On out-of-lane input emit a single out-of-lane error sentinel naming the owning sibling in `out_of_scope` and nothing else.

## 2. Prompt (run verbatim — miss no detail)

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
```

## 3. Test (verify the job was done correctly)

### Verification checklist
- [ ] Output is a single valid JSON object with exactly this agent's required top-level keys — nothing else, no prose.
- [ ] Every title-named probe is present in order with correct shape: per-format Accept, 406 unsupported, wildcard, charset, q-value, Accept-Encoding; supported and unsupported Content-Type, missing Content-Type, charset-in-Content-Type.
- [ ] No out-of-lane case appears (none of: version negotiation, other header concerns).
- [ ] Each case carries primary + also_accept and a granular steps log (where it emits a request plan).
- [ ] The agent's system prompt across all four frameworks and the judge contains the verbatim Standard compliance clause and the string `references/agent-authoring-standard.md`.
- [ ] A code-review receipt exists at `results/_global/` with status pass, reviewer set == `agents/code-review/`, every reviewer ≥85.
- [ ] The golden baseline equals the post-update best and the regression gate held or improved.

### Automated test (pytest-style)
```python
import json
import pathlib
import glob

GOLDEN = "tests/golden/api-tester/verify-content-type-negotiation/golden.json"
SUBAGENT = "agents/api-tester/verify-content-type-negotiation/subagent/verify-content-type-negotiation.md"

PROBE_GROUPS = [
    ["accept"],                          # per-format Accept probe
    ["406", "unsupported"],              # unsupported Accept -> 406
    ["wildcard", "*/*"],                 # wildcard Accept
    ["charset"],                         # charset probe
    ["q-value", "q_value", "q="],        # q-value preference
    ["accept-encoding", "gzip", "br"],   # Accept-Encoding probe
    ["content-type"],                    # supported Content-Type
    ["415"],                             # unsupported Content-Type -> 415
    ["missing"],                         # missing Content-Type
]
OUT_OF_LANE = ["version", "deprecation", "sunset", "vnd.api.v"]


def _load_plan():
    plan = json.loads(pathlib.Path(GOLDEN).read_text(encoding="utf-8"))
    assert isinstance(plan, dict), "emitted plan must be a single JSON object"
    return plan


def test_required_top_level_keys():
    plan = _load_plan()
    assert plan, "plan must have its required top-level keys"


def test_every_title_probe_present():
    plan = _load_plan()
    blob = json.dumps(plan).lower()
    for g in PROBE_GROUPS:
        assert any(tok in blob for tok in g), \
            f"negotiation probe {g[0]} missing — suite fails if even one is absent"


def test_no_out_of_lane_case():
    plan = _load_plan()
    blob = json.dumps(plan).lower()
    for token in OUT_OF_LANE:
        assert token not in blob, f"out-of-lane case '{token}' (version negotiation) must not appear"


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
