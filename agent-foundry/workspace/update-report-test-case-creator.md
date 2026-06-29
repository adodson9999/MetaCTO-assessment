# Update Report — general/test-case-creator (n600)

Date: 2026-06-28 · Skill: update-agent · Backup: `archives/update-test-case-creator-20260628T142536Z/`

## Change applied
Two authorized changes, contract preserved (the agent stays a deterministic, read-only,
text-returning step-extractor emitting ONE 11-key JSON array; `[]` is correct only for a
zero-step How section).

- **CHANGE 1 — harden the harness against empty model output** (root cause of the 0/13
  collapse). Tradeoff: n/a (pure robustness).
- **CHANGE 2 — strengthen the judge so empty/degenerate output cannot saturate.**
  Tradeoff: **authorized** (adopt even if the reported score drops; the prior 100% was
  saturation, not correctness).

## Root cause found
The 0/13 was two compounding faults:
1. **Transport:** the shared local runner sent `response_format={"type":"json_object"}`,
   which forces the model to emit a single JSON *object* (only step 1) when the prompt
   demands a JSON *array* — so `extract_json_array` found nothing and every step-bearing
   agent went empty. Proven directly against Ollama (object with json_object, correct
   array without).
2. **Metric:** scoring trusted the harness's self-reported `metric_value` via the generic
   `judge_score.py`, with a broken metric path (`judge/test-case-creator/` — no
   `general/`). Empty/benign-wrong output could be credited; the old "100%" was saturation.

## Files touched
- `agents/common/testcase.py` — escalating retry prefixes (attempt 2 = one-shot worked
  example, attempt 3 = exact 11-key skeleton; the old attempt-3 skeleton was the WRONG
  `description`/`steps` schema); `_expected_step_count` guard so a zero-step spec returns
  `[]` as success (no retry, no sentinel); loud `TC-ERR-<agent>` sentinel
  (`reason=extraction_failure`, `fail=true`); fixed `emit()` metric path to
  `judge/general/test-case-creator/`.
- `agents/common/runners/subagent_runner.py` — `build_invoker` gains an optional
  `response_format` param (default `{"type":"json_object"}` — backward compatible);
  `_via_local` omits it when `None`.
- `agents/general/test-case-creator/subagent/run.py` — passes `response_format=None`
  (array-emitting agent).
- `judge/general/test-case-creator/score.py` — **new** authoritative scorer: re-scores
  each agent's emitted registry vs gold (never trusts the harness number), gates
  G4/G5/G6/G8/G9/G10, a `quality_score = coverage x field-accuracy x set-equality`
  rank key, an `--oracle` discrimination proof, and a `--check-regression` (G10).
- `judge/general/test-case-creator/metric.json` — declares the six gates; headline moved
  to `quality_score`; `metric_value` stays authoritative coverage.
- `tests/golden/general/test-case-creator/golden.json` — **new** baseline + proven oracle
  invariants.
- `scripts/phase4_testcase_run.sh` — runs the oracle as a precondition, then the
  authoritative scorer, then the G10 regression check (replaces the generic scorer + the
  broken metric path).
- `.claude/agents/general-test-case-creator.md` — **restored** missing host registration
  (its siblings had one); resolves to the canonical subagent prompt.

## Metric — moved (authorized, recorded)
- Old: generic `judge_score.py` echoes the harness `metric_value`; empty/sentinel output
  could be credited → saturation (apparent 100%).
- New: authoritative re-scoring with anti-saturation gates. Empty `[]`, malformed `{}`,
  and the all-sentinel collapse all score **0** (not 100); every single-knob mutation
  strictly lowers `quality_score`.

## Score
| Stage | Coverage | Field-accuracy | quality_score |
|-------|----------|----------------|---------------|
| Baseline FLOOR (RUN-20260628-025411, real) | 0.0% | 0.0% | 0.0 |
| After change — full run (ACCEPT-FULL-20260628T152726, ollama qwen2.5:14b, temp 0) | **92.31%** (12/13) | **87.12%** | **80.42** |

Verdict: **recovered** (0% → 92.31%) under a strictly harder, non-saturating metric.
The one missing case is a genuine partial-extraction gap (pagination step 4), correctly
flagged by G9 rather than hidden.

## Acceptance — both met
1. **Oracle discriminates** (`score.py --oracle`, exit 0): reference→100; empty `[]`→0;
   malformed `{}`→0; all-sentinel collapse→0; drop-step / flip-involves_* / blank-Assert /
   invent-extra each <100; G8 gold determinism; G9 denominator (13==13). Deterministic
   across repeated runs.
2. **Per-agent smoke** (`FORGE_TESTCASE_AGENT`, ollama, end-to-end): demo-crud 100% (6/6,
   incl. sub-lettered 3a/3b), demo-metrics 100% (3/3, incl. the `÷` step), demo-pagination
   75% (3/4), demo-noop `[]` with **no sentinel** (expected-empty). Full run scored by the
   authoritative judge: G8=True, G9=True, 0 malformed, 0 invented extras. G10 vs baseline: OK.

## Regression protection
FLOOR was 0.0% (last real run). New best 92.31% under a harder metric → no regression.
Metric move authorized in the change prompt. Golden baseline re-derived from the
post-update best (coverage 92.31 / field 87.12, tolerance 15.0 for backend stochasticity;
the hard invariant is the exact, deterministic oracle).

## Notes / scope
- This foundry predates the forge-agents v2 script suite — `verify_build.py`,
  `slop_scan.py`, `golden_run.py`, `determinism_check.py`, `analyze.py` are **absent**
  (only `debate_gate.py` exists). Neither change edits a debate-gated *prompt* line
  (CHANGE 1 = harness, CHANGE 2 = judge), so the debate gate did not apply. The equivalent
  gates were run manually: oracle discrimination, gold determinism (G8, in-memory + on-disk
  byte-identical), backward-compat scan of all `build_invoker` callers, and byte-compile of
  every changed module.
- `ollama serve` crashed mid-run once (connection drops surfaced as loud sentinels — the
  intended behavior); restarted for the clean smoke.
