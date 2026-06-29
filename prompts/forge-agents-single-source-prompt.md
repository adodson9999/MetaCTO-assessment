# Refactor: Single-Source Prompt for forge-agents

Update the forge-agents skill so that all four framework agents (LangGraph, CrewAI,
Claude Code subagent, Claude Agent SDK) read from ONE canonical prompt file per
workflow instead of maintaining four separate prompt files.

## What to change

### 1. Locate the skill file

Open `.claude/skills/forge-agents/forge-agents/SKILL.md` (and the outer copy at
`.claude/skills/forge-agents/SKILL.md` if it differs). The section to update is
**Phase 3 — Author the four agents through the debate gate**.

### 2. Replace the output file convention

**Current behavior (wrong):** Phase 3 saves one prompt file per framework:
```
agent_built_prompts/<position>-<workflow>-langgraph.prompt.md
agent_built_prompts/<position>-<workflow>-crewai.prompt.md
agent_built_prompts/<position>-<workflow>-claude_sdk.prompt.md
agent_built_prompts/<position>-<workflow>-claude_code.prompt.md
```

**New behavior (correct):** Phase 3 saves ONE canonical prompt file for the workflow,
plus one debate trail per framework:
```
agent_built_prompts/<position>-<workflow>.prompt.md          ← single source of truth
agent_built_prompts/<position>-<workflow>-langgraph.debate.md
agent_built_prompts/<position>-<workflow>-crewai.debate.md
agent_built_prompts/<position>-<workflow>-claude_sdk.debate.md
agent_built_prompts/<position>-<workflow>-claude_code.debate.md
```

### 3. Update Phase 3 instructions

Replace the "As each agent's lines are finalized" block with:

> As each agent's lines are finalized:
> - Write the agent itself using the framework templates in `references/agent-frameworks.md`
>   and `assets/agent_templates/`. Each agent is built instrumented (emits its metric to
>   `results/`).
> - After all four agents are gated, distill the agreed task instructions into a single
>   canonical file: `agent_built_prompts/<position>-<workflow>.prompt.md`. This file
>   contains the task definition, required behaviors, output schema, and pass/fail thresholds
>   that all four implementations share. It must NOT contain framework-specific syntax.
> - Each framework agent file imports this canonical prompt as its task spec — either by
>   reading the file at runtime or by embedding a reference comment at the top:
>   `# Task spec: agent_built_prompts/<position>-<workflow>.prompt.md`
> - Save each framework's debate trail separately:
>   `agent_built_prompts/<position>-<workflow>-<framework>.debate.md`
>
> All files live flat in `agent_built_prompts/` — no subfolders. The canonical prompt is
> the single source of truth. If the task spec changes, only that one file is updated;
> the four agent files inherit the change automatically.

### 4. Update the DebateGate call

Change `group="<position>/<workflow>"` → `group="<position>-<workflow>"` everywhere
it appears in the skill and in `scripts/` that reference the group path.

### 5. Migrate any existing prompt files

If `agent_built_prompts/` already contains per-framework prompt files from a prior run,
consolidate them:
1. Diff the four `.prompt.md` files — the shared task instructions are identical across
   all four; only framework boilerplate differs.
2. Extract the shared content into `<position>-<workflow>.prompt.md`.
3. Delete the four per-framework `.prompt.md` files.
4. Add the reference comment to the top of each framework agent file.

Do not change debate trail files — those stay per-framework.

## Acceptance criteria

- `agent_built_prompts/` contains exactly ONE `.prompt.md` file per workflow.
- Each of the four framework agent files references that single file (runtime read or
  comment header).
- Debate trail files remain per-framework (four `.debate.md` files per workflow).
- Running the forge-agents skill on a new task produces the correct flat structure
  with no subfolders and no duplicate prompt content.
