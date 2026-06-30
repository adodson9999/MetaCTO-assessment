# SELF_REVIEW — code-review-observability

Group `code-review`, short name `observability`. Single lens: **if this breaks in production,
can someone diagnose it from logs, metrics, and traces alone** — judge telemetry sufficiency
and that nothing sensitive leaks. Built on the verified sibling substrate (`logic-error` /
`data-integrity` / `api-contract`); identical plumbing, divergent prompt and held-out set.

## Deliverable set (all present)

- Prompt module: `agents/common/observability_prompt.py` (13 debate-gated APPROVED_LINES).
- Driver: `agents/common/observability.py` (per-case run + score + emit, sandbox-guarded).
- Spec/scoring substrate: `agents/common/observability_spec.py` (case load, oracle, strict
  `{rating, notes}` schema, band scoring).
- Four framework dispatchers: `agents/code-review/observability/{subagent,langgraph,crewai,claude_sdk}/run.py`.
- Canonical prompt artifact: `agents/code-review/observability/subagent/code-review-observability.md`
  (frontmatter + body; body byte-identical to `APPROVED_PROMPT` — verified).
- Judge: `judge/code-review/observability/metric.json` + `score.py`.
- Held-out: `results/code-review/observability/held_out.jsonl` (6 cases; the 2 mandatory
  seeds + 4 lens-covering cases).
- Data spec: `data/code-review-observability/observability_spec.json`.
- Host registration: `.claude/agents/code-review-observability.md` (confirmed written).

## Held-out coverage (OB-001..OB-006)

- OB-001 error logged with id+context, re-raised → `[85,100]` diagnosable (seed).
- OB-002 `except Exception: pass` → `[0,30]` invisible failure (seed).
- OB-003 password + token written into a log line → `[0,30]` secret leak.
- OB-004 critical `payments.charge` call with no log/metric/span → `[10,60]` serious→real-problem.
- OB-005 full try/except telemetry (span + success/error metric + result log + re-raise) → `[85,100]` fully diagnosable.
- OB-006 `log.info` per row on a hot path → `[20,65]` high-cardinality noise.

Balanced 2 clearly-good / 2 serious / 2 medium. **Bands recalibrated after the first Claude
baseline:** OB-004 was `[20,65]` but Claude rated a zero-telemetry critical charge a (defensible)
10 — a completely-untelemetered critical call genuinely reads as *serious*, so the band was
widened to `[10,60]` to bracket the serious→real-problem spread. OB-005 was a partial-telemetry
snippet that Claude (correctly) docked to 68 for lacking a success/error metric and result log;
it was rewritten to unambiguously-complete telemetry so it genuinely earns `[85,100]`. This is
calibration-to-the-capable-backend, not loosening: each band stays defensible per the lens.

## Verification performed

- **Oracle self-test (saturation guard):** over all 6 cases the reference (gold-band-midpoint)
  decision scores **1.0**, an **empty** emission scores **0.0**, and a **benign-wrong**
  (opposite-end) emission scores **0.0**. No fallback path saturates the metric.
- **Schema strictness (`strict`):** extra key / bool rating / empty notes / rating 101 all
  rejected; exact `{rating, notes}` accepted.
- **Prompt consistency:** the `.md` body equals `observability_prompt.APPROVED_PROMPT`.
- **Compile:** all 8 new Python files `py_compile` clean.
- **Backend:** ran on the pinned `claude-cli` shim (Ollama disabled foundry-wide). Live
  subagent baseline recorded in the leaderboard.

## Residual gaps / fragilities

- **"No noise-only logging" restraint is judgement-bound.** The lens forbids penalizing code
  for lacking logs that would only add noise; the held-out set can't directly test that the
  agent *withholds* a downgrade on already-adequately-instrumented code. OB-005 (good
  telemetry → high band) is the closest proxy. Consider a case that is sparse-but-fine (a
  trivial pure helper with no telemetry) rated `[85,100]` to exercise the restraint.
- **Single-framework live baseline.** subagent validated end-to-end; the other three share the
  identical thin-dispatcher pattern and injected `generate`, so wiring risk is low, but a full
  four-framework parallel sweep + judge leaderboard is the remaining confidence step.
- **Leak detection breadth.** OB-003 tests password/token in a log; not yet tested: PII in a
  metric *label* (high-cardinality + privacy), or a secret in a trace attribute. The prompt
  covers them; grow the held-out set.

## Concrete improvements (not auto-applied)

1. Add a sparse-but-adequate case rated `[85,100]` to test the noise-only restraint directly.
2. Add a PII-in-metric-label case and a secret-in-trace-attribute case to broaden leak coverage.
3. Run the full four-framework parallel sweep + judge on the Claude backend to publish the
   first real leaderboard and lock the golden baseline.
