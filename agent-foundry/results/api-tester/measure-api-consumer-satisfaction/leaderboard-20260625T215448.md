# Leaderboard — nps_measurement_plan_fidelity (higher_is_better)
Updated: 2026-06-26T02:54:02.910745+00:00  ·  run: 20260626T025359-80e41a

| Rank | Agent | This run | Best so far | Runs |
|------|-------|----------|-------------|------|
| 1 | api-tester-measure-api-consumer-satisfaction | 0 | 0 | 1 |
| 2 | claude_sdk | 0 | 0 | 1 |
| 3 | crewai | 0 | 0 | 1 |
| 4 | langgraph | 0 | 0 | 1 |

> **Provenance note.** This run's 0.00 fidelity for all four agents is an EXTERNAL
> billing block, NOT agent quality: every Claude call returned HTTP 400 "Your credit
> balance is too low to access the Anthropic API," so each agent emitted an empty plan
> (which the corrected, strict metric scores 0). The deterministic pipeline is verified
> end-to-end: injecting the canonical reference plan scores **26/26 = 100%** fidelity
> (NPS = +22, valid, 45.0% response rate, top-3 theme sizes 16/13/11), and a subtly-wrong
> plan (detractor band 0-5, k=5, 30-day window) scores **69.23%** — so the metric is
> sound and discriminating. Re-run `scripts/phase4_nps_run.sh` once Anthropic credits are
> restored for live framework numbers. Backend = claude-haiku (no ollama). DummyJSON
> untouched.
