# Implementation Plan — api-tester-test-ip-allowlist-enforcement

- **Agent:** api-tester-test-ip-allowlist-enforcement
- **Workflow:** Complete IP-allowlist tester — given a restricted endpoint's contract (allow/block IPs, edge-IP + X-Forwarded-For header names, allowlist management path, success/forbidden codes), plan allowlisted / non-allowlisted / XFF-spoof / CIDR / IPv6 / multi-hop XFF / denylist-precedence / allowlist add+remove cases.
- **Rating:** now 7/10 → 10
- **Source prompt:** agent-foundry/agents/api-tester/api-tester-update-agent-prompts.md
- **Lane:** owns the IP-allowlist JSON contract (network-origin allow/deny enforcement and allowlist management); defers role-based authorization.

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
- Echo the contract's allow IPs, block IPs, edge-IP and `X-Forwarded-For` header names, allowlist management path, and success/forbidden codes byte-for-byte; never invent an IP, header name, or status.
- Assert no resource data on every blocked case; never fabricate a response body for a 403.
- Never send HTTP, set a source IP, mutate an allowlist, or hit the network — the separate harness sets source IP, headers, and allowlist actions and records responses.
- Emit only network-origin allowlist cases; never emit a role-based-authorization case (out of lane).
- Honor only the documented trusted-proxy depth for multi-hop XFF and the documented denylist-precedence rule; do not assume an undeclared default.

## 2. Prompt (run verbatim — miss no detail)

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
```

## 3. Test (verify the job was done correctly)

### Verification checklist
- [ ] Output is a single valid JSON object with exactly this agent's required top-level keys — nothing else, no prose.
- [ ] Every title-named case is present with correct shape and count: allowlisted-200, non-allowlisted-403, XFF-spoof-403, CIDR/subnet, IPv6, multi-hop XFF depth, denylist-precedence, allowlist add-allows, allowlist remove-blocks; plus the no-data-on-block assertion.
- [ ] No out-of-lane case appears (no role-based authorization); the agent makes no HTTP/allowlist-mutation/network call.
- [ ] Each case carries primary + also_accept and a granular steps log.
- [ ] The agent's system prompt across all four frameworks and the judge contains the verbatim Standard compliance clause and the string `references/agent-authoring-standard.md`.
- [ ] A code-review receipt exists at `results/_global/` with status pass, reviewer set == `agents/code-review/`, every reviewer ≥85.
- [ ] The golden baseline equals the post-update best and the regression gate held or improved.

### Automated test (pytest-style)
```python
import json
import pathlib
import glob

AGENT = "test-ip-allowlist-enforcement"
TITLE_CASES = [
    "allowlisted_200", "non_allowlisted_403", "xff_spoof_403",
    "cidr_subnet", "ipv6", "multi_hop_xff_depth",
    "denylist_precedence", "allowlist_add_allows", "allowlist_remove_blocks",
]
OUT_OF_LANE = ["role", "rbac", "permission"]  # role-based authorization


def _load_emitted_plan():
    path = pathlib.Path(f"tests/golden/api-tester/{AGENT}/golden.json")
    assert path.exists(), f"missing emitted/golden plan for {AGENT}"
    return json.loads(path.read_text(encoding="utf-8"))


def test_single_json_object_required_keys():
    plan = _load_emitted_plan()
    assert isinstance(plan, dict), "plan must be a single JSON object"
    for key in ("endpoint", "cases"):
        assert key in plan, f"missing required top-level key: {key}"


def test_every_title_case_present():
    plan = _load_emitted_plan()
    names = {c.get("name") or c.get("case") for c in plan["cases"]}
    for case in TITLE_CASES:
        assert case in names, f"missing title-named case: {case}"
    assert len(plan["cases"]) == len(TITLE_CASES), (
        f"expected exactly {len(TITLE_CASES)} cases, got {len(plan['cases'])}"
    )


def test_no_data_on_block_assertion():
    plan = _load_emitted_plan()
    for c in plan["cases"]:
        cid = (c.get("name") or c.get("case") or "")
        if "403" in cid or "blocks" in cid:
            blob = json.dumps(c).lower()
            assert "no_data" in blob or "no data" in blob or "empty" in blob, (
                f"blocked case '{cid}' must assert no resource data returned"
            )


def test_no_out_of_lane_case():
    plan = _load_emitted_plan()
    for c in plan["cases"]:
        cid = (c.get("name") or c.get("case") or "").lower()
        for token in OUT_OF_LANE:
            assert token not in cid, (
                f"out-of-lane case '{cid}' contains '{token}' "
                f"(role-based authorization is out of lane)"
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
    matched = [
        json.loads(pathlib.Path(r).read_text(encoding="utf-8"))
        for r in receipts
        if AGENT in pathlib.Path(r).read_text(encoding="utf-8")
    ]
    assert matched, f"no code-review receipt referencing {AGENT}"
    for data in matched:
        assert data.get("status") == "pass", f"receipt status not pass: {data}"
        ratings = [rv["rating"] for rv in data.get("reviewers", [])]
        assert ratings, "receipt has no reviewer ratings"
        assert min(ratings) >= 85, f"a reviewer scored below 85: {ratings}"
```
