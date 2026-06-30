# SELF_REVIEW — code-review-math-correctness

Build of the single-lens math-correctness code-review agent (group `code-review`, short
name `math-correctness`), four frameworks + judge, mirroring the established
documentation-reviewer agent layout.

## What was built (and verified)

| Deliverable | Status |
|---|---|
| `agents/common/mathcorrect_prompt.py` (debate-gated APPROVED_LINES, shared by all four) | ✅ |
| `agents/common/mathcorrect_spec.py` (strict schema + band scorer; oracle) | ✅ self-tested |
| `agents/common/mathcorrect.py` (deterministic driver → run artifacts + emit) | ✅ |
| `agents/code-review/math-correctness/{langgraph,crewai,claude_sdk,subagent}/run.py` | ✅ compile + import |
| `agents/code-review/math-correctness/subagent/code-review-math-correctness.md` | ✅ body == APPROVED_PROMPT (parity) |
| `judge/code-review/math-correctness/metric.json` (contract from spec) | ✅ valid JSON |
| `judge/code-review/math-correctness/score.py` (authoritative recompute + leaderboard) | ✅ ran, ranked |
| `results/code-review/math-correctness/held_out.jsonl` (2 seed + 6 lens cases) | ✅ tracked (durable) |
| `scripts/run_mathcorrect_agents__code-review-math-correctness.py` (4-agent runner) | ✅ compile |
| `data/code-review-math-correctness/task_spec.md` | ✅ |
| `.claude/agents/code-review-math-correctness.md` (symlink → subagent .md) | ✅ resolves |

### Deterministic verification performed
- **Prompt parity** — subagent `.md` body with frontmatter stripped is byte-identical to
  `APPROVED_PROMPT`, so `load_system_prompt` fallback and `active_prompt()` agree.
- **Strict schema gate** — 9 adversarial inputs (extra key, missing notes, empty notes,
  bool rating, float rating, out-of-range, string rating, non-dict) all rejected; valid
  `{rating, notes}` accepted. Honours project principle (1): non-`{rating,notes}` → 0.0.
- **Band scoring** — in-band → 1.0, out-of-band → 0.0, schema-fail → 0.0.
- **Oracle** — band-midpoint decision lands in band on every held-out case (golden baseline).
- **End-to-end** — synthetic oracle agent scores 1.0/100%, an empty agent 0.0/0%, and the
  judge ranks them correctly into `results/leaderboard-code-review-math-correctness.{json,md}`.

## Gaps / residual items (honest)

1. **No live four-framework leaderboard was produced.** No LLM backend was reachable in this
   environment: the claude-cli shim (:8787), LiteLLM proxy (:4000), and Ollama (:11434) are
   all down, and `claude -p` returns "Credit balance is too low." The langgraph/crewai/
   claude_sdk runners additionally need `ANTHROPIC_API_KEY` (ChatAnthropic) under the
   `anthropic` native path. The agents are fully wired; the live run is a one-command step
   once a backend is up — see below. **This is an environment limitation, not a build defect.**
2. **Determinism review (regenerate-N-times) and the 10-round improvement tournament were not
   run live** — both require the LLM backend. The prompt is authored for determinism (temp 0,
   bands resolved mechanically, identical prompt across all four frameworks), and the spec
   scorer is pure-Python and deterministic, but cross-generation convergence is unverified
   against a live model here.
3. **Mid-band held-out cases (mc-006 float-eq [40,75], mc-007 O(n²) [55,89]) are the brittle
   ones.** Clear-cut high/low cases (clean function → [90,100]; crash-on-empty / never-
   terminates / always-IndexError → [0,40-45]) are robust; the two mid-band cases have
   deliberately generous widths but are where a live model is most likely to drift out of
   band. If a live run shows drift, widen those two bands rather than re-tune the prompt.
4. **Concurrent working-tree mutation observed.** During the build, sibling agents
   (`device-stack`, `system-design`) appeared and my untracked `held_out.jsonl` was removed —
   consistent with another session running `git clean`/`checkout` on the same tree. Fixed
   durably by whitelisting the held-out in `.gitignore` and `git add`-ing it (mirroring the
   `minimalist` precedent), so it is now a tracked contract fixture that survives a clean.

## Run the live leaderboard (once a backend is up)
```
cd agent-foundry
# Option A — local, air-gapped:  ollama serve && ollama pull qwen2.5:14b-instruct
FORGE_PROVIDER=ollama .venv/bin/python \
  scripts/run_mathcorrect_agents__code-review-math-correctness.py --workspace . --run-id auto
# then (run-id is printed by the runner):
.venv/bin/python judge/code-review/math-correctness/score.py --workspace . --run-id <run-id>
```

## Verdict
Deliverable set complete and internally consistent; deterministic substrate fully tested and
green. Outstanding work is the live LLM leaderboard + determinism/tournament passes, all
blocked only by backend availability, all runnable with the single command above.
