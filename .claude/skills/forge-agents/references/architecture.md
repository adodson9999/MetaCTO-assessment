# Architecture & Workspace Layout

One self-contained workspace folder holds everything. The skill scaffolds it with `scripts/init_workspace.py`. Default name `agent-foundry/` (override with `--name`).

```
agent-foundry/
├── config.toml                 # central config: backend switch, paths, scopes
├── task_spec.md                # the current task (from the Phase 2 interview)
├── install.sh / install.ps1    # one-command setup (copied from the skill)
│
├── agents/                     # the four built implementations + shared infrastructure
│   ├── common/
│   │   └── runners/            # centralized framework runners (one per framework)
│   │       ├── langgraph_runner.py
│   │       ├── crewai_runner.py
│   │       ├── claude_sdk_runner.py
│   │       ├── subagent_runner.py
│   │       └── utils.py
│   │
│   ├── api-tester/             # group folder for all api-tester-* agents
│   │   └── <short-name>/       # e.g. create-postman-collection (api-tester- prefix dropped)
│   │       ├── langgraph/
│   │       │   └── run.py      # thin dispatcher → common/runners/langgraph_runner.py
│   │       ├── crewai/
│   │       │   └── run.py      # thin dispatcher → common/runners/crewai_runner.py
│   │       ├── claude_sdk/
│   │       │   └── run.py      # thin dispatcher → common/runners/claude_sdk_runner.py
│   │       └── subagent/
│   │           ├── api-tester-<name>.md  # canonical system prompt (YAML + gated body)
│   │           └── run.py      # thin dispatcher → common/runners/subagent_runner.py
│   │
│   └── general/                # group folder for all general-* agents
│       └── <short-name>/       # e.g. bug-reporter (general- prefix dropped)
│           └── langgraph/ crewai/ claude_sdk/ subagent/  # same layout as api-tester
│
├── judge/                      # per-agent judge metric definitions
│   ├── api-tester/             # one subfolder per api-tester agent (short name)
│   │   └── <short-name>/
│   │       ├── metric.json     # the concrete numeric metric for this agent
│   │       └── score.py        # scoring implementation
│   └── general/                # one subfolder per general agent (short name)
│       └── <short-name>/
│           ├── metric.json
│           └── score.py
│
├── memory/                     # shared EverOS store (Markdown + SQLite + LanceDB)
│   └── .everos/                # source-of-truth Markdown + local indexes
│
├── evolvers/                   # SkillOpt + SkillClaw working dirs
│   ├── skillopt/               # per-agent best_skill.md + validation gate
│   └── skillclaw/              # collective shared skills (local-FS backend)
│
├── results/                    # everything the judge reads/writes
│   ├── api-tester/             # per-agent result artifacts, grouped by agent group
│   │   └── <short-name>/       # mirrors agents/api-tester/<short-name>/
│   │       ├── held_out.jsonl                      # held-out evaluation set
│   │       ├── leaderboard-<YYYYMMDDTHHMMSS>.json  # timestamped snapshot (machine)
│   │       └── leaderboard-<YYYYMMDDTHHMMSS>.md    # timestamped snapshot (human)
│   ├── general/                # per-agent result artifacts for general-* agents
│   │   └── <short-name>/
│   │       ├── held_out.jsonl
│   │       ├── leaderboard-<YYYYMMDDTHHMMSS>.json
│   │       └── leaderboard-<YYYYMMDDTHHMMSS>.md
│   ├── _global/                # global/cross-agent artifacts (no single agent owner)
│   └── runs/                   # flat cross-agent run store (all agents, all tasks)
│       └── <YYYYMMDDTHHMMSS-xxxxxx>/
│           ├── langgraph.json          # per-framework result + metric value
│           ├── langgraph.cases.json
│           ├── crewai.json
│           ├── crewai.cases.json
│           ├── claude_sdk.json
│           └── claude_sdk.cases.json
│
├── vendor/                     # vendored, pinned upstream repos (scan-and-integrate)
│   ├── EverOS/   SkillOpt/   SkillClaw/
│
└── SELF_REVIEW.md              # written by the Phase 6 self-questioning pass
```

## Data flow (one task run)

1. **Task** → `task_spec.md` (interview).
2. **Author** → four thin dispatcher `run.py` files written per agent (one per framework), each pointing to the centralized runner in `agents/common/runners/`. The gated system prompt is written directly into `agents/<agent-name>/subagent/<agent-name>.md`.
3. **Run** → `scripts/run_agents.py` runs all four **in parallel**, each writing its metric to `results/runs/<run-id>/<agent>.json`.
4. **Judge** → reads those JSONs, applies `judge/<group>/<agent-short-name>/metric.json`, writes `results/<group>/<agent-short-name>/leaderboard-<ts>.{md,json}`.
5. **Memory** → every run's artifacts written to the shared EverOS pool (common `project_id`/`app_id`, per-agent `agent_id`).
6. **Evolve** → nightly/manual: SkillOpt sharpens each agent's `best_skill.md` behind the judge-metric gate; SkillClaw distills + shares skills across all agents.
7. **Self-review** → `SELF_REVIEW.md`.

## Sandbox boundary

All agent file I/O and process execution is confined to the workspace root. `scripts/run_agents.py` sets each agent's working directory to the workspace and passes the sandbox root in `config.toml`; agent instruction lines (gated) must forbid acting outside it. Nothing the agents do may touch paths above the workspace folder.

## Shared-memory principle

The four agents are *not* isolated. They share one EverOS pool so that what one learns is visible to the others and to any additional agents later dropped into `agents/`. Sharing is by common `project_id` + `app_id`; each agent additionally keeps its own `agent_id` track so contributions are attributable. See `references/memory-everos.md`.
