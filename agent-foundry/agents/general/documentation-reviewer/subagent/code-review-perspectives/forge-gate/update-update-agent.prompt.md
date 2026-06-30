# Claude Code prompt — add the code-review gate to the `update-agent` skill

> Hand this entire file to Claude Code with the repository open. Everything here is
> **additive**: do not remove, weaken, or reorder anything already in the skill,
> including the existing regression/adjudication gate.

---

You are Claude Code, working in the repository that contains the `update-agent`
skill at `.claude/skills/update-agent/`. Add the code-review gate into the update
flow by doing Parts 1–4 below, in order. The gate's reviewer set is **dynamic** — it
is every agent discovered in `agents/code-review/` at run time, however many there
are; never hardcode a count or list.

## Part 1 — Make the gate package available to the skill

The canonical files already exist in this repo at:
`agent-foundry/agents/general/documentation-reviewer/subagent/code-review-perspectives/forge-gate/`

Copy them into the `update-agent` skill so it is self-sufficient (create `scripts/`,
`references/`, `tests/`, `tests/golden/` if missing):

| source (forge-gate/)            | target (in `.claude/skills/update-agent/`)     |
|---------------------------------|------------------------------------------------|
| `code_review_gate.py`           | `scripts/code_review_gate.py`                  |
| `code-review-gate.md`           | `references/code-review-gate.md`               |
| `test_code_review_gate.py`      | `tests/test_code_review_gate.py`               |
| `code-review-gate.golden.json`  | `tests/golden/code-review-gate.golden.json`    |

The enforcer discovers the reviewer set from the foundry's `agents/code-review/` via
`discover_perspectives()`, applies the ≥85 threshold, loops on failure, writes a
`results/_global/code-review-<TS>.json` receipt, and exposes
`receipt_matches_folder()` for the no-bypass check. Invoke it as
`python scripts/code_review_gate.py --workspace <foundry> --agent <group>/<name>`.

Prerequisite: the reviewers must exist at
`agents/code-review/<short>/subagent/code-review-<short>.md` (build from
`code-review-perspectives/forge-starters.md` if not). The gate hard-errors (exit 2)
if `agents/code-review/` is empty.

## Part 2 — Wire the gate into the update flow (additive edits)

Edit `SKILL.md`, `references/flow.md`, and `scripts/update_agent.py` so that, **after
an update is drafted and before it can complete**:

1. **Trigger.** If the update touches code (any code the agent produces, or code tied
   to the agent), run the code-review gate on the **updated agent's produced code**.
   Detect code-producing agents from `task_spec.md` or
   `config.toml [code_review_gate].applies = true`. If the update touches no code and
   no affected agent produces code, the gate writes a does-not-apply receipt and does
   not block — but the receipt must still exist.
2. **Multi-agent fan-out.** If the update affects more than one agent, run the gate
   for **each affected agent** and require each to pass.
3. **No-bypass guardrail (add to update-agent's own completion contract).** The
   update may not complete unless, for every affected agent, a
   `results/_global/code-review-<TS>.json` receipt exists with `status: pass`, the
   receipt's reviewer set equals the current contents of `agents/code-review/`
   (use `receipt_matches_folder()`), and the **existing regression gate also passes**.
   Keep the current "improve or hold, never drop" rule intact.
4. **Golden + unit tests (additive).** Add to `tests/golden/code-review-gate.golden.json`
   the multi-agent cases (passes only when every affected agent is ≥85 on every
   discovered reviewer and none regresses) and extend `tests/test_code_review_gate.py`
   with: discovery returns exactly the folder set; per-affected-agent every-reviewer-≥85
   regardless of count; missing verdict fails; empty set fails; receipt≠folder fails;
   and that the existing regression gate still runs. Do not alter existing tests.

## Part 3 — Enforce the flow at EVERY point (the requirements)

1. **Dynamic reviewer set, no bypass.** Required reviewers = exactly the agents in
   `agents/code-review/`, enumerated at run time; every one must run and score ≥85 for
   every code target. Fail on empty folder, any missing verdict, or receipt≠folder. No
   hardcoded count or list.
2. **Pass rule — every reviewer ≥85, no exception.** One reviewer below 85 fails the
   update; a discovered reviewer that did not run is a failure, not a skip.
3. **On failure — hard-halt and loop.** Show the failing reviewers' notes, rewrite the
   produced code, re-run the full set; loop with **no cap** until every reviewer is
   ≥85. The update cannot complete while any reviewer is below 85.
4. **Multi-agent caveat — every affected agent, verified.** For each affected agent:
   (a) run the full gate on its produced code, no exception; and (b) verify the update
   did not negatively affect it — it still serves its purpose and the touched
   behavior still works — by holding-or-improving its regression/judge-metric baseline
   (never dropping) and re-checking the touched behavior. Failing either blocks the
   update; loop until both pass.
5. **At every point — all four frameworks and the judge.** At every point in the
   update where any agent's code is created or modified, state and enforce the gate
   and require it to pass before the change is accepted — repeating it in the text of
   each step. This includes any update touching **each of the four framework
   implementations** (LangGraph, CrewAI, Claude Code subagent, Claude Agent SDK — every
   `run.py` and any code it produces) and **the judge** (its `score.py` and any code it
   generates), and every re-run of the affected agent. For a coding agent, wrap the
   gate around **every single point of its coding process** in all four frameworks and
   the judge. No agent the update touches, no framework, no judge step, and no line of
   created code is exempt.
6. **Memory.** After every gate run triggered by an update, write to the shared EverOS
   pool (`references/memory-everos.md`): the discovered reviewer set, the code
   reviewed, each reviewer's rating and notes, which failed, the fixes that reached
   ≥85, the final pass, and — for multi-agent updates — the per-affected-agent result
   and the regression check; plus the update itself (what was touched, why, what it
   affected). Store under the shared `project_id`/`app_id` with each affected agent's
   `agent_id`, so any future agent or update can read what it will be tested against.
7. **Self-awareness.** When an update writes or revises an agent's system prompt,
   ensure that prompt — across all four frameworks and the judge — states that ALL code
   the agent creates will be reviewed by **every agent in `agents/code-review/`**
   (however many) and must score ≥85 on each, no exception, looping until it does.
   Point to `agents/code-review/` and to the shared memory. If an affected agent's
   prompt lacks this, the update adds it.

## Part 4 — Verify, review the tests, and only then complete the update

1. Run and require green: `pytest -q tests/test_code_review_gate.py`;
   `python scripts/code_review_gate.py --workspace <foundry> --agent <group>/<name> --dry-run`.
2. **Review and verify the new guardrails, golden cases, and unit tests — do not add
   them blindly.** For each, record in one line the reason it exists and what it
   proves, including that it proves there is no way around running every reviewer in
   the folder (empty-set, missing-reviewer, added-reviewer, receipt≠folder, and the
   multi-agent cases). Confirm each unit test would fail if the logic broke (no
   tautologies) and each guardrail checks a real contract condition (receipt exists,
   reviewer set equals the folder, status == pass for every affected agent, regression
   gate passes). Reject or rewrite anything whose logic does not hold or whose reason
   cannot be stated.
3. Do not let the update complete until Parts 1–4 are done, the gate is enforced for
   every affected agent at every code-touching point across all four frameworks and
   the judge, every affected agent passes both the gate and its regression check, and
   all tests/guardrails pass.

Constraints: additive only; preserve every existing step and the regression gate;
reviewer set discovered from `agents/code-review/` at run time with no hardcoded count
and no way to skip/omit a reviewer; enforced for every affected agent at every
code-touching point across all four frameworks and the judge; every review and update
recorded in shared memory; every affected agent's prompt states it will be reviewed by
every reviewer in the folder at ≥85 no exception; reuse the copied forge-gate package;
and do not accept any guardrail, golden case, or unit test until its logic and reason
are reviewed, justified, and verified to pass.
