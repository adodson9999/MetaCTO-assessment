# Leaderboard — audit_log_test_fidelity (higher_is_better)
Updated: 2026-06-26T00:34:55.053796+00:00  ·  run: oracle-verify

| Rank | Agent | This run | Best so far | Runs |
|------|-------|----------|-------------|------|
| 1 | api-tester-verify-audit-log-generation | 100 | 100 | 1 |
| 2 | claude_sdk | 100 | 100 | 1 |
| 3 | crewai | 100 | 100 | 1 |
| 4 | langgraph | 100 | 100 | 1 |

> **Run `oracle-verify`** drives the harness with the debate-gated *reference* plan (what a perfect agent emits) to verify the execute→score→leaderboard pipeline: **fidelity 100% (54/54)**, **Audit Log Coverage Rate 0%** (DummyJSON has no audit log — the honest finding). A live four-agent Claude run via `scripts/phase4_auditlog_run.sh` is ready but currently **blocked by Anthropic API credits** (`400 — credit balance is too low`); rerun it once credits are topped up to populate per-framework live numbers.
