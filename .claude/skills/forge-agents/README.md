# Forge Agents

Build **four implementations of one task** — LangGraph, CrewAI, a Claude Code subagent, and the Claude Agent SDK — plus a **judge** that invents a concrete numeric metric (not a rubric) and ranks them on a leaderboard that tracks who's best over time. Every instruction line that defines any agent must survive a **four-member debate gate** (literal / adversarial / intent / **Ultron**) that loops, uncapped, until exactly one interpretation survives. Memory is shared and local (EverOS). Agents self-evolve via SkillOpt + SkillClaw. Everything is air-gapped by default.

## Install

```bash
cp -r forge-agents ~/.claude/skills/
```

Then, in Claude Code:

```
/scan-and-integrate     # YOUR existing separate skill — vendors EverOS, SkillOpt, SkillClaw
/forge-agents           # interview → build 4 agents (gated) → judge → leaderboard → self-review
```

> `/scan-and-integrate` is your own standalone skill and is **not** part of this package. `/forge-agents` simply calls it in Phase 0 to vendor the three repos, then proceeds.

## What's inside

```
forge-agents/
├── SKILL.md                     # 6-phase orchestrator
├── commands/
│   ├── forge-agents.md          # /forge-agents
│   └── evolve.md                # /evolve (manual evolution; nightly runs the same)
├── references/
│   ├── debate-gate.md           # the 4-member gate incl. Ultron (the core mechanism)
│   ├── architecture.md          # workspace layout + data flow
│   ├── agent-frameworks.md      # how to build each of the four
│   ├── judge.md                 # metric design + leaderboard
│   ├── memory-everos.md         # shared local memory + hybrid search
│   ├── evolution.md             # SkillOpt + SkillClaw sleep cycle
│   └── self-review.md           # final self-questioning pass
├── scripts/
│   ├── backend_config.py        # one switch: ollama <-> claude-haiku (LiteLLM shim)
│   ├── init_workspace.py        # scaffold the self-contained workspace
│   ├── debate_gate.py           # gate bookkeeping (won't write w/o consensus)
│   ├── hybrid_search.py         # keyword + meaning -> RRF -> local reranker
│   ├── run_agents.py            # parallel runner, sandboxed
│   ├── judge_score.py           # leaderboard over time
│   ├── self_review.py           # Phase 6 scaffold
│   ├── install.sh / install.ps1 # cross-platform setup
│   └── requirements.txt
└── assets/agent_templates/      # langgraph / crewai / claude_code / claude_sdk
```

## Key invariants

- Four agents, one task. The judge metric is a real number, identical across all four, and doubles as the SkillOpt validation gate.
- No agent line is written until the four-member gate agrees it has exactly one meaning — uncapped loop, halts to ask you on any ambiguity.
- Local/air-gapped by default (EverOS + Ollama). Claude Haiku is a one-line opt-in via a LiteLLM proxy.
- Agents are sandboxed to the workspace folder.
- Evolution is staged for your review — nothing auto-adopts.
- The judge does not promote/archive; it measures and tracks who's best over time.
