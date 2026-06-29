# Update-Agent Flow (brownfield, regression-protected)

This is the detailed procedure behind `update-agent <agent_name> <prompt>`. It
mirrors the forge-agents v2 flow but operates on **one existing agent** and folds in
a **user-described change**, under the rule that the update may never silently make
the agent worse.

The skill reuses the foundry's scripts (in `agent-foundry/scripts/`): `verify_build.py`,
`verify_files.py`, `debate_gate.py`, `determinism_check.py`, `slop_scan.py`,
`analyze.py`, `run_agents.py`, `improve_loop.py`, `golden_run.py`. `update_agent.py`
is the orchestrator that sequences them; the gates themselves are unchanged.

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
   change — same gates every round. For per-framework divergence, hand to the
   `fight-camp` skill instead.
4. `golden_run.py --derive` records the **post-update best** as the new baseline.

## Phase 5 — Verify and stage

1. `verify_build.py --phase 6` and `verify_files.py`: every created/updated file is
   present and correct; the `.claude/agents/<name>.md` registration still resolves to
   the canonical prompt; there is no stray `agent-foundry/.claude/agents/`.
2. `golden_run.py` passes (no regression below the prior baseline unless authorized).
3. Write `workspace/update-report-<name>.md`:

```markdown
# Update Report — <agent_name>, <ts>
## Change applied
<user prompt, parsed summary, tradeoff: true/false>
## Score
baseline (FLOOR): <x>   ·   after change: <y>   ·   after improve loop: <z>
verdict: improved | recovered | tradeoff-accepted
## Metric
<unchanged | moved: old -> new, why>
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

Routine, non-regressing updates are applied and reported. A regression without
authorization, or a debate-gate ambiguity, is the only thing that stops to ask.

## Failure / rollback

Any hard-halt leaves the agent in its pre-update state if the user chooses to
abandon — restore from `archives/update-<name>-<ts>/`. The skill never leaves a
half-updated, unverified agent claiming success (constitution Article I.9).
