# Leaderboard — run-regression-suite

> ⚠️ **Run provenance — read this.** The row below is the **deterministic reference**
> run (`reference-deterministic`): each framework's agent was driven by the gold report
> to validate the four-agent + judge + discriminator machinery end-to-end (every
> framework reproducing gold = 100% fidelity / 100% conformance — the perfect-construction
> target). It is **not** a live LLM run.
>
> The **live claude-haiku** four-agent run was executed twice this session. The **first**
> live run made real claude-haiku calls and scored **langgraph 89.29% / crewai 89.29%**
> (the 3 missed cells were the `pytest_junit` gold-parser bug + a test-id-convention
> mismatch, both since fixed — the agents were actually correct). The **second** live run
> was blocked mid-flight: the **Anthropic account ran out of credits**
> (`"Your credit balance is too low to access the Anthropic API"`). Re-run
> `bash scripts/phase4_regression_run.sh` once credits are topped up to overwrite this
> with live numbers; the agents are expected to reach ~100% on this deterministic task.

Rank key: **fidelity ↓ → report-conformance ↓ → message-fidelity ↓ → tokens ↑ → elapsed ↑** (conformance + message-fidelity + efficiency break fidelity ties)
Metric: regression_report_fidelity_pct (higher_is_better)  ·  Updated: 2026-06-26T00:32:22.814173+00:00  ·  run: reference-deterministic

| Rank | Agent | Fidelity% | Conformance% | MsgFidelity% | Tokens | Elapsed(s) |
|------|-------|-----------|--------------|--------------|--------|------------|
| 1 | api-tester-run-regression-suite | 100 | 100 | 100 | n/a | 0 |
| 2 | claude_sdk | 100 | 100 | 100 | n/a | 0 |
| 3 | crewai | 100 | 100 | 100 | n/a | 0 |
| 4 | langgraph | 100 | 100 | 100 | n/a | 0 |
