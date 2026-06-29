# Forge Agents — Start at Phase 2 (build a new agent set)

Paste the block below into a fresh Claude Code session opened in
`/Users/alexdodson/Downloads/Jarvis`. It skips the one-time setup (Phase 0/1 are
already done), verifies the builder is still healthy, archives any prior task so it
isn't clobbered, then runs the task interview (Phase 2) for a brand-new task and
continues from there.

---

```
Use the forge-agents skill. The foundry is already scaffolded and its dependencies are
already integrated at /Users/alexdodson/Downloads/Jarvis/agent-foundry — do NOT re-run
init_workspace, the installer, or /scan-and-integrate, and do NOT re-vendor the repos.

Do these in order; STOP and show me the finding if any readiness check fails.

1. FAST READINESS CHECK (no rebuild). Confirm and report PASS/FAIL for each:
   - vendor/EverOS, vendor/SkillOpt, vendor/SkillClaw all exist
   - config.toml [vendor] has a pinned commit for all three
   - `.venv/bin/python <skill>/scripts/backend_config.py` resolves cleanly (run from agent-foundry/)
   - the reranker model in config [search].reranker_model is cached/loadable
   - results/leaderboard.json exists
   - EverOS can start its server bound to 127.0.0.1 (start it, curl /health, then stop it)
   If anything is FAIL, stop and tell me — don't silently rebuild.

2. PRESERVE PRIOR WORK. If agent-foundry/task_spec.md already exists, this is a NEW,
   DIFFERENT task — archive the previous one first so nothing is overwritten:
   move task_spec.md, data/, agents/{langgraph,crewai,claude_code_subagent,claude_sdk},
   agent_built_prompts/, judge/, and results/ into
   archives/tasks/<short-slug-of-the-old-task>/ (create it). Leave config.toml, vendor/,
   memory/, evolvers/, and the seeded results/leaderboard.json scaffold in place. Tell me
   what you archived and where.

3. PHASE 2 — TASK INTERVIEW. Interview me to pin down the NEW task. One focused question
   at a time; ask only what you can't infer. You need: the task itself, its inputs, what a
   correct/good output looks like, and any constraints. Remember the foundry invariants —
   the task must be implementable in all four frameworks (LangGraph, CrewAI, Claude Code
   subagent, Claude Agent SDK) and measurable by ONE hard numeric metric. If the metric
   needs ground truth, propose how we get it (I'll usually want you to build a small gold
   set from real data in my vault). Capture the result as agent-foundry/task_spec.md, plus
   any schema/inputs/gold under agent-foundry/data/.

4. STOP after Phase 2 and show me the task spec for sign-off. Do NOT start Phase 3
   (debate-gated agent authoring) until I say go.

Backend stays local/air-gapped: Ollama qwen2.5:14b-instruct via config.toml [backend];
everything sandboxed to the agent-foundry/ workspace.
```

---

## Notes
- **Same task again vs. different task.** If you want to re-run the *same* task (e.g. to
  watch a framework improve via evolution), DON'T archive — keep `task_spec.md` and
  `results/` so the judge's leaderboard tracks deltas over time. The archive step is only
  for a genuinely different task.
- **Keeping multiple agent sets side by side.** Archiving (step 2) parks each finished task
  under `archives/tasks/<slug>/`. To resurrect one, move it back into place before Phase 4.
- **Heavier isolation (optional).** If you end up juggling many task families, say so and I'll
  refactor the foundry to a `tasks/<slug>/` layout (per-task agents + results + leaderboard)
  instead of the flat workspace — cleaner than archive/restore, but a one-time change to the
  skill's scripts.
- **If you ever move the repo or the model changes,** the readiness check will catch it
  (backend_config + EverOS server + reranker) and stop before building.
