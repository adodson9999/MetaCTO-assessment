# SELF_REVIEW — code-review / device-stack

Single-lens code-review agent. Lens: does the code still work under real hardware and OS
behavior. Output contract: exactly one bare `{"rating": <int 0-100>, "notes": <non-empty>}`.
Built by cloning the validated `math-correctness` sibling (same group, same `{rating,notes}`
contract, same `rating_band_accuracy` metric) and substituting the device-stack lens.

## What shipped
- Common trio: `agents/common/devicestack{,_spec,_prompt}.py` (deterministic driver, spec/
  scoring/oracle, debate-gated 12-line prompt). No LLM in the plumbing — identical substrate
  for all four frameworks.
- Four frameworks: `langgraph/`, `crewai/`, `claude_sdk/`, `subagent/` thin dispatchers +
  canonical `subagent/code-review-device-stack.md`.
- Judge: `judge/code-review/device-stack/metric.json` + `score.py` (band-accuracy →
  schema-pass → tokens → elapsed).
- Held-out: 8 cases (`results/code-review/device-stack/held_out.jsonl`), seeds disjoint.
- Golden: `tests/golden/code-review/device-stack/golden.json` — structure self-test PASS.
- Registration: `.claude/agents/code-review-device-stack.md` → canonical prompt (symlink,
  resolves).

## Gates
- Golden/oracle self-test: PASS — oracle (band midpoint) saturates at 1.0; empty `{}` scores
  0.0; strict schema rejects extra-key / bool / float / out-of-range / empty-notes; seed
  bands disjoint; worst-case constant-rating ceiling 0.5 over all 8 cases.
- Output contract / file completeness: PASS — all 16 deliverables present, all Python
  byte-compiles, metric.json + held_out parse.
- Live run (`all_emitted: true`): four agents scored against the held-out set. **Schema-pass
  100% on every case across all four frameworks** — the hard contract held.

## Live leaderboard (local Ollama qwen2.5:14b backend)
crewai 0.5 · langgraph 0.375 · device-stack(subagent) 0.375 · claude_sdk 0.375 — all
schema-pass 100%.

## Findings / residual notes
1. **Backend hazard (important).** The Claude-CLI subagent path (`subagent_runner` →
   `claude -p` with `cwd=workspace`) spawned a nested Claude Code session that wiped
   `results/runs/` mid-run — matches the existing memory `forge-concurrent-codereview-build`
   ("results/ fixtures are fragile"). Ran the scored pass on `FORGE_PROVIDER=ollama`
   (no nested session) and it was stable. Recommendation: always score the held-out set on
   the local backend; reserve the live `claude -p` subagent path for interactive use.
2. **Band calibration is correct; the local model is lenient.** qwen-14b nailed both
   device-safe cases (ds-001 monotonic, ds-003 pure fn → 100) but defaulted broken code to a
   flat 75 (ds-002 wall-clock timeout, ds-004 buffer overflow, ds-005 endianness, ds-007
   non-atomic write all under-penalized). Misses are entirely in the too-generous direction —
   the oracle saturates the bands at 1.0, so the bands are right; the gap is model capability.
   Phase 4.5 (tournament / SkillOpt) is what lifts live accuracy; baseline note permits
   re-baselining if a framework stabilizes below 1.0.
3. **Not run:** Phase 4.5 improvement tournament, Phase 5 evolution wiring, and `/fight-camp`
   per-framework divergence — deferred (no live-accuracy gate blocks build completion). Run
   `/fight-camp` or `/evolve` to push live band accuracy up from the 0.375–0.5 floor.
4. **Did not git-commit** — the memory warns against committing during a concurrent
   code-review build race; the working tree carries the build.
