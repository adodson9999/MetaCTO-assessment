# Self-Questioning Pass

The final step of every build. After the four agents, judge, memory, evolvers, and search are scaffolded, turn scrutiny on your own output. Mirror the honest two-axis style of the user's `self-eval` skill: no inflated scores, devil's-advocate reasoning, real findings. **Report — do not auto-apply.**

## When

Once, at the very end (Phase 6), after everything else is in place.

## What to interrogate

Ask hard questions across these axes and answer them honestly:

1. **Ambiguity leakage.** Did any instruction line reach an agent without truly converging in the debate gate? Re-read each `agent_built_prompts/<position>/<workflow>/<framework>.prompt.md` adversarially — could Ultron still reach a second reading?
2. **Measurability.** Is the judge's metric genuinely numeric, identical across all four agents, and computed deterministically? Could two agents game it differently?
3. **Fair comparison.** Are the four implementations actually doing the *same* task, or did one framework's shell drift the task?
4. **Sandbox integrity.** Is there any path by which a generated agent could write or exec outside the workspace?
5. **Air-gap integrity.** Does anything (an embedder, a default base URL, a SkillClaw OSS backend) reach the network unintentionally?
6. **Shared-memory correctness.** Do all four agents truly share the pool (same `project_id`/`app_id`) while staying attributable (`agent_id`)?
7. **Gate/metric coupling.** Does the SkillOpt validation gate really use the judge metric, with a held-out split that prevents overfitting the ranking set?
8. **Fragility.** Where will this break first under real use (local model saturation under parallel runs, EverOS index lag, reranker latency, proxy auth)?

## Output

Write `workspace/SELF_REVIEW.md`:

```markdown
# Self-Review — <task>, <timestamp>

## Honest assessment
<2-axis: how complete is it, how confident am I — no inflation>

## Findings
- [severity] <finding> → <concrete improvement>
- ...

## Ambiguities that may have slipped the gate
- <line> in <agent>: <residual reading> → <suggested rewrite>

## What will break first
- <component>: <why> → <mitigation>

## Recommended next actions (for the user to decide)
- ...
```

Then present the findings to the user and stop. The user decides what to act on.
