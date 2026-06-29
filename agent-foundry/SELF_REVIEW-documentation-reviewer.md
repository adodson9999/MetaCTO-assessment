# Self-Review — general / documentation-reviewer (n603)

Build of the four-framework documentation-reviewer + judge. Self-questioning pass per
forge Phase 6. Report only — nothing auto-applied.

## What was built
- Four framework agents (langgraph, crewai, claude_sdk, subagent) as thin dispatchers over
  the shared `common/runners/*`, all driving one shared, debate-gated prompt
  (`agents/common/docreview_prompt.py`) and one deterministic harness
  (`agents/common/docreview.py` + `docreview_spec.py`).
- Canonical subagent prompt `agents/general/documentation-reviewer/subagent/general-documentation-reviewer.md`,
  registered at the host repo `.claude/agents/general-documentation-reviewer.md` (relative
  symlink, single source of truth) — same convention as the working general-bug-reporter.
- Judge: `judge/general/documentation-reviewer/metric.json` (verdict_accuracy_pct) + `score.py`.
- Doc corpus fixtures (`data/.../cli/*.md`, `reference/*.md`) grounded in this repo's
  DummyJSON API, with file mtimes set to drive the newest-file source-of-truth rule.
- Labeled gold set (`data/.../gold.json`) + four bug reports in the canonical template.
- Golden suite (`tests/golden/general/documentation-reviewer/golden.json`) — 1 metric +
  6 structural cases — GOLDEN PASS.

## Verified
- All Python compiles; code-quality gate = 100 (floor 95) on every new deterministic file.
- Oracle self-test: perfect oracle → verdict_accuracy=100% AND source_of_truth_match=100%.
- Saturation guard (the recorded lesson): EMPTY emission → 0% (not 100); BAD-ENUM → 0%;
  ALL-YES → 25%. Empty/garbage output can never be credited.
- Newest-file-wins verified deterministically: limit=0 conflict ranks cli/products.md
  (2026-06-25) above reference/products.md (2026-06-10); source_of_truth = cli/products.md,
  reference/products.md in other_matches.
- Judge scorer renders a ranked leaderboard.

## Gaps / residual ambiguities (honest)
1. **No live LLM tournament run.** Phases 4 (live four-agent run) and 4.5 (10-round
   improvement loop) need a backend (Claude Code session / Ollama) up; they were NOT run
   here. The harness, judge, golden baseline (oracle=100), and run_docreview_agents.py are
   wired and ready — `python scripts/run_docreview_agents.py --workspace . && python
   judge/general/documentation-reviewer/score.py --workspace . --run-id <id>` produces the
   real leaderboard. The committed `results/general/documentation-reviewer/leaderboard-baseline.json`
   is the deterministic oracle anchor, not a live framework result.
2. **Bootstrap labels.** gold.json is a covering synthetic set (one+ example per verdict
   class) so the build verifies end-to-end now. The interview's real labeled examples drop
   in by replacing that one file — harness/scorer/golden read it verbatim.
3. **Doc folders.** The agent is built to search whatever `cli/` + `reference/` folders the
   spec points at; the committed fixtures are representative DummyJSON docs for the golden
   suite. Point `docreview_spec.json` cli_dir/reference_dir at the real folders at runtime.
4. **Verifier vs. convention.** `verify_files.py` expects `subagent/<short-name>.md`; every
   actually-built agent (incl. general-bug-reporter) uses `<group>-<name>.md` to match the
   Claude Code `name:` frontmatter. This agent follows the working convention. The verifier
   mismatch is pre-existing, not introduced here.
5. **Semantic comparison is the live agent's job.** The deterministic pre-grep + corpus
   ordering is exact; deciding yes/no/missing-docs from documented-vs-observed is the LLM's
   reasoning, scored against gold. Determinism review applies to the gated prompt lines, not
   to the model's per-report judgement (which the metric measures instead).

## Concrete improvements (not applied)
- Add a 5th/6th labeled case (a `yes` sourced from a cli/ file; a `missing-docs` where a
  near-miss keyword matches an unrelated line) to harden discrimination.
- Have the harness also score `documented_expected`/`other_matches` shape as a second
  discriminator once real labels are in.
- Wire the per-agent live leaderboard path into the judge's output so golden_run reads the
  live score directly instead of the oracle anchor.
