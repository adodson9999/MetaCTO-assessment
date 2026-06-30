# Implementation Plan — api-tester-test-ssl-tls-enforcement

- **Agent:** api-tester-test-ssl-tls-enforcement
- **Workflow:** Complete TLS-enforcement tester — given a target (https/http ports, an endpoint, the minimum TLS version), plan protocol probes, certificate assertions, HSTS, forward-secrecy/cipher-order, forbidden weak-cipher families, and SNI/wildcard cases.
- **Rating:** now 7/10 → 10
- **Source prompt:** agent-foundry/agents/api-tester/api-tester-update-agent-prompts.md
- **Lane:** owns the transport-layer TLS JSON contract (protocol/cert/HSTS/cipher/SNI assertions); defers application-layer auth.

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
- Echo the target's https/http ports, endpoint, and minimum TLS version byte-for-byte; never invent a port, host, or version threshold.
- Pin the five protocol-probe expect values exactly (plain HTTP rejected/redirected; TLS 1.0 and 1.1 rejected; TLS 1.2 and 1.3 accepted); never fabricate a handshake outcome or negotiated suite.
- Never open a connection, perform a TLS handshake, send an HTTP request, or hit the network — the separate harness performs the handshakes and read-only GETs.
- Enumerate exactly the five forbidden weak-cipher families (RC4, DES, 3DES, EXPORT, NULL) as not-offered; never add or drop a family.
- Emit only transport-layer TLS cases; never emit an application-layer-auth case (out of lane).

## 2. Prompt (run verbatim — miss no detail)

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
```

## 3. Test (verify the job was done correctly)

### Verification checklist
- [ ] Output is a single valid JSON object with exactly this agent's required top-level keys — nothing else, no prose.
- [ ] Every title-named case is present with correct shape and count: five protocol probes with correct accept/reject, certificate assertions (incl. OCSP), HSTS, forward-secrecy/cipher-order, the five forbidden weak-cipher families, SNI/wildcard; plus the exact protocol-probe expect values.
- [ ] No out-of-lane case appears (no application-layer auth); the agent makes no connection/handshake/HTTP/network call.
- [ ] Each case carries primary + also_accept and a granular steps log.
- [ ] The agent's system prompt across all four frameworks and the judge contains the verbatim Standard compliance clause and the string `references/agent-authoring-standard.md`.
- [ ] A code-review receipt exists at `results/_global/` with status pass, reviewer set == `agents/code-review/`, every reviewer ≥85.
- [ ] The golden baseline equals the post-update best and the regression gate held or improved.

### Automated test (pytest-style)
```python
import json
import pathlib
import glob

AGENT = "test-ssl-tls-enforcement"
TITLE_CASES = [
    "protocol_probes", "certificate_assertions", "hsts",
    "forward_secrecy_cipher_order", "forbidden_weak_ciphers", "sni",
]
FORBIDDEN_CIPHERS = ["RC4", "DES", "3DES", "EXPORT", "NULL"]
OUT_OF_LANE = ["auth", "login", "rbac", "token"]  # application-layer auth


def _load_emitted_plan():
    path = pathlib.Path(f"tests/golden/api-tester/{AGENT}/golden.json")
    assert path.exists(), f"missing emitted/golden plan for {AGENT}"
    return json.loads(path.read_text(encoding="utf-8"))


def test_single_json_object_required_keys():
    plan = _load_emitted_plan()
    assert isinstance(plan, dict), "plan must be a single JSON object"
    for key in ("target", "cases"):
        assert key in plan, f"missing required top-level key: {key}"


def test_every_title_case_present():
    plan = _load_emitted_plan()
    names = {c.get("name") or c.get("case") for c in plan["cases"]}
    for case in TITLE_CASES:
        assert case in names, f"missing title-named case: {case}"
    assert len(plan["cases"]) == len(TITLE_CASES), (
        f"expected exactly {len(TITLE_CASES)} cases, got {len(plan['cases'])}"
    )


def test_five_protocol_probe_expect_values():
    plan = _load_emitted_plan()
    probes = next(
        c for c in plan["cases"]
        if (c.get("name") or c.get("case")) == "protocol_probes"
    )
    expects = probes.get("probes") or probes.get("expects")
    assert len(expects) == 5, "must have exactly five protocol probes"
    blob = json.dumps(expects).lower()
    for label in ("http", "tls1.0", "tls1.1", "tls1.2", "tls1.3"):
        assert label.replace(".", "") in blob.replace(".", ""), (
            f"protocol probe for {label} missing"
        )


def test_five_forbidden_weak_cipher_families():
    plan = _load_emitted_plan()
    weak = next(
        c for c in plan["cases"]
        if (c.get("name") or c.get("case")) == "forbidden_weak_ciphers"
    )
    blob = json.dumps(weak).upper()
    for fam in FORBIDDEN_CIPHERS:
        assert fam in blob, f"forbidden weak-cipher family {fam} not asserted"


def test_no_out_of_lane_case():
    plan = _load_emitted_plan()
    for c in plan["cases"]:
        cid = (c.get("name") or c.get("case") or "").lower()
        for token in OUT_OF_LANE:
            assert token not in cid, (
                f"out-of-lane case '{cid}' contains '{token}' "
                f"(application-layer auth is out of lane)"
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
