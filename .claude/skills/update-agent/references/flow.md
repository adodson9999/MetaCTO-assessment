# Update-Agent Flow (brownfield, regression-protected)

This is the detailed procedure behind `update-agent <agent_name> <prompt>`. It
mirrors the forge-agents v2 flow but operates on **one existing agent** and folds in
a **user-described change**, under the rule that the update may never silently make
the agent worse.

The skill reuses the foundry's scripts (in `agent-foundry/scripts/`): `verify_build.py`,
`verify_files.py`, `debate_gate.py`, `determinism_check.py`, `slop_scan.py`,
`analyze.py`, `run_agents.py`, `improve_loop.py`, `golden_run.py`. `update_agent.py`
is the orchestrator that sequences them; the gates themselves are unchanged.

It additionally ships and runs the **code-review gate** (`scripts/code_review_gate.py`,
beside the orchestrator in this skill). The gate's reviewer set is **dynamic** —
every agent in `agent-foundry/agents/code-review/` discovered at run time
(`discover_perspectives()`), however many — and every code target the update creates
or modifies (all four framework `run.py`, the judge `score.py`, and any produced
code) must score **≥ 85 on every one of them, no exception**. No-bypass is enforced
with `receipt_matches_folder()` (the receipt's reviewer set must equal the folder).
This gate is **additive**: it never replaces the regression gate — both must pass,
for **every affected agent**.

## Phase 0 — Locate, snapshot, back up

1. **Resolve the agent.** Accept the full name (`api-tester-validate-request-payloads`)
   or short name (`validate-request-payloads`). Search
   `agent-foundry/agents/<group>/<name>/`. If multiple match, ask which. If none
   match, stop: this skill updates existing agents only.
2. **Record the baseline.** Read the agent's latest judged score and its golden
   baseline (`tests/golden/<group>/<name>/golden.json`). Call this `FLOOR`. The
   update must not end below `FLOOR` unless a tradeoff is authorized.
3. **Back up.** Copy the agent's prompt, runners, judge metric, golden, and the
   `.claude/agents/<name>.md` registration into
   `archives/update-<name>-<ts>/` so the update is fully reversible.

## Phase 1 — Capture the change

Write the user's prompt verbatim to `workspace/update_spec-<name>.md`, plus a parsed
summary: items to add, remove, or alter, and a **tradeoff flag** — `true` only if the
user explicitly allowed the metric to drop (phrases like "even if it lowers the
score", "accept the tradeoff"). Default `false`.

## Phase 2 — Re-author through the debate gate

1. Compute the **target instruction set** = existing lines + the requested change.
2. For each **new or changed** line, run the four-member debate gate
   (`../forge-agents/references/debate-gate.md`). A line is written only when
   literal/adversarial/intent/Ultron collapse to one interpretation; otherwise
   hard-halt and ask the user to clarify the change.
3. Unchanged lines that already passed are re-verified (still single-interpretation
   given the new neighbors), not re-litigated from scratch.
4. **Determinism review** the updated prompt (`determinism_check.py`): regenerate the
   gated lines N times; a non-deterministic result returns to the gate.
5. **95 code-quality gate** (`slop_scan.py`) on any regenerated `run.py`, runner, or
   `score.py`. Below 95 → rewrite, not patch.
6. **Code-review gate on every regenerated file (all four frameworks + the judge).**
   Any code this phase writes — the **LangGraph, CrewAI, Claude Code subagent, and
   Claude Agent SDK** `run.py`, and the judge `score.py` — must score **≥ 85 on every
   reviewer discovered in `agents/code-review/`** (however many), no exception. Below
   85 on any reviewer → hard-halt, show the notes, rewrite that file, re-run the full
   set; loop with no cap until every reviewer is ≥85. When this phase writes/revises
   the system prompt, add the **self-awareness clause** to the prompt across all four
   frameworks and the judge: it states that ALL code the agent creates is reviewed by
   every agent in `agents/code-review/` at ≥85, no exception, looping until it does,
   and points to `agents/code-review/` and `references/memory-everos.md`.

## Phase 3 — Analyze (consistency)

Run `analyze.py`. The updated prompt must stay consistent with the judge metric, the
task spec, and the constitution. If the change alters what the agent emits (new
fields, new categories), update `judge/<group>/<name>/metric.json` and `score.py`
to match, and record the metric change in the report — a moved metric is allowed but
must be explicit, never silent. Contradiction → hard-halt + ask.

## Phase 4 — Re-judge, improve, regression-check

1. Run the updated agent against the judge (`run_agents.py --only <group>/<name>`).
2. **Regression gate:**
   - `new_score >= FLOOR` → proceed.
   - `new_score < FLOOR` and tradeoff authorized → proceed, record the accepted drop.
   - `new_score < FLOOR` and **not** authorized → **hard-halt and ask the user**:
     show the delta and the options (revise the change, authorize the tradeoff, or
     abandon and restore from the Phase-0 backup).
3. Run the 10-round keep-if-improved tournament
   (`improve_loop.py --agent <group>/<name>`) to recover or raise the score after the
   change — same gates every round. **Every round that rewrites code re-runs the
   code-review gate**: a self-revision dropping any reviewed file below 85 on any
   reviewer in `agents/code-review/` is rejected, exactly as a metric regression is.
   For per-framework divergence, hand to the `fight-camp` skill instead.
4. `golden_run.py --derive` records the **post-update best** as the new baseline.
5. **Code-review gate — every affected agent, all four frameworks + the judge
   (no bypass).** `update_agent.py` now runs
   `code_review_gate.py --workspace <foundry> --agent <group>/<name>` for the updated
   agent **and each `--affected <group>/<name>`**. For every affected agent it:
   (a) runs the full reviewer set discovered in `agents/code-review/` over every code
   target (the four `run.py`, the judge `score.py`, any produced code) — pass = **≥ 85
   on every reviewer, no exception**; a missing reviewer/target, an empty folder, or a
   receipt ≠ folder is a failure, not a skip; and (b) re-checks regression
   (`is_regression(after, floor, tradeoff)` — hold-or-improve, never drop) and that the
   touched behavior still works. Failing either **hard-halts**: show the failing
   reviewers' notes, rewrite the code, re-run the full set; **loop with no cap** until
   every reviewer is ≥85 and no affected agent regressed. The update cannot proceed
   while any affected agent is below 85 on any reviewer or has regressed.

## Phase 5 — Verify and stage

1. `verify_build.py --phase 6` and `verify_files.py`: every created/updated file is
   present and correct; the `.claude/agents/<name>.md` registration still resolves to
   the canonical prompt; there is no stray `agent-foundry/.claude/agents/`.
2. `golden_run.py` passes (no regression below the prior baseline unless authorized).
3. **No-bypass code-review completion contract (every affected agent).** The update
   may **not** complete unless, for **every affected agent**, a
   `results/_global/code-review-<TS>.json` receipt exists with `status: pass`, the
   receipt's reviewer set **equals** `agents/code-review/` (`receipt_matches_folder()`),
   **and** the regression gate also passed. `code_review_contract_ok()` enforces this in
   `update_agent.py`: a missing receipt, a `status != pass`, or a receipt ≠ folder
   hard-halts. A does-not-apply receipt (no created/produced code) passes but must
   still exist. This is checked **in addition to** the regression gate — never instead
   of it; the "improve or hold, never drop" rule stays intact.
4. **Memory (EverOS shared pool).** After every gate run, `record_memory()` writes to
   `agent-foundry/memory/code-review/update-<ts>.md` (the `references/memory-everos.md`
   pool): the discovered reviewer set, the code reviewed, each reviewer's rating and
   notes, which failed, the fixes that reached ≥85, the final pass, and — for
   multi-agent updates — the per-affected-agent result and the regression check; plus
   the update itself (what was touched, why, what it affected). Stored under the shared
   `project_id=agent-foundry`/`app_id=forge` with each affected agent's `agent_id`, so
   any future agent or update can read what it will be tested against.
5. Write `workspace/update-report-<name>.md`:

```markdown
# Update Report — <agent_name>, <ts>
## Change applied
<user prompt, parsed summary, tradeoff: true/false>
## Score
baseline (FLOOR): <x>   ·   after change: <y>   ·   after improve loop: <z>
verdict: improved | recovered | tradeoff-accepted
## Metric
<unchanged | moved: old -> new, why>
## Code-review gate (per affected agent)
- <group>/<name>: reviewers=<N from agents/code-review/>  min_rating=<m>  status=pass  receipt=results/_global/code-review-<TS>.json
- <each --affected agent>: reviewers=<N>  min_rating=<m>  status=pass  regression=ok
## Files touched
- agents/<group>/<name>/subagent/<name>.md
- agents/<group>/<name>/<framework>/run.py (if regenerated)
- judge/<group>/<name>/metric.json (if moved)
- tests/golden/<group>/<name>/golden.json (new baseline)
## Registration
.claude/agents/<name>.md -> canonical prompt: OK
## Backup
archives/update-<name>-<ts>/
```

Routine, non-regressing updates **that pass the code-review gate** are applied and
reported. A regression without authorization, a reviewer below 85 on any affected
agent, a missing/stale code-review receipt, or a debate-gate ambiguity hard-halts to
ask the user; the gate loops (rewrite → re-run the full reviewer set) until every
reviewer is ≥85 for every affected agent.

## Failure / rollback

Any hard-halt leaves the agent in its pre-update state if the user chooses to
abandon — restore from `archives/update-<name>-<ts>/`. The skill never leaves a
half-updated, unverified agent claiming success (constitution Article I.9).
