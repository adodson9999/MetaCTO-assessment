# SELF_REVIEW — general / bug-reporter ("n602")

Phase-6 self-questioning pass. Findings only — nothing here is auto-applied.

## What was built

The four-framework forge (LangGraph / CrewAI / Claude Code subagent / Claude Agent SDK)
+ judge for the Bug-Reporter task, mirroring the `general-run-cicd-pipeline` (n599)
template exactly. The agent is the **analytical core**: per non-PASSED pipeline agent it
emits a five-key bug-report decision (title, severity via the nine ordered rules,
priority, mapped testing_steps, postman_references with constructed v2.1 new_items). The
shared harness materialises the file artifacts (replay screenshot, asciinema recording,
logs; DB dump skipped — no `[database]`), assembles `[BUG_ID].json` + `index.json`,
scores fidelity vs gold, and records the task gate metrics. Backend = Ollama; the server
is never started; DummyJSON is never touched.

## Verification done (deterministic, no LLM / no server)

- `build_gold.py` → 9 failures, severity rules R1..R9 each fire as intended
  (CRITICAL=3, HIGH=3, MEDIUM=2, LOW=1; must_exit_1=true).
- Harness oracle (returns the gold decision) → **100% fidelity (45/45)**, completeness
  90%, mandatory 100%, testing-steps 100%, exit1=true.
- Degraded generator (wrong title + new_items flattened to existing) → **73.33%**, ranks
  last. Judge → leaderboard discriminates and ranks strictly.
- `py_compile` + `bash -n` clean across all runners, judge, runner, build_gold, gate
  authoring, phase4 script. Both registration symlinks resolve to the frontmatter
  `name: general-bug-reporter`. 16 gated lines × 4 frameworks → prompts byte-match the
  approved lines; debate trails written.

## Gaps / weak spots (HIGH → LOW)

- **HIGH — no live ranking yet.** Per the owner ("do not start the server / just create
  the agent"), no live Ollama pass was run, so the leaderboard reflects only the
  deterministic oracle wiring proof (removed after verifying). Real framework numbers
  await `ollama serve` + `bash scripts/phase4_bugreport_run.sh`. The smaller, JSON-heavy
  new_item objects are the most likely place a 14B local model diverges (nested Postman
  v2.1 structure + verbatim test-script strings) — expect fidelity, not 100%, on the
  live run; that is the metric working as intended.

- **MEDIUM — Postman Reference Rate is 72.73%, below the task's 90% gate, by design.**
  Two HTTP cases are intentionally absent from the collection to exercise the new_item
  path. This is an honest fixture characteristic, not a bug: it surfaces the genuine
  "new items need manual review" finding. If a clean ≥90% demo is wanted, move
  `tc-pipe-001` / `tc-webhook-001` into the collection fixture — but that would stop
  exercising the agent's richest analytical work (new_item construction), which is the
  main fidelity discriminator. Recommend keeping it and documenting the 72.73%.

- **MEDIUM — the agent never writes files or sets the exit code.** Faithful to the
  foundry's debate-gated split (the agent emits the decision; the harness materialises
  and the CI program exits), but it means the task's literal "the agent writes
  `[BUG_ID].json`" and "exit 1" are the *harness's* behaviour here, recorded as
  `would_exit_code_1`. Same precedent as run-cicd-pipeline (records
  `runs_that_must_block_deployment`) and run-regression-suite. If the owner wants the
  agent itself to own the writes, that is a different (non-air-gapped, non-gated) design.

- **LOW — `created_at` is fixture-stable, not wall-clock.** The harness stamps a
  deterministic `created_at` so gold/oracle runs are reproducible (real
  `datetime.utcnow()` would make the recording timestamp + report non-deterministic and
  break the self-test). A production n602 would use real UTC; documented in the harness.

- **LOW — screenshot/recording fallbacks.** ImageMagick `convert` and `ansi2html` are
  not assumed present in the air-gapped sandbox, so Artifact 3 is the spec's documented
  final fallback (the plain-text replay file) and Artifact 4 is the pure-Python asciinema
  v2 cast. Both always succeed; no PNG/HTML is produced. If those binaries are installed,
  a future harness pass could upgrade Artifact 3 to a real PNG without touching the agent.

- **LOW — metric saturation risk.** As with the other deterministic reporters
  (cicd/postman/softdelete), four correct agents tie at 100% fidelity; completeness also
  ties (fixture-determined), so on the live run the real separation falls to tokens →
  elapsed. Same known limitation flagged across the foundry; a latency/token tie-breaker
  is already the rank tail.

## Evolution (Phase 5)

Inherits the foundry's generic SkillOpt + SkillClaw wiring (`evolvers/evolve.py` +
`config.toml [evolution]`, nightly + manual `/evolve`, staged, never auto-adopted). The
judge metric (Bug-Report Fidelity over the held-out fixture via
`FORGE_HELDOUT_FIXTURE`) is the validation gate. No dedicated `evolve_bugreport.py` was
added — matching the n599/n600/n601 trio, which also defer to the generic evolver.
