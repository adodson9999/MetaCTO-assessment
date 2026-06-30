# SELF_REVIEW — code-review-performance

Build of the single-lens performance code-review agent (group `code-review`, short name
`performance`), four frameworks + judge, cloned from the merged math-correctness sibling
substrate (module stem `perfreview`).

## What was built (and verified)

| Deliverable | Status |
|---|---|
| `agents/common/perfreview_prompt.py` (debate-gated APPROVED_LINES, shared by all four) | ✅ |
| `agents/common/perfreview_spec.py` (strict schema + band scorer; oracle) | ✅ self-tested |
| `agents/common/perfreview.py` (deterministic driver → run artifacts + emit) | ✅ |
| `agents/code-review/performance/{langgraph,crewai,claude_sdk,subagent}/run.py` | ✅ compile + import |
| `agents/code-review/performance/subagent/code-review-performance.md` | ✅ body == APPROVED_PROMPT (parity) |
| `judge/code-review/performance/metric.json` (contract from spec) | ✅ valid JSON |
| `judge/code-review/performance/score.py` (authoritative recompute + leaderboard) | ✅ ran, ranked |
| `results/code-review/performance/held_out.jsonl` (2 seed + 6 lens cases) | ✅ on disk |
| `scripts/run_perfreview_agents__code-review-performance.py` (4-agent runner) | ✅ compile |
| `data/code-review-performance/task_spec.md` | ✅ |
| `.claude/agents/code-review-performance.md` (symlink → subagent .md) | ✅ resolves |

### Held-out cases (lens coverage)
- pf-001 set-membership hash lookup `[85,100]` (seed) · pf-002 `x in b` list scan over 1e6 in a loop `[0,50]` (seed)
- pf-003 clean O(n) sum `[90,100]` · pf-004 N+1 query in a loop `[0,45]`
- pf-005 loop-invariant `config.load_factor()` hoistable `[40,80]` · pf-006 `re.compile` per-iteration `[45,85]`
- pf-007 `SELECT *` over-fetch when one column used `[55,90]`
- pf-008 nested loop over a static 3-key startup config — **negligible, must NOT flag** `[80,100]`

### Deterministic verification performed
- **Prompt parity** — subagent `.md` body (frontmatter stripped) is byte-identical to `APPROVED_PROMPT`.
- **Strict schema gate** — 9 adversarial inputs rejected (extra key, missing/empty notes, bool/float/string/out-of-range rating, non-dict); valid `{rating,notes}` accepted. Honours principle (1).
- **Band scoring** — in-band→1.0, out-of-band→0.0, schema-fail→0.0.
- **Oracle** — band-midpoint lands in band on every held-out case (golden baseline).
- **End-to-end** — synthetic oracle scores 1.0/100%, empty agent 0.0/0%, judge ranks correctly into `results/leaderboard-code-review-performance.{json,md}`.

## Gaps / residual items (honest)

1. **No live four-framework leaderboard.** No LLM backend reachable: shim (:8787), proxy
   (:4000), Ollama (:11434) all down; `claude -p` was out of credits in the prior build.
   The agents are fully wired; one-command live run below once a backend is up. Environment
   limitation, not a build defect.
2. **Determinism review (regenerate-N) + 10-round tournament not run live** — both need the
   backend. Prompt authored for determinism (temp 0, mechanical bands, identical prompt
   across all four frameworks); spec scorer is pure-Python deterministic.
3. **Brittle mid-band cases:** pf-005/006/007 (hoist/cache/over-fetch) have generous widths,
   but are where a live model is most likely to drift. pf-008 is the key discriminator for
   the "don't flag negligible/rarely-run cost" rule — if a live model over-penalises the
   tiny nested loop it lands low and fails the band, which is the signal we want. Widen
   only if a live run shows systematic drift; don't re-tune the prompt to chase a band.
4. **Active branch race continues** — built while a concurrent session held branch
   `code-review-unit-test`. Files are untracked in a shared tree; NOT committed (consistent
   with [[forge-concurrent-codereview-build]] — don't commit during a race). The held-out is
   under `results/` which the current `.gitignore` ignores; force-add it (as with the
   math-correctness sibling) when committing.

## Run the live leaderboard (once a backend is up)
```
cd agent-foundry
FORGE_PROVIDER=ollama .venv/bin/python \
  scripts/run_perfreview_agents__code-review-performance.py --workspace . --run-id auto
.venv/bin/python judge/code-review/performance/score.py --workspace . --run-id <printed-id>
```

## Verdict
Deliverable set complete and internally consistent; deterministic substrate fully tested
and green. Outstanding work is the live LLM leaderboard + determinism/tournament passes,
all blocked only by backend availability, all runnable with the single command above.
