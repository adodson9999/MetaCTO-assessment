# Implementation Plan — api-tester-measure-api-consumer-satisfaction

- **Agent:** api-tester-measure-api-consumer-satisfaction
- **Workflow:** Complete consumer-satisfaction measurement plan (plan-only over a local fixture) — emit a JSON plan defining the 90-day recipient window, NPS/CSAT/CES/open-text survey questions, 14-day collection window, promoter/passive/detractor bands + NPS formula, 30% validity threshold, per-segment NPS/CSAT, quarter-over-quarter trend, clustering config, and dashboard fields.
- **Rating:** now 7/10 → 10
- **Source prompt:** agent-foundry/agents/api-tester/api-tester-update-agent-prompts.md
- **Lane:** owns the consumer-satisfaction measurement-plan JSON over a local fixture; defers all execution — never runs the survey, delivery, or clustering itself (no database/email/survey-delivery/clustering/network call).

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
- Emit a plan only over the supplied local fixture; make no database, email, survey-delivery, clustering, or network call — a separate harness runs the plan and publishes the real numbers.
- Never invent a survey response, a recipient, an NPS/CSAT number, a theme, or a count; the plan defines structure and fixed constants only, not computed results.
- Pin the fixed constants exactly: 90-day recipient window, 0–10 NPS scale, 1–5 CSAT with top-2-box, CES ease-of-use item, 14-day collection window, 30 percent response-rate validity threshold, and the `round(promoter_pct − detractor_pct)` NPS formula with the documented promoter/passive/detractor bands.
- Reproduce the survey question text verbatim (NPS, CSAT, CES, open-text pain-point/improvement/other); never paraphrase or substitute a question.
- Emit the clustering config (k-means/TF-IDF, top-3-themes) as configuration only; never execute clustering or emit fabricated themes.

## 2. Prompt (run verbatim — miss no detail)

```
update-agent api-tester-measure-api-consumer-satisfaction Specify the complete consumer-satisfaction measurement plan (plan-only over a local fixture): emit a JSON plan defining a 90-day recipient window (distinct users with at least one API call); the survey questions including the 0–10 NPS scale, a 1–5 CSAT item with a top-2-box formula, a CES ease-of-use item, and the open-text pain-point, improvement and other questions; a 14-day collection window; the promoter/passive/detractor bands and the round(promoter_pct − detractor_pct) NPS formula; a 30 percent response-rate validity threshold; per-segment NPS and CSAT (by plan tier or call-volume band); a quarter-over-quarter trend (current versus prior with a delta); a k-means/TF-IDF top-3-themes clustering config over the combined open text; and the dashboard fields. Emit JSON only — no database, no email, no survey delivery, no clustering, no network, sandbox to FORGE_WORKSPACE; a separate deterministic harness runs the plan against the fixture and publishes the real numbers. In the same update and under the same gates, build this agent's lane-and-coverage safety net: a GUARDRAIL that keeps it in its lane — it emits only the JSON measurement-plan contract above and never executes the survey/clustering itself, failing closed rather than straying out of lane; GOLDEN test cases pinning the exact expected JSON plan and covering every single element the title workflow names above (90-day window, NPS+CSAT+CES+open-text questions verbatim, 14-day window, bands, NPS formula, 30% validity, per-segment, quarter-over-quarter trend, clustering config, dashboard fields) with none omitted, saved as the regression baseline at tests/golden/api-tester/measure-api-consumer-satisfaction/golden.json; and UNIT tests that assert the plan has exactly the required top-level keys and the exact fixed constants and question text, that every title-named element above is present with the correct shape (the suite fails if even one is missing), and that no out-of-lane behavior (executing the survey) appears. Additionally, in this same update and under the update-agent gates, append the two standard sections below to this agent (identical for every agent in this file).

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
- [ ] Every title-named element is present with correct shape: 90-day window, NPS+CSAT+CES+open-text questions verbatim, 14-day window, bands, NPS formula, 30% validity, per-segment, quarter-over-quarter trend, clustering config, dashboard fields; plus the exact fixed constants and question text.
- [ ] No out-of-lane behavior appears (no executing the survey/clustering, no database/email/survey-delivery/network call).
- [ ] The plan asserts exact fixed constants (hand-derived) rather than fabricated survey numbers.
- [ ] The agent's system prompt across all four frameworks and the judge contains the verbatim Standard compliance clause and the string `references/agent-authoring-standard.md`.
- [ ] A code-review receipt exists at `results/_global/` with status pass, reviewer set == `agents/code-review/`, every reviewer ≥85.
- [ ] The golden baseline equals the post-update best and the regression gate held or improved.

### Automated test (pytest-style)
```python
import json
import pathlib
import glob

AGENT = "measure-api-consumer-satisfaction"
REQUIRED_KEYS = [
    "recipient_window_days", "survey_questions", "collection_window_days",
    "bands", "nps_formula", "validity_threshold_pct", "per_segment",
    "quarter_over_quarter_trend", "clustering_config", "dashboard_fields",
]
OUT_OF_LANE_MARKERS = ["smtp", "send_email", "db.execute", "http://", "https://"]


def _load_plan():
    # Emitted measurement plan for the representative golden fixture.
    path = pathlib.Path(f"tests/golden/api-tester/{AGENT}/golden.json")
    assert path.exists(), f"missing emitted/golden plan for {AGENT}"
    return json.loads(path.read_text(encoding="utf-8"))


def test_single_json_object_required_keys():
    plan = _load_plan()
    assert isinstance(plan, dict), "plan must be a single JSON object"
    for key in REQUIRED_KEYS:
        assert key in plan, f"missing required plan element: {key}"


def test_fixed_constants_exact():
    # Hand-derived fixed constants pinned by the title workflow.
    plan = _load_plan()
    assert plan["recipient_window_days"] == 90, "recipient window must be 90 days"
    assert plan["collection_window_days"] == 14, "collection window must be 14 days"
    assert plan["validity_threshold_pct"] == 30, (
        "response-rate validity threshold must be 30 percent"
    )


def test_nps_formula_is_round_promoter_minus_detractor():
    plan = _load_plan()
    formula = json.dumps(plan["nps_formula"]).lower().replace(" ", "")
    assert "promoter" in formula and "detractor" in formula, (
        "NPS formula must reference promoter and detractor percentages"
    )
    assert "round" in formula, (
        "NPS formula must be round(promoter_pct - detractor_pct)"
    )


def test_survey_questions_cover_nps_csat_ces_open_text():
    plan = _load_plan()
    blob = json.dumps(plan["survey_questions"]).lower()
    for kind in ("nps", "csat", "ces", "pain", "improvement", "other"):
        assert kind in blob, f"survey questions missing the {kind} item"
    # NPS 0-10 scale and CSAT 1-5 scale present.
    assert "0-10" in blob or "0–10" in blob, "NPS 0-10 scale missing"
    assert "1-5" in blob or "1–5" in blob, "CSAT 1-5 scale missing"


def test_no_out_of_lane_execution_marker():
    plan = _load_plan()
    blob = json.dumps(plan).lower()
    for marker in OUT_OF_LANE_MARKERS:
        assert marker not in blob, (
            f"plan leaks out-of-lane execution marker: {marker} "
            f"(the agent must never execute the survey/clustering)"
        )


def test_clustering_config_is_config_only():
    plan = _load_plan()
    cfg = json.dumps(plan["clustering_config"]).lower()
    assert "k-means" in cfg or "kmeans" in cfg, "clustering config must name k-means"
    assert "tf-idf" in cfg or "tfidf" in cfg, "clustering config must name TF-IDF"
    assert "3" in cfg, "clustering config must specify top-3 themes"


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
