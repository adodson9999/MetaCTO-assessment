---
description: "Forge four implementations of one task (LangGraph, CrewAI, Claude Code subagent, Claude Agent SDK) plus a judge that invents a numeric metric and ranks them. Every agent line passes the four-member debate gate."
allowed-tools: Read, Write, Edit, Bash, Glob, Grep
---

# /forge-agents

Run the Forge Agents workflow defined in the `forge-agents` skill (`SKILL.md`). Follow its phases in order and read the referenced files at each phase — do not improvise the debate gate or the judge.

$ARGUMENTS

## Checklist

1. **Dependencies present?** If `vendor/EverOS`, `vendor/SkillOpt`, `vendor/SkillClaw` are missing, invoke the user's existing **`/scan-and-integrate`** skill first (it is a separate skill, not part of this package), passing each repo URL + stated purpose.
2. **Workspace present?** If not, run `scripts/init_workspace.py` and the installer.
3. **Interview** the user for the task → `task_spec.md`.
4. **Author** the four agents, every line through the debate gate (`references/debate-gate.md`). Save clean prompt + debate log per agent to `agent_built_prompts/`.
5. **Build the judge** (`references/judge.md`): invent the numeric metric → `judge/metric.json`.
6. **Run** all four in parallel (`scripts/run_agents.py`); **judge** → `results/leaderboard.{md,json}`.
7. **Wire evolution** (`references/evolution.md`): SkillOpt + SkillClaw, nightly + manual, gated by the judge metric, staged for review.
8. **Self-review** (`references/self-review.md`) → `SELF_REVIEW.md`. Report; do not auto-apply.

Stop and ask the user the moment the debate gate finds any line with more than one interpretation. There is no iteration cap.
