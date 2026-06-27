# The Judge Agent

The judge's job is to make the four agents **comparable on a hard number** — not a rubric. It invents one concrete numeric metric for the current task, ensures all four agents can emit it, measures them, and maintains a leaderboard over time.

## Judge folder layout

Each agent has its own judge subfolder inside a group folder that mirrors the agent group:

```
judge/
├── api-tester/          # all api-tester-* agents
│   └── <short-name>/    # e.g. create-postman-collection
│       ├── metric.json  # the concrete numeric metric for this agent
│       └── score.py     # scoring implementation
└── general/             # all general-* agents
    └── <short-name>/    # e.g. bug-reporter
        ├── metric.json
        └── score.py
```

When building a new agent, create the judge subfolder at the path that mirrors
the agent's group and short name. For an agent at
`agents/api-tester/create-postman-collection/`, the judge folder is
`judge/api-tester/create-postman-collection/`.

## Step 1 — Invent the metric

Given `task_spec.md`, design a single metric that is:

- **Numeric.** A real scalar, not a 1–5 vibe score and not a checklist. Examples by task type: exact-match accuracy, F1, pass@1 on a held-out set, edit distance to a reference, latency-to-correct, token cost per solved item, % of constraints satisfied.
- **Measurable on all four agents identically.** The same computation applied to each agent's output.
- **Direction-explicit.** State whether higher or lower is better.
- **Deterministic to compute** where possible (program over LLM-judgment). If the task genuinely needs model-graded scoring, the judge still emits a number, computed the same way for all four, with the grading procedure fixed and recorded.

Write the metric contract to `judge/<group>/<agent-short-name>/metric.json`:

```json
{
  "metric_name": "exact_match_accuracy",
  "direction": "higher_is_better",
  "unit": "fraction",
  "how_computed": "fraction of held-out items where agent output == reference",
  "emit_fields": ["metric_name", "metric_value", "raw_output_path"],
  "held_out_path": "results/<group>/<agent-short-name>/held_out.jsonl"
}
```

Alongside it, write `judge/<group>/<agent-short-name>/score.py` — the scoring
implementation that reads an agent's result JSON and returns the numeric value.

Because the metric is fixed *before* the agents run and is identical across them,
it doubles as the **SkillOpt validation-gate metric** (see `references/evolution.md`).
One number drives both ranking and the accept/reject gate. There is no second,
fuzzy metric anywhere.

## Step 2 — Run the four (parallel)

Invoke `scripts/run_agents.py`, which launches all four agents at once, each
writing `results/runs/<run-id>/<agent>.json`. Respect the local-model concurrency
reality: parallel is the default per the spec; the runner exposes a cap if the
local backend saturates.

## Step 3 — Score and rank

Read the four result JSONs, apply the metric from
`judge/<group>/<agent-short-name>/metric.json` via
`judge/<group>/<agent-short-name>/score.py`, and produce:

- `results/<group>/<agent-short-name>/leaderboard-<YYYYMMDDTHHMMSS>.json` — timestamped snapshot, machine-readable; source of truth for evolvers and the gate.
- `results/<group>/<agent-short-name>/leaderboard-<YYYYMMDDTHHMMSS>.md` — timestamped snapshot, human-readable leaderboard.

The leaderboard tracks results **over time** (appends each run, keeps best-so-far
per agent), so repeated runs reveal which framework is best at this task as the
agents evolve.

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

## Guardrails

These rules are **hard constraints** enforced every time the judge writes output. Violating them creates the exact structural debt that was fixed in the June 2026 reorganization.

### Results folder
1. **Never write leaderboard or held_out files to `results/` root.** Every artifact belongs inside `results/<group>/<agent-short-name>/`. Root-level leaderboard files (`leaderboard.json`, `leaderboard-<name>.json`) are the old flat pattern and must not be created.
2. **Leaderboard filenames must carry a timestamp.** Format: `leaderboard-<YYYYMMDDTHHMMSS>.json` and `.md`. This allows multiple snapshots per agent without collision. Never write a bare `leaderboard.json` or `leaderboard.md` inside an agent subfolder.
3. **`results/runs/` stays flat.** Timestamped run directories go directly under `results/runs/<run-id>/` — no agent or group subfolder under `runs/`. The per-run files are named by framework (`langgraph.json`, `crewai.json`, `claude_sdk.json`), not by agent name.
4. **Group folder must mirror the agent group.** An agent at `agents/api-tester/<name>/` writes results to `results/api-tester/<name>/`. An agent at `agents/general/<name>/` writes to `results/general/<name>/`. No exceptions.

### Naming
5. **No abbreviated folder names.** Folder names like `authz`, `clarity`, `crud`, `schema`, `status`, `versioning` are banned. Always use the full hyphenated agent short name (e.g. `check-authorization-rules`, `verify-error-message-clarity`).
6. **No agent-name prefix in the filename once inside the agent subfolder.** The parent folder already identifies the agent. `leaderboard-create-postman-collection.json` (old flat pattern) becomes `leaderboard-<ts>.json` inside `results/api-tester/create-postman-collection/`.
7. **Auth-prefixed filenames belong inside the agent subfolder.** `auth_leaderboard.json` → `results/api-tester/test-authentication-flows/leaderboard-<ts>.json`. Drop the `auth_` prefix; the subfolder path provides context.

### Judge folder
8. **Judge subfolder must exist before agents run.** Create `judge/<group>/<agent-short-name>/metric.json` and `score.py` in Step 1, before invoking `scripts/run_agents.py`. Running agents without a judge subfolder breaks the scoring step.
9. **One metric per agent subfolder.** Never write multiple `metric.json` variants into one judge subfolder. If the metric changes, version the judge subfolder (e.g. `judge/api-tester/<name>-v2/`) and update the agent and evolver references together.


## Out of scope

The judge does **not** promote a winner, archive losers, or distill skills. It
defines the metric, measures, and tracks who is best over time. What to do with
the verdict is the user's call.
