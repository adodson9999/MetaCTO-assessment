# Implementation Plan — api-tester-run-regression-suite

- **Agent:** api-tester-run-regression-suite
- **Workflow:** Complete regression-suite reporter (a pure two-artifact comparator — no test execution or deployment actions) — given previous + current build test-result artifacts (JUnit XML, Jest --json, pytest-json, TAP, TRX/NUnit) and the two build ids, emit a JSON report of total / prev-passed / regressions / newly-passing / flaky / slowed / overall status.
- **Rating:** now 7/10 → 10
- **Source prompt:** agent-foundry/agents/api-tester/api-tester-update-agent-prompts.md
- **Lane:** owns the regression JSON report derived solely from the two supplied test-result artifacts; defers all test execution and deployment — performs no test run or deployment action.

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
- Derive every value solely from the two supplied artifacts (previous + current); make no test run, deployment, or network call.
- Never invent a test id, a count, a failure message, or a runtime; read them only from the artifacts and echo the two build ids byte-for-byte.
- Apply the regression definition exactly: a regression is a test that passed in N-1 and failed in N — already-failing, skipped, and removed tests are never regressions; the flaky array (pass-and-fail across repeated runs of build N) is excluded from regressions.
- Set overall status to fail whenever any regression exists; never report pass when a regression is present.
- Emit exactly the required report keys (total, previously-passing, regressions with failure message, newly-passing, flaky, slowed, overall status) — no extra, renamed, or omitted field.

## 2. Prompt (run verbatim — miss no detail)

```
update-agent api-tester-run-regression-suite Specify the complete regression-suite reporter (a pure two-artifact comparator — no test execution or deployment actions): given a previous build's and a current build's automated-test result artifacts (JUnit XML, Jest --json, pytest-json, plus TAP and TRX/NUnit) and the two build ids, emit a JSON report listing the total tests, the previously-passing count, the regressions (passed in N-1, failed in N — already-failing, skipped and removed tests are never regressions) each with its failure message, the newly-passing tests, a flaky array (tests that both pass and fail across repeated runs of build N, excluded from regressions) when repeated runs are supplied, a slowed array (tests whose runtime grew beyond a documented multiple), and an overall status that is fail whenever any regression exists. Emit JSON only — no test runs, no deployment, no network, sandbox to FORGE_WORKSPACE; every value derives solely from the two artifacts. In the same update and under the same gates, build this agent's lane-and-coverage safety net: a GUARDRAIL that keeps it in its lane — it emits only the JSON report contract above, derives solely from the two artifacts, and never runs tests or touches deployment, failing closed rather than straying out of lane; GOLDEN test cases pinning the exact expected report for representative artifact pairs across each supported format and covering every single rule the title workflow names above (total, prev-passed, regression definition, newly-passing, flaky, slowed, overall status; already-failing/skipped/removed never count as regressions) with none omitted, saved as the regression baseline at tests/golden/api-tester/run-regression-suite/golden.json; and UNIT tests that, per golden pair, assert the report has exactly the required keys and that each derived value matches the hand-derived expectation (the suite fails if even one rule is wrong or missing), and that no out-of-lane behavior (test execution or deployment action) appears. Additionally, in this same update and under the update-agent gates, append the two standard sections below to this agent (identical for every agent in this file).

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
- [ ] Every title-named field is present with correct shape and count: total, previously-passing, regressions (each with failure message), newly-passing, flaky, slowed, overall status; already-failing/skipped/removed never count as regressions.
- [ ] No out-of-lane behavior appears (no test execution or deployment action); every value derives solely from the two artifacts.
- [ ] The report asserts exact computed values (hand-derived) rather than fabricated numbers; overall status is fail whenever any regression exists.
- [ ] The agent's system prompt across all four frameworks and the judge contains the verbatim Standard compliance clause and the string `references/agent-authoring-standard.md`.
- [ ] A code-review receipt exists at `results/_global/` with status pass, reviewer set == `agents/code-review/`, every reviewer ≥85.
- [ ] The golden baseline equals the post-update best and the regression gate held or improved.

### Automated test (pytest-style)
```python
import json
import pathlib
import glob

AGENT = "run-regression-suite"
REQUIRED_KEYS = [
    "total_tests", "previously_passing", "regressions",
    "newly_passing", "flaky", "slowed", "overall_status",
]


def _load_report():
    # Emitted report for the representative golden artifact pair.
    path = pathlib.Path(f"tests/golden/api-tester/{AGENT}/golden.json")
    assert path.exists(), f"missing emitted/golden report for {AGENT}"
    return json.loads(path.read_text(encoding="utf-8"))


def test_single_json_object_required_keys():
    report = _load_report()
    assert isinstance(report, dict), "report must be a single JSON object"
    for key in REQUIRED_KEYS:
        assert key in report, f"missing required report field: {key}"
    extra = set(report) - set(REQUIRED_KEYS)
    assert not extra, f"unexpected extra keys in report: {extra}"


def test_no_execution_or_deployment_marker():
    report = _load_report()
    blob = json.dumps(report).lower()
    for forbidden in ("deploy", "subprocess", "pytest -", "npm test", "http://", "https://"):
        assert forbidden not in blob, (
            f"report leaks out-of-lane execution/deployment marker: {forbidden}"
        )


def test_regressions_each_carry_failure_message():
    report = _load_report()
    for r in report["regressions"]:
        assert r.get("failure_message"), (
            f"regression {r} must carry its failure message"
        )


def test_overall_status_fail_when_regression_exists():
    report = _load_report()
    if report["regressions"]:
        assert report["overall_status"] == "fail", (
            "overall_status must be fail whenever any regression exists"
        )


def test_hand_derived_regression_set():
    # Hand-derived expectation for the representative golden pair:
    #   N-1: t_a pass, t_b pass, t_c fail, t_d pass
    #   N:   t_a pass, t_b fail, t_c fail, t_d skipped(removed)
    # Only t_b (pass->fail) is a regression; t_c already-failing is NOT;
    # t_d removed/skipped is NOT.
    expected_regressions = {"t_b"}
    report = _load_report()
    actual = {r.get("test") or r.get("name") for r in report["regressions"]}
    assert actual == expected_regressions, (
        f"regression set {actual} != hand-derived {expected_regressions}"
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
