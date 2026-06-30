# SELF_REVIEW — code-review-data-integrity

Group `code-review`, short name `data-integrity`. Single lens: **can stored data end up
wrong, duplicated, orphaned, or lost** — judge whether writes stay consistent under
concurrent writes and retries and whether migrations are safe. Built by adapting the sibling
`logic-error` agent's verified substrate to this lens; identical plumbing, divergent prompt
and held-out set.

## Deliverable set (all present)

- Prompt module: `agents/common/dataintegrity_prompt.py` (13 debate-gated APPROVED_LINES).
- Driver: `agents/common/dataintegrity.py` (per-case run + score + emit, sandbox-guarded).
- Spec/scoring substrate: `agents/common/dataintegrity_spec.py` (case load, oracle, strict
  `{rating, notes}` schema, band scoring).
- Four framework dispatchers: `agents/code-review/data-integrity/{subagent,langgraph,crewai,claude_sdk}/run.py`.
- Canonical prompt artifact: `agents/code-review/data-integrity/subagent/code-review-data-integrity.md`
  (frontmatter + body; body is byte-identical to `APPROVED_PROMPT` — verified).
- Judge: `judge/code-review/data-integrity/metric.json` + `score.py`.
- Held-out: `results/code-review/data-integrity/held_out.jsonl` (6 cases; the 2 mandatory
  seeds + 4 lens-covering cases).
- Data spec: `data/code-review-data-integrity/dataintegrity_spec.json`.
- Host registration: `.claude/agents/code-review-data-integrity.md` (confirmed written).

## Verification performed

- **Oracle self-test (saturation guard — the standing forge warning):** over all 6 cases the
  reference (gold-band-midpoint) decision scores **1.0**, an **empty** emission scores **0.0**,
  and a **benign-wrong** (opposite-end rating) emission scores **0.0**. No fallback path
  saturates the metric.
- **Schema strictness (`strict` mode):** extra key → reject; `rating` bool → reject; empty
  `notes` → reject; `rating` 101 → reject; exact `{rating, notes}` → accept.
- **Prompt consistency:** the `.md` body equals `dataintegrity_prompt.APPROVED_PROMPT`
  (determinism contract — the subagent framework reads the `.md`, the other three read the
  module; they must converge).
- **Compile:** all 8 new Python files `py_compile` clean.
- **End-to-end live run (Ollama `qwen2.5:14b`, langgraph):** ran all 6 cases, **schema valid
  on 100%**, judge + leaderboard rendered. Band accuracy **0.5** — the local 14b model
  under-rates the subtler threats (check-then-insert race and lost-update it rated 75; float
  money it rated 100). This is a local-model sensitivity floor, not a wiring defect.
- **End-to-end live run (in-session Claude backend, subagent):** rating correctly in-band on
  the cases observed (DI-001→100, DI-002→15, …). The capable backend is the agent's design
  target.

## Residual gaps / fragilities

- **Gold-band calibration vs. model sensitivity.** Cases DI-003 (check-then-insert race),
  DI-004 (read-modify-write lost update) at `[0,45]` and DI-006 (float money) at `[0,55]`
  encode the *correct* severity per the lens (duplicate/lost data = serious; float money =
  real problem). Weak local models under-rate them. The bands are deliberately **not** widened
  to absorb a 75 rating, because that would make "real problem" indistinguishable from
  "fine." A capable backend is required to hit the strong golden baseline; the Ollama 0.5 is
  an honest floor, not the target.
- **Full 4-framework parallel leaderboard not run end-to-end here.** langgraph (Ollama) and
  subagent (Claude) were validated individually; crewai and claude_sdk share the identical
  thin-dispatcher pattern and the same injected `generate`, so wiring risk is low, but a full
  `run_agents`-style parallel sweep on one backend is the remaining confidence step.
- **Held-out breadth.** 6 cases cover atomic-tx, check-then-insert, lost-update, idempotent
  upsert, and float money. Not yet covered: explicit unsafe-migration, foreign-key/orphan,
  and naive-vs-UTC timestamp cases. The lens prompt covers them; the held-out set should grow
  to exercise them (swap in more lines — ids re-assign by surviving order).

## Concrete improvements (not auto-applied)

1. Add 2–3 held-out cases for the uncovered facets (unsafe migration, orphaned FK, naive
   timestamp) with defensible bands once a capable backend is the standing scorer.
2. Run the full four-framework parallel sweep + judge on the Claude backend to publish the
   first real leaderboard and lock the golden baseline.
3. Consider a `medium`-severity anchor case in the prompt (a third worked anchor) to sharpen
   the 40–69 band, where local models are weakest.
