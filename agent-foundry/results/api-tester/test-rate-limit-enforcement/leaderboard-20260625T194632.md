# Leaderboard — rate_limit_test_fidelity (higher_is_better)

**Status: awaiting a valid four-agent run (blocked on Anthropic API credits).**

The deterministic gold reference + shared harness are validated to **100%** against
DummyJSON's real, active limiter (every endpoint trips at exactly request **101**, with
`Retry-After`, in-window 429, after-window reset — Rate Limit Trigger Precision = **PASS**).

A single-endpoint harness check produced **8/8 = 100%** scenario correctness. The four
agents (LangGraph, CrewAI, Claude Code subagent, Claude Agent SDK) all emitted valid
eleven-key plans in earlier runs, proving the plumbing end-to-end — but the **final
ranked run requires Anthropic credits** (backend = `claude-haiku` per instruction; balance
exhausted 2026-06-25). Prior leaderboard rows were against the pre-correction config
(limiter assumed absent) and have been cleared as non-comparable.

**To finish:** add API credits, then `bash scripts/phase4_ratelimit_run.sh`.
