# Implementation Plan — api-tester-track-defect-density

- **Agent:** api-tester-track-defect-density
- **Workflow:** Complete defect-density reporter (a pure deterministic calculator over the supplied brief — no Jira or git calls) — emit a JSON report of raw/severity-weighted/per-area densities, rolling 3-sprint average, deviation, alert flag, P1–P4 counts, and trend.
- **Rating:** now 7/10 → 10
- **Source prompt:** agent-foundry/agents/api-tester/api-tester-update-agent-prompts.md
- **Lane:** owns the defect-density JSON report computed solely from the supplied sprint brief; defers all external data acquisition — performs no Jira/git/network call.

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
- Compute every value solely from the supplied brief (Jira issues with priorities, git numstat diff, three preceding densities); make no Jira, git, network, or test-execution call.
- Never invent a defect, an issue id, a changed-line count, a component label, or any number — read them only from the brief.
- Apply the fixed formulas exactly: defects per 1000 changed lines excluding test files; severity weights P1=8/P2=4/P3=2/P4=1; rolling three-sprint average; deviation percent; alert flag only when deviation exceeds 20 percent.
- Round all arithmetic half-up exactly as specified; never truncate, round half-even, or report unrounded floats.
- Emit exactly the required report keys (sprint_name, defect_density, severity-weighted density, per-area densities, rolling average, deviation percent, alert flag, P1–P4 counts, trend) — no extra, renamed, or omitted field.

## 2. Prompt (run verbatim — miss no detail)

```
update-agent api-tester-track-defect-density Specify the complete defect-density reporter (a pure deterministic calculator over the supplied brief — no Jira or git calls): given a sprint's Jira issues with priorities, a git numstat diff, and the three preceding densities, emit a JSON report containing sprint_name, defect_density (defects per 1000 changed lines, excluding test files), a severity-weighted density (P1=8/P2=4/P3=2/P4=1), per-area densities grouped by a component label, the rolling three-sprint average, the deviation percent, an alert flag when deviation exceeds 20 percent, the P1–P4 counts, and the trend versus the most recent sprint, with all arithmetic rounded half-up. Emit JSON only — no Jira, no git, no network, sandbox to FORGE_WORKSPACE; every value is derived solely from the brief. In the same update and under the same gates, build this agent's lane-and-coverage safety net: a GUARDRAIL that keeps it in its lane — it emits only the JSON report contract above, computes solely from the brief, and never calls Jira/git/network, failing closed rather than straying out of lane; GOLDEN test cases pinning the exact expected JSON report for representative sprint briefs and covering every single field and rule the title workflow names above (raw density with test-file exclusion, severity-weighted density, per-area densities, rolling 3-sprint average, deviation percent, 20% alert flag, P1–P4 counts, trend, half-up rounding) with none omitted, saved as the regression baseline at tests/golden/api-tester/track-defect-density/golden.json; and UNIT tests that, per golden brief, assert the report has exactly the required keys and that each computed value matches the hand-derived expected number (the suite fails if even one field or rule is wrong or missing), and that no out-of-lane behavior (any external call) appears. Additionally, in this same update and under the update-agent gates, append the two standard sections below to this agent (identical for every agent in this file).

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
- [ ] Every title-named field is present with correct shape and count: sprint_name, defect_density (with test-file exclusion), severity-weighted density, per-area densities, rolling 3-sprint average, deviation percent, 20% alert flag, P1–P4 counts, trend; all arithmetic rounded half-up.
- [ ] No out-of-lane behavior appears (no Jira/git/network/test-execution call); every value is derived solely from the brief.
- [ ] The report asserts exact computed values (hand-derived) rather than fabricated numbers.
- [ ] The agent's system prompt across all four frameworks and the judge contains the verbatim Standard compliance clause and the string `references/agent-authoring-standard.md`.
- [ ] A code-review receipt exists at `results/_global/` with status pass, reviewer set == `agents/code-review/`, every reviewer ≥85.
- [ ] The golden baseline equals the post-update best and the regression gate held or improved.

### Automated test (pytest-style)
```python
import json
import pathlib
import glob
from decimal import Decimal, ROUND_HALF_UP

AGENT = "track-defect-density"
REQUIRED_KEYS = [
    "sprint_name", "defect_density", "severity_weighted_density",
    "per_area_densities", "rolling_3_sprint_average", "deviation_percent",
    "alert", "p1_count", "p2_count", "p3_count", "p4_count", "trend",
]


def _load_report():
    # Emitted report for the representative golden sprint brief.
    path = pathlib.Path(f"tests/golden/api-tester/{AGENT}/golden.json")
    assert path.exists(), f"missing emitted/golden report for {AGENT}"
    return json.loads(path.read_text(encoding="utf-8"))


def _half_up(x, places=2):
    q = Decimal(10) ** -places
    return float(Decimal(str(x)).quantize(q, rounding=ROUND_HALF_UP))


def test_single_json_object_required_keys():
    report = _load_report()
    assert isinstance(report, dict), "report must be a single JSON object"
    for key in REQUIRED_KEYS:
        assert key in report, f"missing required report field: {key}"
    extra = set(report) - set(REQUIRED_KEYS)
    assert not extra, f"unexpected extra keys in report: {extra}"


def test_no_external_call_emitted():
    report = _load_report()
    blob = json.dumps(report).lower()
    for forbidden in ("http://", "https://", "jira", "git ", "subprocess"):
        assert forbidden not in blob, (
            f"report leaks out-of-lane external-call marker: {forbidden}"
        )


def test_alert_flag_matches_deviation_rule():
    report = _load_report()
    expected_alert = abs(report["deviation_percent"]) > 20
    assert report["alert"] == expected_alert, (
        f"alert flag {report['alert']} disagrees with >20% rule on "
        f"deviation_percent={report['deviation_percent']}"
    )


def test_hand_derived_raw_defect_density():
    # Hand-derived expectation for the representative golden brief:
    # 12 defects over 4800 non-test changed lines -> 12 / 4800 * 1000 = 2.5
    # (defects per 1000 changed lines, excluding test files, half-up to 2dp).
    DEFECTS = 12
    NON_TEST_CHANGED_LINES = 4800
    expected = _half_up(DEFECTS / NON_TEST_CHANGED_LINES * 1000, 2)  # 2.5
    report = _load_report()
    assert report["defect_density"] == expected, (
        f"defect_density {report['defect_density']} != hand-derived {expected}"
    )


def test_hand_derived_severity_weighted_density():
    # Hand-derived: P1=1,P2=2,P3=4,P4=5 -> weighted defects
    # = 1*8 + 2*4 + 4*2 + 5*1 = 29; per 1000 lines = 29 / 4800 * 1000 = 6.04
    weighted_defects = 1 * 8 + 2 * 4 + 4 * 2 + 5 * 1  # 29
    expected = _half_up(weighted_defects / 4800 * 1000, 2)  # 6.04
    report = _load_report()
    assert report["severity_weighted_density"] == expected, (
        f"severity_weighted_density {report['severity_weighted_density']} "
        f"!= hand-derived {expected}"
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
