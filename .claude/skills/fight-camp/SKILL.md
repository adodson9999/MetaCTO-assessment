---
name: fight-camp
description: "Run a separate autoresearch-style improvement experiment for EACH of the four agent frameworks (LangGraph, CrewAI, Claude Agent SDK, Claude Code subagent) so every framework continuously improves against the judge — and each is allowed to evolve its OWN distinct prompt, because a prompt that wins for one framework may lose for another. The task and the judge's hard metric stay identical across all four (fair comparison); only the per-framework prompt is optimized independently, keep-if-improved, over many rounds. Produces one best prompt per framework, a per-framework score trajectory, and a cross-framework leaderboard of best-achievable performance. Use this skill whenever the user wants to 'run fight camp', train the frameworks, optimize each framework's prompt separately, run per-framework experiments, find the best prompt for each framework, squeeze the most out of every framework on a task, or continuously improve the four forge agents independently. Pairs with the forge-agents skill (which builds the four agents + judge); fight-camp is the training camp that makes each one as strong as it can be."
---

# Fight Camp

Forge-agents builds four implementations of one task and a judge that scores them.
**Fight Camp is the training camp.** It takes those four frameworks and runs a
**separate experiment for each one** — LangGraph, CrewAI, Claude Agent SDK, Claude
Code subagent — improving each continuously against the judge. Crucially, **each
framework may end up with a different prompt**: the experiments are independent, so
a prompt that is great for CrewAI but mediocre for LangGraph is kept for CrewAI and
discarded for LangGraph.

Think of it literally as a fight camp: four fighters, four corners, four training
plans — one referee (the judge) and one scorecard (the metric). The fighters do not
have to train the same way; they only fight the same fight.

## What stays identical vs. what diverges

| Held identical across all four (fair comparison) | Optimized independently per framework |
|--------------------------------------------------|----------------------------------------|
| the **task** (`task_spec.md`)                     | the **prompt / skill doc** |
| the judge's **metric** + `score.py`               | the prompt's structure, examples, ordering |
| the **held-out** evaluation split                 | framework-specific phrasing & tool rules |
| the **fixed run budget** (so rounds compare)      | the number of useful rounds (each converges differently) |

This answers a sharper question than a single shared prompt can: *given each
framework its best shot, which one does this task best?*

## Relationship to forge-agents

Fight Camp **depends on a built foundry** (run forge-agents first). It reuses the
foundry's gates and scripts — it does not reimplement them:

- debate gate (`references/debate-gate.md` in forge-agents) for every changed line,
- determinism review (`scripts/determinism_check.py`) every round,
- 95-floor code-quality gate (`scripts/slop_scan.py`) on every generated file,
- the judge + `scripts/run_agents.py` for scoring,
- file-completeness + output-contract guardrails (`scripts/verify_build.py`,
  `scripts/verify_files.py`) at the end.

It generalizes forge-agents **Phase 4.5** (the 10-round tournament): that phase, run
through Fight Camp, becomes four independent per-framework tournaments with
divergent prompt state instead of one shared one.

## The constitution still governs

Everything in `references/constitution.md` (forge-agents) holds. In particular:
Article I.8 (determinism review on every AI artifact), Article II (95 code-quality
floor → rewrite below), Article V (built for the simplest model; only the debate
gate and a guardrail failure halt), Article VI (backend = current Claude Code
session → Ollama fallback). Fight Camp may diverge prompts **but may never weaken
an invariant** — same task, same metric, all gates intact.

## Procedure

Read `references/experiments.md` for the full spec. Control flow:

### Phase A — Set the camp up
1. Confirm a built foundry exists (`scripts/verify_build.py --phase 4` passes).
2. Snapshot each framework's current prompt as that fighter's **round-0 baseline**
   and record its current judged score.
3. Create independent camp state per framework under
   `evolvers/fight-camp/<framework>/` — its own `best_prompt.md` and trajectory.

### Phase B — Train each fighter (four independent experiments)
For **each** framework, run its own keep-if-improved experiment (default 10 rounds,
configurable). The four experiments are independent and may run in parallel up to
the local backend's concurrency cap. Each round, for that framework only:

```
1. PROPOSE  — propose ONE bounded edit to THIS framework's prompt, informed by the
              judge metric + this framework's last result (not the others').
2. GATE     — every changed line re-passes the debate gate.
3. DETERMINISM — the revised prompt gets a determinism review.
4. QUALITY  — any regenerated file must score >= 95 (else rewrite).
5. RUN      — run THIS framework against the judge under the fixed budget.
6. KEEP/DISCARD — keep the edit only if THIS framework's score improves (else
                  discard and retry). Prompts diverge legitimately here.
7. LOG      — append {round, edit, score, kept} to this framework's trajectory.
```

Fighters never copy each other's prompts during training (that is SkillClaw's job
later, and it is opt-in). Each corner is sealed.

### Phase C — Weigh-in and scorecard
1. Write each framework's surviving `best_prompt.md` back into its agent
   (`subagent/<name>.md` for the subagent fighter; the runner-loaded prompt for the
   others) so the four agents now legitimately carry **different** prompts.
2. Re-derive each framework's golden baseline (`scripts/golden_run.py --derive`) at
   its new best.
3. Emit the **cross-framework leaderboard**: each framework's best-evolved score,
   round count, and a link to the prompt that achieved it.
4. Run `verify_build.py --phase 6` + `verify_files.py`: the divergent prompts and
   their new registrations must still satisfy the full output contract — including
   every `.claude/agents/<name>.md` registration.

## Output

```
evolvers/fight-camp/
├── langgraph/      best_prompt.md  trajectory-<ts>.json
├── crewai/         best_prompt.md  trajectory-<ts>.json
├── claude_sdk/     best_prompt.md  trajectory-<ts>.json
└── claude_subagent/best_prompt.md  trajectory-<ts>.json
results/_global/
└── fight-camp-<ts>.{json,md}   # cross-framework best-achievable leaderboard
```

### fight-camp-<ts>.md format
```markdown
# Fight Camp — <task short name>
Metric: <metric_name> (<direction>)  ·  Updated: <iso8601>
Each fighter trained independently; prompts diverge by design.

| Rank | Framework        | Baseline | Best evolved | Rounds | Prompt |
|------|------------------|----------|--------------|--------|--------|
| 1    | crewai           | 0.74     | 0.88         | 9      | evolvers/fight-camp/crewai/best_prompt.md |
| 2    | claude_sdk       | 0.79     | 0.86         | 10     | evolvers/fight-camp/claude_sdk/best_prompt.md |
| 3    | langgraph        | 0.71     | 0.83         | 8      | evolvers/fight-camp/langgraph/best_prompt.md |
| 4    | claude_subagent  | 0.70     | 0.81         | 10     | evolvers/fight-camp/claude_subagent/best_prompt.md |
```

## Trigger

`/fight-camp` runs the whole thing. `forge fight-camp` (CLI) maps to
`scripts/fight_camp.py`. `/fight-camp <framework>` trains a single fighter.
