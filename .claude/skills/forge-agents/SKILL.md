---
name: forge-agents
description: "Build four parallel implementations of the same task-agent (LangGraph, CrewAI, Claude Code subagent, Claude Agent SDK), plus a judge agent that invents a concrete numeric metric and ranks them on a leaderboard. Every line of every agent's instructions passes a four-member adversarial debate gate (literal / adversarial / intent / Ultron) before it is written, looping until exactly one interpretation survives. Wires the agents into a shared local EverOS memory pool and a SkillOpt + SkillClaw self-evolution loop. Use this skill whenever the user wants to forge agents, build a multi-framework agent comparison, create an agent arena, build the same agent in several frameworks and score them, set up a judged agent benchmark, or says 'forge agents', 'build me the four agents', 'compare frameworks on this task', or anything about building agents that must be measured against a hard metric. Trigger even when the user only describes the task and expects the four-agent + judge build implicitly."
---

# Forge Agents

You are an agent foundry. Given one task, you build **four implementations of that same task** in LangGraph, CrewAI, a Claude Code subagent, and the Claude Agent SDK plus a **judge agent** that invents a concrete numeric metric and ranks the four on a leaderboard. Every instruction line that defines any agent must survive a four-member debate gate before it is committed. Everything runs locally and air-gapped.

This SKILL.md is the control flow. Detailed specs live in `references/` read the named file at each phase rather than guessing.

## Non-negotiable invariants

These hold in every phase. If any instruction you are about to write would violate one, stop.

1. **Four agents, one task.** Always exactly four implementations of the *same* task: LangGraph, CrewAI, Claude Code subagent, Claude Agent SDK. Four-of-the-same is intended.
2. **The judge invents a hard metric, not a rubric.** The judge defines a single numeric metric measurable on all four, measures it, and emits a leaderboard. No fuzzy scoring. See `references/judge.md`.
3. **Every agent line passes the debate gate.** No instruction line reaches an agent file until the four-member panel reaches consensus that it has exactly one interpretation. See `references/debate-gate.md`. This is the most important gate in the skill — never skip or batch it.
4. **Agents are built to be measured.** Each agent must emit its metric in an obvious, machine-readable way (structured JSON to `results/`). If you cannot see how a built agent would emit its number, the build is wrong.
5. **Local and air-gapped.** Memory is EverOS only (Markdown + SQLite + LanceDB on Ollama). Backend is swappable between Ollama and Claude Haiku via one central config. Nothing calls a non-local service unless the user explicitly opts into a cloud backend.
6. **Sandbox.** All agent read/write/exec is confined to the workspace folder. Never let a generated agent act outside it.
7. **Single-source LLM config — never hardcode a provider.** Every shell script
   the foundry generates MUST follow this exact pattern and no other:
   - `config.toml [backend].provider` is always `"auto"` (never `"ollama"` or `"claude-haiku"`)
   - Every `phase4_*.sh` script resolves the provider via exactly:
     `eval "$(python scripts/llm_config.py --export)"`
   - No script contains a bare `export FORGE_PROVIDER="..."` assignment
   - Every ollama health-check (`curl …/api/tags`) is wrapped in:
     `if [ "$FORGE_PROVIDER" = "ollama" ]; then … fi`
   - After generating or editing any shell script, run:
     `python scripts/verify_llm_config.py`
     and fix all failures before proceeding. A non-zero exit is a build defect.

## Phases

Move through these in order. Phase 0 and Phase 1 set up the environment; Phases 2–6 run per task.

### Phase 0 — Integrate dependencies (call the existing `/scan-and-integrate` skill)

Before the first build, the three upstream repos must be present and verified. `/scan-and-integrate` is the user's **own separate skill** — this skill does not implement it. Invoke `/scan-and-integrate`, passing each repo URL and its stated purpose, and let that skill do the security scan, purpose verification, and vendored install into `vendor/`. The three repos and the purpose to pass for each:

- **EverMind-AI/EverOS** — local self-evolving agent memory (the shared memory pool).
- **microsoft/SkillOpt** — per-agent, validation-gated skill optimization (`best_skill.md`).
- **AMAP-ML/SkillClaw** — collective cross-agent skill evolution and sharing.

If `/scan-and-integrate` reports that a repo fails its security scan or purpose check, STOP and report to the user. Do not proceed to build against an unintegrated repo. After it finishes, record each pinned commit in `config.toml` `[vendor]`.

### Phase 1 — Scaffold the workspace

Run `scripts/init_workspace.py` to create the one self-contained workspace folder. Layout and rationale are in `references/architecture.md`. The folder contains `agents/`, `memory/`, `agent_built_prompts/`, `evolvers/`, `results/`, the shared EverOS store, the central `config.toml`, and the installer. Then run the installer (`scripts/install.sh` on macOS/Linux, `scripts/install.ps1` on Windows) for one-command setup.

### Phase 2 — Define the task (interactive interview)

Interview the user to pin down the task. Ask only what you cannot infer, one focused question at a time. You need: the task itself, its inputs, what a correct/good output looks like, and any constraints. Capture the result as `workspace/task_spec.md`. This interview is **separate** from the debate gate — here you gather the task; the gate governs the agent instruction lines you write afterward.

### Phase 3 — Author the four agents through the debate gate

For each of the four agents, draft its instruction set **one line at a time**, and pass every line through the debate gate before writing it. The full procedure — the four panel members, the consensus rule, the halt-and-ask behavior, and the uncapped loop — is in `references/debate-gate.md`. Read it now; do not improvise the gate.

As each agent's lines are finalized:

- Write the agent itself using the framework templates in `references/agent-frameworks.md` and `assets/agent_templates/`. Each agent is built instrumented (emits its metric to `results/`).
- Save the clean approved prompt to `agent_built_prompts/<agent>.prompt.md`.
- Save the debate trail to `agent_built_prompts/<agent>.debate.md`.

All four agents share the same EverOS memory pool — see `references/memory-everos.md` for the shared-scope wiring (common `project_id`/`app_id`, per-agent `agent_id`).

### Phase 4 — Build the judge and run the four agents

Build the judge per `references/judge.md`: it invents one concrete numeric metric for this task, runs the four agents **in parallel** (`scripts/run_agents.py`), reads their emitted numbers, and writes a leaderboard (`results/leaderboard.md` + `results/leaderboard.json`). The judge tracks results over time so repeated runs show which framework is best at this task.

### Phase 5 — Wire self-evolution

Wire the agents into the evolution loop per `references/evolution.md`: SkillOpt sharpens each agent's own skill document behind a validation gate that uses the judge's metric; SkillClaw shares and collectively evolves skills across all agents in the folder. Evolution runs on a **nightly sleep cycle plus a manual trigger** (`/evolve`), staged for the user's review before adoption — never auto-adopted.

### Phase 6 — Self-questioning pass

As the final step, critique your own build. Read `references/self-review.md` and write `workspace/SELF_REVIEW.md`: gaps, weak spots, ambiguities that slipped through, fragile wiring, and concrete improvements. Report findings; do not auto-apply them. The user decides what to act on.

## Folder search

Whenever you search the workspace folder, use the hybrid pipeline in `scripts/hybrid_search.py`: a keyword leg (BM25/SQLite) and a meaning leg (EverOS embeddings/LanceDB) run in parallel, their results are fused with reciprocal-rank fusion, and a local reranker produces the final order. Never do a single-mode lookup.

## Backend switching

All components read one central backend config (`scripts/backend_config.py` + `config.toml`). The provider switch toggles between `ollama` and `claude-haiku` (`claude-haiku-4-5`), with a LiteLLM proxy as the universal OpenAI-compatible shim so even SkillClaw and EverOS's OpenAI path accept Claude. Swapping models is a one-line change; every agent, the judge, the debaters, and the evolvers inherit it.