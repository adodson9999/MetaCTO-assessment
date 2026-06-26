# SELF_REVIEW — general / run-cicd-pipeline ("CI/CD Pipeline Runner")

Phase-6 self-critique of the build. Findings only — nothing auto-applied.

## What was built (and verified)

- Four framework implementations of one task (LangGraph, CrewAI, Claude Code subagent,
  Claude Agent SDK) under `agents/general-run-cicd-pipeline/`, all eliciting the SAME
  14-line debate-gated prompt and sitting on one shared deterministic harness
  (`agents/common/cicd.py`).
- The judge invents a hard numeric metric — **Pipeline-Summary Fidelity** (% of
  scenario×field cells matching gold), tie-broken by report-conformance → tokens →
  elapsed — and renders `results/leaderboard-run-cicd-pipeline.{json,md}`.
- Deterministic gold + four scenario fixtures (`data/run-cicd-pipeline/`), debate trail
  (`agent_built_prompts/general/run-cicd-pipeline/*.debate.md`), subagent registered
  at foundry + host scope.
- **Verified deterministically (no LLM, no server):** gold classification correct for
  all four scenarios; harness→judge path ranks perfect=100%/100%, degraded=95%/83.33%,
  empty=15%/0%. py_compile + `bash -n` clean. Backend resolves to ollama (air-gapped).
  Ollama server NOT started; DummyJSON untouched; config.toml unchanged.

## Gaps / weak spots

- **HIGH — no live ranking yet.** The four frameworks have only been exercised against
  the deterministic harness with mock generators. A real leaderboard needs a
  user-started local Ollama (`ollama serve` + `ollama pull llama3.1:8b`) — deliberately
  not started here per the owner's instruction. Until then the leaderboard reflects
  fixtures + plumbing, not framework skill.
- **MEDIUM — correctness saturates.** The task is deterministic and the prompt is
  tightly gated, so all four frameworks will likely tie at/near 100% fidelity on a live
  run; the ranking then rests entirely on report_conformance + efficiency. That is by
  design (mirrors run-regression-suite) but means the headline metric discriminates
  weakly — watch conformance as the real differentiator.
- **MEDIUM — the analytical/deterministic split is a modelling choice.** The literal
  task is an orchestrator (install/serve/spawn/kill/exit). This build measures only its
  analytical core (classify + summarize) and assigns the rest to a separate program,
  exactly as run-regression-suite assigns deploy/exit-code to the harness. Defensible
  and debate-gated (L12), but a reviewer expecting the agent to actually spawn
  subprocesses would see a scope gap. The task_spec documents the fork explicitly.
- **LOW — fixture coverage.** Four scenarios cover all four categories, the
  enabled-filter, empty-stdout-as-malformed, and the timed-out-precedence edge. Not
  covered: a manifest with zero enabled agents (pass_rate→0 guard exists but untested
  end-to-end), a malformed manifest (non-array / missing `name`), and >8 agents
  spanning 3+ batches. Add these if the live run looks too easy.
- **LOW — `model` field source.** The gated prompt copies `model` from the `[backend]`
  block in the brief, not from the foundry's own `config.toml` `ollama_model`. Correct
  for the task (it reports the pipeline-under-test's configured model), but means the
  emitted `model` ("llama3.1:8b") differs from the model that actually ran the agent
  (`qwen2.5:14b-instruct`) — intended, noted here so it is not mistaken for a bug.

## Concrete improvements (for the user to weigh)

1. Start Ollama locally and run `scripts/phase4_cicd_run.sh` for the first real ranking.
2. Add the zero-enabled, malformed-manifest, and 3-batch scenarios to `cicd_spec.SCENARIOS`.
3. If frameworks tie at 100%, lean on conformance in the metric weighting (already the
   primary tiebreaker) or add a token-budget scenario to stress efficiency.
