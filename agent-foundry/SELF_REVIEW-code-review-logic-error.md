# SELF_REVIEW — code-review-logic-error

**Group:** code-review · **Short name:** logic-error · **Built:** 2026-06-30
**Lens:** would the code do the right thing for every normal input, even though it runs
without crashing — judge logical correctness only.

## What was built (4 agents + judge, full deliverable set)

- **Common lens trio** (`agents/common/`): `logicerror_prompt.py` (13 debate-gated APPROVED
  lines + `active_prompt`/`user_message`), `logicerror_spec.py` (case loading, oracle,
  strict `{rating, notes}` scorer), `logicerror.py` (deterministic driver shared by all four
  frameworks).
- **Four framework agents** (`agents/code-review/logic-error/`): `subagent/` (canonical
  prompt md + dispatcher), `langgraph/`, `crewai/`, `claude_sdk/` — each a thin `run.py`
  delegating to `agents/common/runners/`. Identical prompt across all four; only the
  framework differs (fair comparison).
- **Judge** (`judge/code-review/logic-error/`): `metric.json` (`rating_band_accuracy`,
  higher-is-better) + `score.py` (recomputes authoritatively, ranks
  `accuracy ↓ → tokens ↑ → elapsed ↑`, renders the leaderboard).
- **Data/labels**: `data/code-review-logic-error/{task_spec.md,logicerror_spec.json}`,
  `results/code-review/logic-error/held_out.jsonl` (2 disjoint-band seed cases).
- **Run script**: `scripts/run_logicerror_agents__logic-error.py`.
- **Golden suite**: `tests/golden/code-review/logic-error/{golden.json,run_golden.py}` —
  11 schema cases + 2 band cases (oracle + saturation guard).
- **Host registration**: `.claude/agents/code-review-logic-error.md` → symlink to the
  canonical subagent prompt (confirmed readable).

## Verification performed

- **Golden suite:** PASS — schema_cases 11/11, band_cases 4/4 (oracle in-band + empty→0).
- **Oracle / saturation / schema self-test:** PASS — oracle scores 1.0 on every case; empty
  emission scores 0.0 (no saturation trap, per `forge-metric-saturation`); constant ratings
  {0,10,50,92,100} all score ≤ 0.5 (disjoint bands); 9 malformed objects rejected by the
  strict schema, 3 valid accepted.
- **Live Phase-4 run (Ollama backend):** all four agents emitted, `rating_band_accuracy=1.0`,
  schema_valid=100%. Ratings genuinely discriminate: LE-001 (correct accessor) → 85;
  LE-002 (off-by-one) → 10–20.
- **Determinism (principle 3):** a second live run landed every case in the same band
  (identical ratings) — band-stable.
- **Byte-compile:** all 8 new `.py` files compile clean.

## Gaps / residual ambiguities

1. **Tiny labeled set (2 cases).** Disjoint bands defeat constant-rating saturation, but the
   held-out set only exercises one logic family deeply (off-by-one/bound). Swap in more
   labeled `{input_code, gold_band}` lines (inverted condition, null mishandling, stale
   state, wrong-variable copy-paste, false-assumption) to broaden coverage; ids auto-assign
   in line order (LE-001, LE-002, …). No code change needed.
2. **Crash vs wrong-result wording.** The lens headline says "even though it runs without
   crashing," yet the LE-002 anchor (`items[len(items)]`) actually raises `IndexError`. The
   prompt scopes the bug as an off-by-one bound confusion (covered by this lens) and rates on
   "wrong result for a normal input," so the rating is correct; the headline is aspirational
   framing, not a gate. Left as-is to match the task brief verbatim.
3. **Tokens unreported (n/a).** Frameworks didn't expose usage on this backend, so ties break
   on elapsed only. Acceptable — accuracy is the primary key and all four tied at 1.0.
4. **Phase 4.5 tournament not run.** Single Phase-4 run produced the baseline (1.0). The
   10-round keep-if-improved loop and SkillOpt/SkillClaw wiring are available via the foundry
   but not exercised here; with accuracy already at the oracle ceiling there is no headroom to
   improve against the current labels (re-baseline after labels are broadened).

## Fragile wiring fixed during build

- `run_golden.py` workspace default was `parents[4]` (one level too high → `ModuleNotFoundError`
  when run without `FORGE_WORKSPACE`); corrected to `parents[3]`. Now runs with or without the
  env var.
