# Orchestrator prompts

These are **prompts**, not skills. Each file is a complete system prompt for an Orchestrator
agent that drives the api-tester agents + the 4 general agents against the DummyJSON endpoints
and **owns the per-case adjudication loop**. They replace the old `orchestration*` skills.

| Prompt | Scope | Use when |
|---|---|---|
| `orchestrator-full.md` | All 40 testers × 4 generals × every endpoint. No scoping. | You want a complete ground-truth run. |
| `orchestrator-smart.md` | Only endpoints affected by detected doc/code changes (+ their URL family). | You want to retest just what changed. |
| `orchestrator-single.md` | One named tester + 4 generals × every endpoint. | You want to isolate one tester. |

`orchestrator-full.md` is canonical. The other two carry an **identical** Responsibility Split
(§1), Invariants (§2), Adjudication Loop (§3), and Hard-fail Guardrails (§4); they differ only in
how scope is chosen (Phase 0).

## How to start an orchestrator

Load the relevant prompt as the agent's system prompt and run it from the MetaCTO-Assessment
project root, e.g.:
- Full: use `orchestrator-full.md`.
- Smart: use `orchestrator-smart.md`.
- Single: use `orchestrator-single.md` and pass the agent name, e.g.
  `orchestrator-single check-authorization-rules`.

## The bug these prompts fix

Previously the api-tester agents were pure generators, explicitly forbidden from judging
outcomes. The "stop-on-bug → bug-reporter → resume" behavior was assumed to exist but lived in
**no** component — nothing compared `actual` vs `expected` per case. Cases recorded `pass:false`
and were never escalated, so real bugs (e.g. an endpoint that should return 401/403 returning 200
with data) slid through. In one observed run, 5 failing authorization cases were recorded but
never reported.

The fix moves adjudication to where it belongs — the orchestrator:

```
Orchestrator
  └─ test-case-creator (SOLE PRODUCER) reads the agent spec's How section and
     authors the registry — the single authoritative set of cases (expected + cited_feature)
  └─ orchestrator freezes the registry and passes it UNCHANGED to the executor
  └─ executor (api-tester / crewai / langgraph / claude_sdk) CONSUMES the cases,
     runs them ONE AT A TIME, records actual ONLY — never authors a case
  └─ tc_id-set equality check: executor's tc_ids must exactly match the registry (HF10)
  └─ for each case, the ORCHESTRATOR adjudicates:
        actual == expected            → PASS
        "Code Update"                 → label, no bug
        actual != expected (MISMATCH) → send to documentation-reviewer → verdict:
            "yes"          → CONFIRMED BUG: HALT → bug-reporter (with source_of_truth) → RESUME
            "no"           → test-case-creator UPDATES expected, RE-RUN (≤2x), no bug
            "missing-docs" → record missing-docs outcome; EXCLUDE from CI; no bug
  └─ never abort; every registry case reaches a terminal outcome
```

The dedicated **documentation-reviewer** agent — not the orchestrator — decides whether a
mismatch is a real bug. It scans the docs (`data/documentation-reviewer/cli/` + `reference/`),
resolves conflicting docs in favor of the most-recently-modified file, and returns
`yes` / `no` / `missing-docs` with a `source_of_truth`. **Only a `yes` reaches the bug-reporter.**
A `missing-docs` case is recorded as `missing-docs` (not "failed") and is flagged so
run-cicd-pipeline does **not** add it to the CI suite.

"Stop immediately" means **pause-and-hand-off, then resume** — never abort. Aborting remaining
cases would collapse coverage and tank the fidelity metric (whose denominator is the full
generated matrix), so the loop always resumes and completes all cases.

## Decisions baked in (from the requirements)

1. **A mismatch is adjudicated by the documentation-reviewer, and only a `yes` is a bug.**
   - On `actual != expected` the orchestrator hands the case to **documentation-reviewer**, which
     returns one of three verdicts:
     - **`yes`** → docs document the expected behavior and observed differs → valid bug → sent to
       the bug-reporter.
     - **`no`** → observed matches the source of truth (our `expected` was wrong, or a doc
       conflict resolved to the newest file) → test-case-creator **updates the expected and the
       test is re-run** (EXPECTED-CORRECTED event); no bug.
     - **`missing-docs`** → nothing documents the behavior → the result is recorded as
       **`missing-docs` (not "failed")**, and the case is **excluded from what run-cicd-pipeline
       adds to CI**.
   - Severity tags (CRITICAL data-exposure / HIGH wrong-data / MEDIUM-LOW cosmetic) set priority
     only. They never change the rule that a `yes` bug is **reported**.
2. **The reviewer's `source_of_truth` (file, line, text) is attached to the bug report** so the
   bug-reporter documents against a real, cited source of truth. The reviewer also returns
   `other_matches` (e.g. a superseded conflicting doc) and its `reason`.
3. **Three separate, self-contained prompts** (full / smart / single) rather than one shared file.
4. **Hard-fail guardrails** — every real bug must be reported or the run is marked **BROKEN** and
   exits non-zero. No "warn and continue."
5. **Single source of test cases** — `test-case-creator` is the ONLY agent allowed to author
   cases. Every other agent and framework (crewai, langgraph, claude_sdk, future executors) is a
   consumer that may only execute cases and record actual evidence. It reads the agent spec's How
   section and emits the authoritative registry; executors never read the spec, never invent,
   expand, reorder, merge, split, add, or drop a case, and never copy any answer-key set. A
   consumer that thinks a case is missing or wrong reports back to the orchestrator and stops.

### Producer / consumer flow

```
test-case-creator (PRODUCER, runs FIRST)  ──authors──▶  registry (authoritative cases)
        │                                                     │
        │ orchestrator freezes + hashes the registry          │ same registry, unchanged
        ▼                                                     ▼
   executor (api-tester / crewai / langgraph / claude_sdk)  ──CONSUMES──▶ records actual only
        │
        ▼
   orchestrator: tc_id-set equality (HF10) → adjudicate (§3):
        mismatch → documentation-reviewer → yes (bug) / no (correct+retest) / missing-docs (exclude)
```

## Guardrails (hard fail → exit non-zero)

| ID | Rule |
|---|---|
| HF1 | Cases are sent one at a time; each `actual` is recorded/surfaced before the next. Bulk-fire = BROKEN. |
| HF2 | Every MISMATCH is sent to documentation-reviewer and ends in EXPECTED-CORRECTED→PASS (`no`), a written bug report (`yes`), or the `missing-docs` outcome (`missing-docs`). Never dropped or labeled "failed". |
| HF3 | Completeness: every registry case reaches a terminal outcome (PASS / Code Update / corrected / BUG / missing-docs). A never-executed case = mismatch(0) = BROKEN. |
| HF4 | Resume always: after a bug detour the loop continues the remaining cases. |
| HF5 | Every CONFIRMED BUG has a `[BUG_ID].json`. Bug count must equal confirmed-bug count. |
| HF6 | Writer isolation: only bug-reporter writes reports; only test-case-creator writes the registry. |
| HF7 | Corrections are auditable: every EXPECTED-CORRECTED requires a `no` verdict and logs before/after/source_of_truth. A verdict-less correction that hides a bug = BROKEN. |
| HF8 | Registry-first: no executor runs before test-case-creator has produced the registry cases for that agent+endpoint. (Enforcement point 1.) |
| HF9 | Registry immutable to executors: the same registry is passed unchanged to every executor; hash before/after — any executor change = BROKEN. (Point 2.) |
| HF10 | tc_id set equality: an executor's reported tc_ids must exactly equal the registry's — no extras, no omissions. Mismatch = authored/dropped cases → discard + re-run once, then BROKEN. (Point 3.) |
| HF11 | Producer exclusivity: only test-case-creator authors cases or expected-corrections. Any executor-authored case reaching the registry/results = BROKEN. (Point 4.) |
| HF12 | Reviewer is the doc authority: every mismatch is adjudicated by documentation-reviewer; every BUG row carries `reviewer_verdict == "yes"`; every `missing-docs` row carries `exclude_from_cicd: true` and is absent from the CI add-set. A bug without a `yes`, or a missing-docs case added to CI, = BROKEN. |

Two audit artifacts make the guardrails enforceable, written under
`agent-foundry/results/runs/[RUN_ID]/`:
- `adjudication-ledger.json` — one row per case: `{endpoint_id, agent, sub_test, expected,
  actual, cited_feature, retest_count, reviewer_verdict, source_of_truth, outcome,
  exclude_from_cicd, bug_id?}`.
- `expected-corrections.json` — one row per EXPECTED-CORRECTED event (requires a `no` verdict).

Phase 3 reconciles the ledger against the reviewer verdicts and the bug-reports directory. Any
inconsistency is a hard fail. A clean **exit 0** therefore asserts: every endpoint × every
in-scope agent ran, every registry case was adjudicated, every mismatch was reviewer-adjudicated
to a correction / bug / missing-docs, the bug count matches the report count, and no missing-docs
case entered CI.

## New: the documentation-reviewer agent

A 4th general agent, `documentation-reviewer`, is the single doc authority. The orchestrator
invokes it on every mismatch; it returns a verdict object:

```json
{
  "verdict": "yes" | "no" | "missing-docs",
  "source_of_truth": { "file": "...", "line": N, "text": "..." } | null,
  "other_matches": [ { "file": "...", "line": N, "text": "..." } ],
  "documented_expected": "..." | null,
  "observed": "...",
  "reason": "..."
}
```

It reads docs from `data/documentation-reviewer/cli/` and `data/documentation-reviewer/reference/`,
and when two files conflict, the most-recently-modified file wins as `source_of_truth` (the older
one is kept in `other_matches`). `yes` → bug; `no` → correct the expected and re-test; after a full
scan with nothing found, `missing-docs` → record `missing-docs` and exclude from CI.

## What carried over unchanged from the old skills

- Backend detection (claude-code vs ollama), prerequisite checks, `.understandignore` merge.
- `test-case-creator` as the sole registry writer, with the 3-attempt retry + ERROR sentinel —
  now also the sole **producer** that authors cases (runs first, before any executor).
- Sequential agents within an endpoint and sequential endpoints.
- State written after every agent; resumable runs.
- Smart-run change detection (cli-factory diff + `/understand-diff` + KG diff → RETEST_ENDPOINTS);
  single-run name validation against the 40-agent list.
