# The Judge Agent

The judge's job is to make the four agents **comparable on a hard number** — not a rubric. It invents one concrete numeric metric for the current task, ensures all four agents can emit it, measures them, and maintains a leaderboard over time.

## Step 1 — Invent the metric

Given `task_spec.md`, design a single metric that is:

- **Numeric.** A real scalar, not a 1–5 vibe score and not a checklist. Examples by task type: exact-match accuracy, F1, pass@1 on a held-out set, edit distance to a reference, latency-to-correct, token cost per solved item, % of constraints satisfied.
- **Measurable on all four agents identically.** The same computation applied to each agent's output.
- **Direction-explicit.** State whether higher or lower is better.
- **Deterministic to compute** where possible (program over LLM-judgment). If the task genuinely needs model-graded scoring, the judge still emits a number, computed the same way for all four, with the grading procedure fixed and recorded.

Write the metric contract to `judge/metric.json`:

```json
{
  "metric_name": "exact_match_accuracy",
  "direction": "higher_is_better",
  "unit": "fraction",
  "how_computed": "fraction of held-out items where agent output == reference",
  "emit_fields": ["metric_name", "metric_value", "raw_output_path"],
  "held_out_path": "results/held_out.jsonl"
}
```

Because the metric is fixed *before* the agents run and is identical across them, it doubles as the **SkillOpt validation-gate metric** (see `references/evolution.md`). One number drives both ranking and the accept/reject gate. There is no second, fuzzy metric anywhere.

## Step 2 — Run the four (parallel)

Invoke `scripts/run_agents.py`, which launches all four agents at once, each writing `results/runs/<run-id>/<agent>.json`. Respect the local-model concurrency reality: parallel is the default per the spec; the runner exposes a cap if the local backend saturates.

## Step 3 — Score and rank

Read the four result JSONs, apply `metric.json`, and produce:

- `results/leaderboard.json` — machine-readable, the source of truth for evolvers and the gate.
- `results/leaderboard.md` — a human leaderboard of all four agents.

The leaderboard tracks results **over time** (appends each run, keeps best-so-far per agent), so repeated runs reveal which framework is best at this task as the agents evolve.

### Leaderboard.md format

```markdown
# Leaderboard — <task short name>
Metric: <metric_name> (<direction>)  ·  Updated: <iso8601>

| Rank | Agent                | This run | Best so far | Runs |
|------|----------------------|----------|-------------|------|
| 1    | crewai               | 0.81     | 0.83        | 7    |
| 2    | claude_sdk           | 0.79     | 0.82        | 7    |
| 3    | langgraph            | 0.77     | 0.80        | 7    |
| 4    | claude_code_subagent | 0.74     | 0.78        | 7    |
```

## Out of scope

The judge does **not** promote a winner, archive losers, or distill skills. It defines the metric, measures, and tracks who is best over time. What to do with the verdict is the user's call.
