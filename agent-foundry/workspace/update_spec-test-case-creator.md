# Update Spec — general/test-case-creator (n600)

Captured: 2026-06-28 · skill: update-agent · tradeoff authorized: **true**

## Contract (preserved, not redesigned)
The agent stays a deterministic, read-only, text-returning **step-extractor**. It returns
ONE JSON array of step objects, each with EXACTLY the 11 keys (`tc_id`, `agent`,
`step_id`, `step_ext`, `involves_http_call`, `involves_db_query`, `involves_file_write`,
`involves_assertion`, `involves_metric_check`, `expected_outcome`, `fail_condition`),
`tc_id == [agent]-step-[step_id]`. It is NOT an HTTP/endpoint case author. The
deterministic extractor (`testcase_spec.py`), gold (`build_gold.py`), and scorer remain
authoritative. An empty array `[]` is correct ONLY when the How section has zero
numbered steps.

## CHANGE 1 — harden against empty model output (root cause of 0/13)
- Keep the 3-attempt retry, but **escalate format enforcement each attempt**:
  - attempt 1: plain brief.
  - attempt 2: prepend a one-shot worked example (sample How → sample 11-key array).
  - attempt 3: hand back the exact expected 11-key JSON skeleton to fill in.
- **Expected-empty is success**: if the deterministic extractor finds zero numbered
  steps in `how_text`, `[]` is correct — no retry, no sentinel (fixes the spurious
  `TC-ERR-...-noop`).
- On terminal empty after attempt 3 for a steps-present agent, emit an auditable
  sentinel `tc_id = "TC-ERR-<agent>"`, `reason = "extraction_failure"`, **fail loudly**
  (`fail = true`). Never return nothing; never let an empty result score as success.

## CHANGE 2 — strengthen the judge so empty/degenerate output cannot saturate
Authorized metric move (adopt even if the reported score drops; prior 100% was
saturation, not correctness). In `judge/general/test-case-creator/metric.json` +
new `score.py`:
- **G4 anti-saturation oracle**: reference input → 100%; empty `{}`/`[]` → a low floor,
  never 100%; single-knob mutations (drop a step, flip one `involves_*`, blank an Assert
  clause) each lower the score.
- **G5 schema validity**: every case has exactly the 11 keys, correct types, unique
  `tc_id`; malformed cases are flagged/dropped, never counted as covered.
- **G6 tc_id set equality vs gold per agent**: no invented extras, no omissions.
- **G8 gold determinism**: regenerating the reference registry twice is byte-identical.
- **G9 coverage denominator intact**: `gold_tc == sum of steps per enabled agent`; every
  gold `tc_id` appears in the registry or as a logged sentinel.
- **G10 regression floor**: coverage / field-accuracy may not drop below the last
  accepted baseline.

## Acceptance
1. The oracle suite proves the metric discriminates (empty output ≠ 100%).
2. A per-agent smoke (`FORGE_TESTCASE_AGENT` on 2–3 agents) runs end-to-end and passes.

## Baseline (FLOOR)
Last real judged run RUN-20260628-025411: `metric_value = 0.0%` (post empty-output
collapse). Prior "100%" was saturation. Tradeoff authorized → regression gate satisfied.
