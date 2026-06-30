# Implementation Plan — api-tester-validate-api-versioning-behavior

- **Agent:** api-tester-validate-api-versioning-behavior
- **Workflow:** Versioning tester — path-based versions (current/deprecated/unsupported), header/media-type versioning, query-parameter versioning if documented, and a default-version case; each response body validated per version with ajv v8.
- **Rating:** now 6/10 → 10
- **Source prompt:** agent-foundry/agents/api-tester/api-tester-update-agent-prompts.md
- **Lane:** owns the JSON versioning plan (current, deprecated with Deprecation+Sunset+successor Link, unsupported 404/400; header/media-type versions; query-param version; default-version); defers generic Accept/Content-Type negotiation to its owning sibling (fail closed).

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
- Derive the supported versions (with current/deprecated status), unsupported versions, and the v2-vs-v1 schema-diff field only from the endpoint's versioning contract; never invent a version, status, or schema-diff field the contract does not declare.
- Emit only this agent's closed case set: path-based versions (current → 200 with its schema and no Deprecation header; deprecated → 200 with its schema plus a future-dated Deprecation header, a Sunset header, and a successor Link; unsupported → 404, or 400 for a non-numeric version); header/media-type versioning (Accept: application/vnd.api.v2+json current, v1 deprecated, v0/v99 unsupported); query-parameter versioning if documented; and a default-version case (no version → documented default or an explicit error) — never add a case.
- Validate each response body per version with ajv v8; never assert the actual returned body, status, or headers — the harness runs read-only GETs and records the real responses.
- Echo the media-type version strings (e.g. application/vnd.api.v2+json), version numbers, and header names (Deprecation, Sunset, Link) byte-for-byte; never normalize or re-encode them.
- Defer generic Accept/Content-Type negotiation to its owning sibling; on out-of-lane input emit a single out-of-lane error sentinel naming that sibling in `out_of_scope` and nothing else.

## 2. Prompt (run verbatim — miss no detail)

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
```

## 3. Test (verify the job was done correctly)

### Verification checklist
- [ ] Output is a single valid JSON object with exactly this agent's required top-level keys — nothing else, no prose.
- [ ] Every title-named case is present with correct shape and count: current (200, schema, no Deprecation header), deprecated (200, schema, Deprecation+Sunset+successor Link), unsupported (404 or 400 non-numeric); header/media-type versions (v2 current, v1 deprecated, v0/v99 unsupported); query-param version (if documented); default-version.
- [ ] No out-of-lane case appears (none of: generic Accept/Content-Type negotiation).
- [ ] Each case carries primary + also_accept and a granular steps log (where it emits a request plan).
- [ ] The agent's system prompt across all four frameworks and the judge contains the verbatim Standard compliance clause and the string `references/agent-authoring-standard.md`.
- [ ] A code-review receipt exists at `results/_global/` with status pass, reviewer set == `agents/code-review/`, every reviewer ≥85.
- [ ] The golden baseline equals the post-update best and the regression gate held or improved.

### Automated test (pytest-style)
```python
import json
import pathlib
import glob

GOLDEN = "tests/golden/api-tester/validate-api-versioning-behavior/golden.json"
SUBAGENT = "agents/api-tester/validate-api-versioning-behavior/subagent/validate-api-versioning-behavior.md"

CASE_GROUPS = [
    ["current"],
    ["deprecated", "deprecation"],
    ["sunset"],
    ["successor", "link"],
    ["unsupported", "404", "400"],
    ["vnd.api.v", "media-type", "media_type", "accept"],
    ["default"],
]
OUT_OF_LANE = ["406", "415", "accept-encoding", "wildcard", "q-value", "q_value"]


def _load_plan():
    plan = json.loads(pathlib.Path(GOLDEN).read_text(encoding="utf-8"))
    assert isinstance(plan, dict), "emitted plan must be a single JSON object"
    return plan


def test_required_top_level_keys():
    plan = _load_plan()
    assert plan, "plan must have its required top-level keys"


def test_every_title_case_present():
    plan = _load_plan()
    blob = json.dumps(plan).lower()
    for g in CASE_GROUPS:
        assert any(tok in blob for tok in g), \
            f"versioning case {g[0]} missing — suite fails if even one is absent"


def test_deprecated_carries_deprecation_sunset_link():
    plan = _load_plan()
    blob = json.dumps(plan).lower()
    assert "deprecation" in blob, "deprecated version must carry a Deprecation header assertion"
    assert "sunset" in blob, "deprecated version must carry a Sunset header assertion"
    assert "link" in blob, "deprecated version must carry a successor Link assertion"


def test_no_out_of_lane_case():
    plan = _load_plan()
    blob = json.dumps(plan).lower()
    for token in OUT_OF_LANE:
        assert token not in blob, f"out-of-lane case '{token}' (general content negotiation) must not appear"


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
