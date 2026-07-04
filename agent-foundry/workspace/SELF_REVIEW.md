# Self-Review — api-tester foundry (update batch prep)

Scope: bring the 39 api-tester agents up to standard via the update-agent skill,
with the code-review gate skipped (FORGE_SKIP_CODE_REVIEW) per operator directive.

## State
- Run-output layer regenerated for all api-tester + general judged agents
  (leaderboards + receipts) after a prior reorg deleted it.
- Orchestration paths repaired flat->nested (lane runners, scorers, generic
  run_agents.py --only dispatch); thin-dispatcher runners fixed (active_prompt import);
  tls execution harness hardened.
- Code-review reviewer group intentionally out of scope for this batch.

## Known residual
- Some heavy agents (validate-request-payloads, 558 gold cases) are slow on the
  claude-cli shim and were run with an extended timeout.
