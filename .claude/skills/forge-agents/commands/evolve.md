---
description: "Manually trigger one self-evolution pass (SkillOpt sharpening + SkillClaw sharing), gated by the judge metric and staged for review. Same engine as the nightly sleep cycle."
allowed-tools: Read, Write, Bash, Glob, Grep
---

# /evolve

Run one evolution pass on demand (the nightly sleep cycle runs the same thing automatically). See `references/evolution.md`.

$ARGUMENTS

## Procedure

1. **Harvest** recent run sessions from `results/runs/` and the shared EverOS pool.
2. **SkillOpt:** for each agent, propose bounded add/delete/replace edits to its `best_skill.md`; **accept only if the held-out judge metric strictly improves** (`results/held_out.*`, metric from `judge/metric.json`). Reject otherwise.
3. **SkillClaw:** distill session artifacts into shared `SKILL.md` skills; `skillclaw skills sync` over the local-FS backend.
4. **Stage, don't adopt.** Write proposed changes to `evolvers/` as a staged proposal and present a diff to the user. Adoption is the user's explicit choice.

Never auto-adopt. Never use a metric other than the judge's.
