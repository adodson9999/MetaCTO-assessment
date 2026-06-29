# Per-Framework Experiments

Four independent experiments, one per framework. Same task, same metric, same
held-out split, same budget — **independent prompt state**. This is the autoresearch
keep-if-improved loop run four times in four sealed corners.

## Why per-framework prompts diverge

A prompt encodes *how* to do the task in a way a specific framework's control flow
and tool surface can execute. LangGraph's graph nodes, CrewAI's role/task framing,
the Claude Agent SDK's tool loop, and a Claude Code subagent's system prompt reward
different phrasings, orderings, and amounts of structure. Forcing one shared prompt
under-serves at least three of the four. Fight Camp optimizes each independently so
the leaderboard reflects **best-achievable-per-framework**, not best-shared-prompt.

The comparison stays fair because the *invariants of the contest* are fixed: the
task, the metric, the evaluation data, and the run budget are identical. Only the
controllable the user cares about — the prompt — is allowed to adapt.

## One experiment (one framework)

```
state: best_prompt := framework's current prompt
       best_score  := judged score of best_prompt
for round in 1..R (default 10, config [fight_camp].rounds):
    candidate := best_prompt + ONE bounded edit
                 (add/delete/replace a line; informed by THIS framework's last
                  result and the judge metric — never by other fighters' prompts)
    if debate_gate(changed lines) fails:        discard, retry
    if determinism_review(candidate) == non-det: discard, retry
    if slop_scan(regenerated files) < 95:        rewrite, retry
    score := judge(run framework with candidate, fixed budget)
    if score >= best_score:  best_prompt, best_score := candidate, score   # KEEP
    else:                    discard                                       # DISCARD
    log {round, edit, score, kept}
write evolvers/fight-camp/<framework>/best_prompt.md, trajectory-<ts>.json
```

Monotonic by construction: a fighter's score never regresses across its camp.

## Fixed budget (comparability)

Every round for every framework runs under identical conditions, autoresearch-style:
same held-out set, same backend (session → Ollama), same parallelism cap, same
per-run time/iteration cap (`config [fight_camp].eval_budget`). The only variable is
the prompt edit. Without a fixed budget, a "better" score could just be more compute.

## Independence and isolation

- During training, fighters **do not** read each other's prompts. Cross-pollination
  (taking CrewAI's winning trick and trying it on LangGraph) is a *separate, opt-in*
  step handled by SkillClaw after the camp, staged for user review — never automatic
  inside a sealed round.
- Each framework owns its own `best_prompt.md` and trajectory. Deleting or rerunning
  one fighter's camp never touches another's.

## Writing winners back (Phase C)

After a fighter converges, its `best_prompt.md` is written into the live agent:
- **claude_subagent** → `agents/<g>/<n>/subagent/<n>.md` body (re-gated lines only);
  the `.claude/agents/<n>.md` registration is re-verified by `verify_files.py`.
- **langgraph / crewai / claude_sdk** → the prompt the framework's runner loads
  (`active_prompt` / system prompt), via the existing thin-dispatcher path.

The four agents now legitimately carry **different prompts**. That is the intended
end state, and the output contract (`verify_build.py`) validates it as complete and
well-formed exactly as for any build — divergent prompts are not a defect here.

## Determinism every round (mandatory)

Per constitution Article I.8, every round's candidate prompt and judged score pass a
determinism review. A score that "improved" only on an unstable sample is not a real
improvement and the edit is discarded. This keeps the monotonic trajectory honest.

## Config

```toml
[fight_camp]
rounds      = 10        # per framework
eval_budget = "fixed"   # identical across rounds/frameworks
parallel    = true      # run the four camps in parallel up to backend cap
frameworks  = ["langgraph", "crewai", "claude_sdk", "claude_subagent"]
```
