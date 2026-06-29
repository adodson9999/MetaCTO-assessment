# Improvement Tournament — 10 rounds, keep-if-improved

Each agent plays **10 rounds against the judge**, revising itself to raise its
score. The discipline is autoresearch's: propose a bounded change, run it under a
fixed comparable budget, **keep it only if the metric improves, else discard**,
repeat. This runs in **Phase 4.5**, after the first judged run. The post-loop best
score per agent becomes the **golden baseline** (`references/golden-tests.md`).

This is the "improvement" companion to the determinism/guardrail spine: it makes
each agent measurably better while every change still passes the same gates.

## The round (per agent)

```
best := current best_skill + current judged score
for round in 1..10:
    1. PROPOSE  — agent reads the judge's metric + its last result and proposes ONE
                  bounded edit to its own skill/prompt (add / delete / replace a line).
    2. GATE     — every changed instruction line re-passes the four-member debate
                  gate (references/debate-gate.md). A line that can't converge is
                  rejected; the round retries with a different edit.
    3. DETERMINISM — the revised prompt gets a determinism review
                  (references/determinism.md). non-deterministic => discard the edit.
    4. RUN      — run the revised agent against the judge under the SAME fixed budget
                  (same held-out split, same backend, same concurrency).
    5. KEEP/DISCARD —
         if judged_score improves (or ties) best:  adopt, best := this
         else:                                      discard, restore previous best
    6. LOG      — append {round, edit, score, kept} to the trajectory.
best becomes the golden baseline.
```

The loop only ever moves the score up or sideways — it cannot regress an agent.

## Fixed comparable budget

Like autoresearch's 5-minute wall-clock budget, every round runs under identical
conditions so rounds are comparable: same held-out evaluation set
(`results/<group>/<name>/held_out.*`), same backend (session → Ollama), same
parallelism cap. The only thing that varies between rounds is the agent's own
skill edit. Budget knobs: `config.toml [improve] rounds=10, eval_budget=...`.

## Same process as before — with improvement

Nothing about the gates relaxes inside the loop. A revision must clear the **exact
same pipeline** a first-build line clears (debate gate + determinism review +
metric measurement). The loop adds only the keep-if-improved decision and the
trajectory log. This is the autoresearch idea applied to agent skills: the agent
edits its own "train.py" (its skill doc), the human-owned control flow
(this skill) stays fixed.

## Artifacts

```
evolvers/skillopt/<group>/<name>/
├── best_skill.md                 # the surviving best skill after 10 rounds
└── trajectory-<TS>.json          # [{round, edit, score, kept, determinism_verdict}]
results/<group>/<name>/
└── leaderboard-<TS>.{json,md}    # updated best-so-far per agent
tests/golden/<group>/<name>/
└── golden.json                   # baseline := post-loop best score
```

## Coupling to SkillOpt and the golden suite

- The loop **is** SkillOpt's optimization made explicit and time-boxed: the
  validation gate is the judge metric, the held-out split prevents overfitting,
  and adoption is keep-if-improved. SkillOpt's nightly sleep cycle continues the
  same loop offline (`references/evolution.md`), staged for user review.
- After the loop, `golden_run.py --derive` records the baseline. From then on, any
  future SkillOpt/SkillClaw edit must pass the golden suite or it is rejected — so
  self-improvement can never quietly regress a shipped agent.

## Per-framework variant — fight-camp

This loop, as written, sharpens an agent's skill with one prompt state. When you
want **each framework optimized independently with its own divergent prompt** (a
prompt great for CrewAI but poor for LangGraph is kept only for CrewAI), use the
separate **`fight-camp`** skill. It runs this exact keep-if-improved loop four
times in four sealed corners — same task, same metric, same budget, independent
prompt per framework — and produces a cross-framework best-achievable leaderboard.
fight-camp reuses these same gates; it does not relax any of them.

## Determinism is mandatory every round

Per the user's directive and constitution Article I.8, **every round gets a
determinism review** — code, the debate verdict on changed lines, and the judged
score. A round whose score "improved" only because of an unstable sample is not
adopted.
