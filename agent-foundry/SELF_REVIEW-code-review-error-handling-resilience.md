# SELF_REVIEW — code-review-error-handling-resilience

**Built:** 2026-06-29 · **Group:** code-review · **Short name:** error-handling-resilience
**Backend:** not run live (no server started; deterministic gates only)

## What was built

The single-lens agent in all four frameworks (langgraph / crewai / claude_sdk / subagent),
mirroring the vulnerability sibling's substrate:

- `agents/common/errresilience_spec.py` — held-out loader, per-case brief, strict
  `{rating, notes}` schema gate + in-band scorer, reference oracle (band midpoint).
- `agents/common/errresilience_prompt.py` — 12 debate-gated APPROVED_LINES + user message.
- `agents/common/errresilience.py` — deterministic driver (score every case, write reviews,
  emit metric, EverOS note). Empty/raising `generate()` → `{}` → scores 0.0 (no saturation).
- `agents/code-review/error-handling-resilience/{langgraph,crewai,claude_sdk,subagent}/run.py`
  — thin dispatchers into `agents/common/runners/`.
- `agents/code-review/error-handling-resilience/subagent/code-review-error-handling-resilience.md`
  — canonical prompt artifact; body == APPROVED_LINES verbatim (consistency-checked).
- `judge/code-review/error-handling-resilience/{metric.json,score.py}` — `rating_band_accuracy`,
  tie-break schema-pass → tokens → elapsed; renders leaderboard.
- `results/code-review/error-handling-resilience/held_out.jsonl` — 8 cases.
- `tests/golden/code-review/error-handling-resilience/{run_golden.py,golden.json}`.
- `scripts/run_errresilience_agents__code-review-error-handling-resilience.py`.
- `data/code-review-error-handling-resilience/task_spec.md`.
- Registered: `.claude/agents/code-review-error-handling-resilience.md` (host symlink, resolves).

## Verification (deterministic, no model, no server)

- `py_compile` clean on all 10 Python files.
- Golden suite: schema 13/13 (forces the strict two-key contract: rejects 101, −1, float,
  string, bool, empty notes, extra key, missing notes, empty object) + band 6/6
  (oracle in-band + empty scores 0).
- Metric soundness self-test: oracle (band-midpoint) = **1.0**, empty = **0.0**,
  degraded "always 95" = **0.375** → metric rewards correct, refuses fallback saturation,
  and discriminates. Owner seed bands honored exactly (ehr-001 [85,100], ehr-002 [0,35]).
- Consistency: subagent `.md` body == 12 gated APPROVED_LINES verbatim.

## Held-out coverage (8 cases)

Safe/high: `with open` (ehr-001), `try/finally` release (ehr-007), bounded idempotent retry
that re-raises (ehr-008). Unsafe/low: swallowed mid-transaction charge→ship (ehr-002, seed),
swallowed single write (ehr-003), writer leak on error unwind (ehr-004), unbounded retry of
non-idempotent charge (ehr-005), fail-open on auth error (ehr-006). Every lens bullet is
exercised by ≥1 case.

## Gaps / residual risk

- **HIGH — no live ranking.** Per owner default for the recent code-review builds, no
  backend was started, so there is no real four-way leaderboard yet. The harness is wired:
  `python scripts/run_errresilience_agents__code-review-error-handling-resilience.py` then
  the judge `score.py`, once Ollama (or a Claude shim) is up. Expect a likely high/tied
  field — the prompt is highly determined and these snippets are unambiguous.
- **MEDIUM — band width.** Bands are generous (e.g. ehr-004 [1,45]) so a correct lens lands
  in band without pixel-precision; this makes the metric tolerant. A future tightening pass
  could narrow bands once a live distribution exists.
- **MEDIUM — small held-out (8).** Enough to exercise every bullet once; not enough to
  separate two strong agents finely. Schema-pass is the real discriminator at this size.
- **LOW — Phase 4.5 / Phase 5 not run.** No 10-round tournament or SkillOpt/SkillClaw wiring
  for this lens (matches the vulnerability sibling's scope). The post-golden baseline is the
  oracle = 1.0 reference.

## Concrete improvements (not auto-applied)

1. Start a backend and run the four agents + judge to produce the first real leaderboard.
2. Add 4–6 harder held-out cases (partial rollback that itself can fail; retry with a cap
   but non-idempotent effect; context manager that suppresses in `__exit__`).
3. Tighten bands after observing the live rating distribution.
