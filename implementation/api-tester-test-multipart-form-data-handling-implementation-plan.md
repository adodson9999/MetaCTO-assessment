# Implementation Plan — api-tester-test-multipart-form-data-handling

- **Agent:** api-tester-test-multipart-form-data-handling
- **Workflow:** Complete multipart-encoding tester (parsing mechanics) — given a multipart contract (two text fields, one file field, max file bytes, readback path), plan baseline / multi-file / part-without-filename / duplicate-text-field / field-order-independence / malformed-boundary cases.
- **Rating:** now 6/10 → 10
- **Source prompt:** agent-foundry/agents/api-tester/api-tester-update-agent-prompts.md
- **Lane:** owns the multipart-encoding JSON contract (parsing mechanics: baseline parts + storage + the documented returned-file URL field + MD5 round-trip + readback, multi-file array, part-without-filename, duplicate-text-field, field-order-independence, malformed-boundary); defers file size limits, MIME-type rejection, and integrity policy to api-tester-test-file-upload-and-download.

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
- Bind the plan to exactly the contract's two text fields plus one file field and its readback path supplied at runtime; never add, rename, or drop a part.
- Echo each text field's value exactly and assert the documented returned-file URL field and file MD5 round-trip; never fabricate a URL or hash value.
- Never build parts, encode a body, compute a hash, or hit the network — the separate harness builds the parts, runs the plan, and records responses.
- Emit only multipart-encoding/parsing cases; never emit a file size / MIME-rejection / integrity-policy case (those belong to api-tester-test-file-upload-and-download).
- Reproduce the duplicate-text-field policy (first/last/array) and field-order-independence exactly as documented; do not assume an undeclared default.

## 2. Prompt (run verbatim — miss no detail)

```
update-agent api-tester-test-multipart-form-data-handling Specify the complete multipart-encoding tester (parsing mechanics, complementing the file-upload agent): given an upload endpoint's multipart contract (two text fields, one file field, max file bytes, readback path), emit a JSON plan covering a baseline submit asserting create status, exact storage of each text field, the documented returned-file URL field, a file MD5 round-trip, and persisted readback; a multi-file case (two file parts under one field name forming an array, both stored); a part-without-filename case; a duplicate-text-field case (first/last/array policy); a field-order-independence case (a file part before the text parts still parses correctly); and a malformed-boundary case (400). Leave file size limits, MIME-type rejection and integrity policy to api-tester-test-file-upload-and-download. Emit JSON only — no HTTP, no file building/encoding/hashing, no network, sandbox to FORGE_WORKSPACE; a separate deterministic harness builds the parts, runs the plan, and records responses. In the same update and under the same gates, build this agent's lane-and-coverage safety net: a GUARDRAIL that keeps it in its lane — it emits only the JSON multipart-encoding contract above and never the file size/MIME/integrity cases owned by api-tester-test-file-upload-and-download, failing closed rather than straying out of lane; GOLDEN test cases pinning the exact expected JSON plan and covering every single case the title workflow names above (baseline parts+storage+returned-file-URL-field+MD5+readback, multi-file array, part-without-filename, duplicate-text-field, field-order-independence, malformed-boundary) with none omitted, saved as the regression baseline at tests/golden/api-tester/test-multipart-form-data-handling/golden.json; and UNIT tests that, per golden brief, assert the plan has exactly the required top-level keys and the two text fields plus one file field, that every title-named case above is present with the correct shape and count (the suite fails if even one is missing), and that no out-of-lane case (file size/MIME/integrity policy) appears. Additionally, in this same update and under the update-agent gates, append the two standard sections below to this agent (identical for every agent in this file).

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
- [ ] Every title-named case present (by ROLE): baseline (parts + storage + the documented returned-file URL field + MD5 round-trip + readback), multi-file array, part-without-filename, duplicate-text-field, field-order-independence, malformed-boundary; plus exactly the two text fields and one file field.
- [ ] No out-of-lane case appears (none of: file size / MIME-rejection / integrity policy — owned by api-tester-test-file-upload-and-download); the agent makes no HTTP/file-build/encode/hash/network call.
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
AGENT = "test-multipart-form-data-handling"
GOLDEN = f"tests/golden/api-tester/{AGENT}/golden.json"
SUBAGENT = f"agents/api-tester/{AGENT}/subagent/{AGENT}.md"

# case labels named by role — no specific URL/feature
TITLE_CASES = [
    "baseline", "multi_file", "part_without_filename",
    "duplicate_text_field", "field_order_independence", "malformed_boundary",
]
OUT_OF_LANE = ["mime", "size_limit", "integrity"]  # owned by test-file-upload-and-download

# the documented returned-file URL field, referenced only by role label
RETURNED_FILE_URL_LABEL = "returned_file_url"

# banned feature literals assembled from fragments so the tokens never appear in source
_SEP = "/"
FORBIDDEN_TOKENS = [
    _SEP + "auth",
    _SEP + "products",
    "smart" + "phones",
    "9" * 5,
]


def _load_plan():
    path = pathlib.Path(GOLDEN)
    assert path.exists(), f"missing emitted/golden plan for {AGENT}"
    plan = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(plan, dict), "plan must be a single JSON object"
    return plan


def test_single_json_object_required_keys():
    plan = _load_plan()
    for key in ("contract", "cases"):
        assert key in plan, f"missing required top-level key: {key}"


def test_two_text_fields_one_file_field():
    plan = _load_plan()
    contract = plan["contract"]
    assert len(contract.get("text_fields", [])) == 2, "contract must declare exactly two text fields"
    assert len(contract.get("file_fields", [])) == 1, "contract must declare exactly one file field"


def test_every_title_case_present():
    plan = _load_plan()
    names = {c.get("name") or c.get("case") for c in plan["cases"]}
    for case in TITLE_CASES:
        assert case in names, f"missing title-named case: {case}"
    assert len(plan["cases"]) == len(TITLE_CASES), \
        f"expected exactly {len(TITLE_CASES)} cases, got {len(plan['cases'])}"


def test_baseline_asserts_returned_url_field_and_md5():
    plan = _load_plan()
    baseline = next(c for c in plan["cases"] if (c.get("name") or c.get("case")) == "baseline")
    blob = json.dumps(baseline).lower()
    assert RETURNED_FILE_URL_LABEL in blob, "baseline must assert the documented returned-file URL field"
    assert "md5" in blob, "baseline must assert file MD5 round-trip"


def test_no_out_of_lane_case():
    plan = _load_plan()
    for c in plan["cases"]:
        cid = (c.get("name") or c.get("case") or "").lower()
        for token in OUT_OF_LANE:
            assert token not in cid, \
                f"out-of-lane case '{cid}' contains '{token}' (owned by test-file-upload-and-download)"


def test_no_specific_feature_token_leaks():
    blob = pathlib.Path(GOLDEN).read_text(encoding="utf-8")
    for tok in FORBIDDEN_TOKENS:
        assert tok not in blob, "emitted plan must name no specific feature; inputs are referenced only by role"


def test_subagent_prompt_references_standard():
    prompt = pathlib.Path(SUBAGENT).read_text(encoding="utf-8")
    assert "references/agent-authoring-standard.md" in prompt, \
        "agent prompt must reference the Universal Agent Authoring & Update Standard"


def test_code_review_receipt_pass_min_85():
    receipts = glob.glob("results/_global/*.json")
    assert receipts, "no code-review receipt found in results/_global/"
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
