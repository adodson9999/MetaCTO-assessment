# Self-Evolution (SkillOpt + SkillClaw)

Two complementary mechanisms make the agents better over time. They are not redundant: SkillOpt sharpens each agent individually behind a hard gate; SkillClaw shares and collectively evolves skills across all agents in the folder.

## SkillOpt — per-agent, validation-gated (vertical)

SkillOpt treats each agent's skill document as the trainable state of a frozen model and optimizes it with the loop: rollout → reflect → aggregate → select → update → evaluate. A bounded add/delete/replace edit to the skill doc is **accepted only if it strictly improves a held-out validation score**; otherwise it is rejected. The output is a compact `best_skill.md` per agent (in `evolvers/skillopt/<agent>/`).

**The validation-gate metric is the judge's metric** (`judge/<group>/<agent-short-name>/metric.json`). The same number that ranks the agents gates their self-improvement — no second, fuzzy metric. The held-out set is `results/<group>/<agent-short-name>/held_out.*` so optimization cannot overfit the items used for ranking.

SkillOpt-Sleep is the deployment-time companion: a nightly **sleep cycle** that reviews past sessions/runs, replays recurring tasks offline, consolidates validated edits behind the held-out gate, and **stages a proposal for the user to adopt** — never auto-adopts. Its engine is decoupled and runs locally.

## SkillClaw — collective, cross-agent (horizontal)

SkillClaw distills real session artifacts into reusable `SKILL.md` skills and shares them across the whole set of agents in the folder. A client proxy records session artifacts; an evolve server summarizes → aggregates → executes to evolve or create skills; `skillclaw skills pull/push/sync` keeps the shared pool current. Pin the storage backend to **local filesystem** (not Alibaba OSS / S3) so it stays air-gapped — shared skills live in `evolvers/skillclaw/`.

## How they combine

```
SkillOpt:  each agent's own skill  --gated by judge metric-->  better best_skill.md
SkillClaw: all agents' sessions    --distilled + shared----->  shared SKILL.md pool
                                                  |
                                     both feed the four agents
```

## Cadence and adoption

- **When:** nightly sleep cycle **plus** a manual trigger (`/evolve`).
- **Gate:** every SkillOpt edit must strictly improve the held-out judge metric.
- **Adoption:** staged for the user's review (review-then-adopt). Nothing auto-adopts.

## Backend

Both evolvers read the central backend config. Claude reaches SkillClaw and EverOS's OpenAI path through the LiteLLM proxy; Ollama is natively OpenAI-compatible. Swapping the model is one line in `config.toml`.
