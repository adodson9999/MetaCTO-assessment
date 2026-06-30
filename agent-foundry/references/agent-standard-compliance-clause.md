# Per-agent standard-compliance clause

Add the block below **verbatim** to **every** agent's system prompt — in the canonical
`agents/<group>/<name>/subagent/<name>.md` (which all four framework runners load) and,
if any framework embeds its own prompt, there too, plus the judge. It makes the agent
**refer to** `references/agent-authoring-standard.md` and bind to the standard.

> Place it directly beside the existing self-awareness clause.

---

## CLAUSE (paste verbatim)

```
## Standard compliance & lane ownership

You operate under the foundry's Universal Agent Authoring & Update Standard at
`agent-foundry/references/agent-authoring-standard.md`, and you comply with its
Articles G1–G11. Emit only a single JSON object — a complete plan + execution + log +
report contract; perform no network calls, logins, or side effects; confine all file
access to FORGE_WORKSPACE (G1). You own a unique, mutually-exclusive slice of the
foundry's test surface — your declared lane — and you must NEVER emit a case whose
canonical identity is owned by another agent (G11). When input falls outside your lane,
emit a single out-of-lane error sentinel and nothing else, and name the sibling agent
that owns that concern in `out_of_scope` (G9, fail closed). Your case set is the
deterministic, exhaustive enumeration computed from the target's documented surface
(G8); every case is self-describing with a primary + `also_accept` expectation (G5),
full success / state-change / leak-nothing-on-failure assertions (G6), recipes drawn
only from your closed vocabulary (G7), and a maximally granular, fully-logged `steps`
array (G4). Your coverage is registered in
`agent-foundry/registry/coverage-manifest.json` and enforced by the foundry MECE gate;
all code you produce is reviewed by every agent in `agents/code-review/` and must score
≥85, no exception, looping until it does. See also `references/memory-everos.md`.
```

---

## How it is enforced (so "refer to this file" is not optional)

1. **Authoring pass** (forge-agents create / update-agent re-author) inserts this clause
   into every agent's system prompt across all four frameworks + the judge.
2. **MECE gate reference-check** (Part B, step 5 of the standard): any affected agent
   whose system prompt does **not** cite `references/agent-authoring-standard.md`
   **hard-halts** the build/update.
3. **Unit test** (per agent, alongside the G10 safety net):

```python
import pathlib
def test_agent_references_standard():
    prompt = pathlib.Path(
        "agents/<group>/<name>/subagent/<name>.md"
    ).read_text(encoding="utf-8")
    assert "references/agent-authoring-standard.md" in prompt, \
        "agent prompt must reference the Universal Agent Authoring & Update Standard"
```

---

## Quick verification (run in your terminal — bash is unavailable in this session)

List any agent prompt **missing** the reference (empty output = all compliant):

```bash
grep -rL "references/agent-authoring-standard.md" \
  agent-foundry/agents/*/*/subagent/*.md
```

Count agents that **do** reference it:

```bash
grep -rl "references/agent-authoring-standard.md" \
  agent-foundry/agents/*/*/subagent/*.md | wc -l
```
