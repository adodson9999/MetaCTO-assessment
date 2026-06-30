---
name: update-agent
description: "Take a previously created agent and update it — applying a user-provided change prompt — by running it through the full forge-agents v2 flow: re-author every changed instruction line through the four-member debate gate, determinism review on every AI artifact, the aislop-style 95-floor code-quality gate on every regenerated file, the /analyze cross-artifact consistency gate, a re-judge plus the 10-round keep-if-improved tournament, the dynamic code-review gate (every agent in agent-foundry/agents/code-review/ must score the updated code >=85, no exception, looping until it does — across all four frameworks and the judge, for every affected agent), and the file-completeness + output-contract guardrails and golden regression suite — all under regression protection so an update can never silently degrade the agent. Use this skill whenever the user wants to update, upgrade, modify, revise, retrofit, or bring-up-to-standard an existing agent and supplies an instruction for the change. Invocation: 'update-agent <agent_name> <prompt...>' where <agent_name> is the existing agent (e.g. api-tester-validate-request-payloads) and <prompt...> is the change to make. Trigger on phrasings like 'update-agent X ...', 'update agent X to ...', 'upgrade X so that ...', 'modify the X agent to ...', 'bring X through the new flow and make it ...'. Requires a forge-agents foundry (agent-foundry/) to already exist; pairs with the forge-agents and fight-camp skills."
---

# Update Agent

Bring **one existing agent** up to the forge-agents v2 standard while applying a
**change the user describes**. It is the brownfield counterpart to forge-agents:
forge-agents builds four-of-the-same from scratch; `update-agent` takes an agent
that already exists in the foundry and re-runs it through every v2 gate, folding in
the user's requested change — and it guarantees the update never makes the agent
worse (regression protection).

## Invocation

```
update-agent <agent_name> <prompt ...>
```

- `<agent_name>` — the existing agent's name or short name, e.g.
  `api-tester-validate-request-payloads` or `validate-request-payloads`.
- `<prompt ...>` — free-form: the change to make, e.g.
  `update-agent api-tester-validate-request-payloads also cover PATCH request bodies and treat empty arrays as invalid`.

Inside Claude Code: `/update-agent <agent_name> <prompt>`. Direct/CI form:
`python scripts/update_agent.py <agent_name> "<prompt>" --workspace <repo>/agent-foundry`.

## Governing rules

This skill obeys the **forge-agents constitution**
(`../forge-agents/references/constitution.md`) in full — same invariants, same 95
code-quality floor, same "built for the simplest model" (deterministic scripts do
the work; only a debate-gate ambiguity or a guardrail/regression failure halts),
same backend default (current Claude Code session → Ollama). It **reuses** the
foundry's scripts and gates rather than reimplementing them; it adds only the
locate → apply-change → regression-protect orchestration.

**Regression protection (the rule unique to updates).** An update may not lower the
agent's judged metric below its recorded golden baseline. If the user's change
improves the metric, adopt it. If it would regress the metric, **hard-halt and ask
the user** — unless the user's prompt explicitly states the change is allowed to
trade off the metric (e.g. "even if it lowers exact-match"), which is recorded.

**Code-review gate (additive, never replaces the regression gate).** Any time an
update creates or modifies code — every framework `run.py`, the judge `score.py`,
and any code an affected agent produces — that code must score **≥ 85 on every
agent discovered in `agent-foundry/agents/code-review/`** before the update can
complete. The reviewer set is **dynamic**: it is exactly whatever agents are in
that folder at run time, however many — never a hardcoded count or list. **Every
discovered reviewer must run for every code target; one reviewer below 85, one
reviewer that did not run, an empty folder, or a receipt whose reviewer set does
not equal the folder all fail the update.** On failure the gate **hard-halts**,
shows the failing reviewers' notes, the code is rewritten, and the full reviewer
set re-runs — **looping with no cap until every reviewer is ≥85**. The threshold is
a floor (may be raised, never lowered) and the gate is never waived. This runs
**in addition to** the regression gate above: both must pass. Enforced by
`scripts/code_review_gate.py`; see `references/code-review-gate.md`. Each gate run
discovers the reviewer set with `discover_perspectives()` and the no-bypass check
uses `receipt_matches_folder()`.

**Multi-agent fan-out.** If the update affects more than one agent, the code-review
gate **and** the regression check run for **each affected agent** and **every one
must pass** — no exception, no skip. (Pass `--affected <group>/<name>` per extra
agent, or list them in the report.)

**Self-awareness.** When an update writes or revises an agent's system prompt —
across **all four frameworks and the judge** — that prompt must state that ALL code
the agent creates will be reviewed by **every agent in `agents/code-review/`**
(however many) and must score **≥ 85 on each, no exception, looping until it does**,
and must point to `agents/code-review/` and to the shared memory
(`references/memory-everos.md`). If an affected code-producing agent's prompt lacks
this, the update **adds** it.

## Flow

Read `references/flow.md` for the full procedure. Control flow:

### Phase 0 — Locate, snapshot, back up
1. Resolve `<agent_name>` to `agent-foundry/agents/<group>/<name>/` (accept the
   short name; disambiguate if needed). Confirm the foundry exists
   (`verify_build.py --phase 4`). If the agent doesn't exist, stop and say so —
   this skill updates existing agents, it does not create new ones (use
   forge-agents for that).
2. Record the **baseline**: the agent's current judged score and its golden
   baseline. This is the floor the update must not fall below.
3. Back up the agent's current prompt, runners, judge metric, and registration.

### Phase 1 — Capture the change (the user's prompt)
Write the user-provided prompt to `workspace/update_spec-<name>.md` as the change
specification: what to add / remove / alter, and whether a metric tradeoff is
explicitly permitted. This is the brownfield equivalent of the specify phase.

### Phase 2 — Re-author through the debate gate
Apply the change to the agent's instruction lines **one line at a time**. Every
**new or changed** line passes the four-member debate gate before it is written;
unchanged lines that previously passed are re-verified, not re-litigated. Run a
**determinism review** on the updated prompt and the **95 code-quality gate** on any
regenerated `run.py` / runner / `score.py`. (Debate gate, determinism, and quality
gate references all live in forge-agents.)

**Code-review gate at this point (all four frameworks + the judge).** Any code this
phase regenerates — the **LangGraph, CrewAI, Claude Code subagent, and Claude Agent
SDK** `run.py` dispatchers, and the judge's `score.py` — is created/modified code,
so it must pass the code-review gate: **≥ 85 on every reviewer discovered in
`agents/code-review/`** (however many), no exception. If any reviewer scores below
85, hard-halt, show its notes, rewrite that file, and re-run the full reviewer set;
loop until every reviewer is ≥85 for every regenerated file. When this phase writes
or revises the system prompt, add the **self-awareness clause** (see Governing
rules) to the prompt across all four frameworks and the judge.

### Phase 3 — Analyze
Run `/analyze`: the updated prompt must stay consistent with the judge metric,
task_spec, and constitution. If the change alters what the agent emits, update the
judge `metric.json` + `score.py` to match (and record that the metric moved). A
contradiction hard-halts and asks the user.

### Phase 4 — Re-judge, improve, regression-check
1. Run the updated agent against the judge.
2. **Regression gate:** if the new score < golden baseline and no tradeoff was
   authorized, hard-halt and ask the user; otherwise continue.
3. Run the 10-round keep-if-improved tournament
   (`../forge-agents/references/improvement-loop.md`) to recover/raise the score —
   or, for per-framework divergence, hand to the **fight-camp** skill. **Every round
   that rewrites code re-runs the code-review gate**: a self-revision that drops any
   reviewed file below 85 on any reviewer in `agents/code-review/` is rejected,
   exactly as a metric regression is.
4. The post-update best becomes the **new golden baseline**
   (`golden_run.py --derive`).
5. **Code-review gate (all four frameworks + the judge), every affected agent.** Run
   `scripts/code_review_gate.py --workspace <foundry> --agent <group>/<name>` for the
   updated agent **and every other affected agent** (`--affected <group>/<name>` per
   extra). It discovers every reviewer in `agents/code-review/` at run time and
   scores every code target — the four framework `run.py`, the judge `score.py`, and
   any produced code — at **≥ 85 on every reviewer, no exception**. For each affected
   agent it also re-checks the regression baseline (hold-or-improve, never drop) and
   that the touched behavior still works. Any reviewer < 85, any missing
   reviewer/target, an empty folder, a receipt ≠ folder, or a regression
   **hard-halts**; rewrite and loop until every reviewer is ≥85 for every affected
   agent. After every gate run, record it to the shared memory (see Phase 5).

### Phase 5 — Verify and stage
1. `verify_build.py --phase 6` + `verify_files.py`: every file present and correct,
   the `.claude/agents/<name>.md` registration still resolves, no stray
   `agent-foundry/.claude/agents/`.
2. Golden regression suite passes (no regression below the *prior* baseline unless
   authorized).
3. **No-bypass code-review completion contract (every affected agent).** The update
   may **not** complete unless, for **every affected agent**, a
   `results/_global/code-review-<TS>.json` receipt exists with `status: pass`, the
   receipt's reviewer set **equals** the current contents of `agents/code-review/`
   (`receipt_matches_folder()`), **and** the regression gate also passed. A
   does-not-apply receipt (no created/produced code) passes but must still exist.
   This is checked in addition to — never instead of — the "improve or hold, never
   drop" regression rule.
4. **Memory.** After every gate run, write to the shared EverOS pool
   (`references/memory-everos.md`): the discovered reviewer set, the code reviewed,
   each reviewer's rating and notes, which failed, the fixes that reached ≥85, the
   final pass, and — for multi-agent updates — the per-affected-agent result and the
   regression check; plus the update itself (what was touched, why, what it
   affected). Store under the shared `project_id`/`app_id` with each affected agent's
   `agent_id` so any future agent or update can read what it will be tested against.
5. Write a **diff report** (`workspace/update-report-<name>.md`): old vs new prompt,
   score delta, metric changes, files touched, **and the code-review result per
   affected agent** (reviewer set size, min rating, pass). Present it. Routine,
   non-regressing updates that pass the code-review gate are applied and reported;
   anything that regresses, fails a reviewer, or is ambiguous halts for the user's
   decision.

## Output

```
agent-foundry/
├── agents/<group>/<name>/...           # updated prompt + runners (in place)
├── judge/<group>/<name>/metric.json    # updated iff the change moved the metric
├── tests/golden/<group>/<name>/golden.json   # new baseline = post-update best
├── results/_global/code-review-<TS>.json     # code-review gate receipt (per affected agent)
├── memory/code-review/update-<ts>.md   # EverOS pool record of the gate run + update
├── workspace/
│   ├── update_spec-<name>.md           # the user's change prompt, recorded
│   └── update-report-<name>.md         # diff + score delta + files touched + code-review result
└── archives/update-<name>-<ts>/        # backup of the pre-update agent
```

## What it does NOT do

It does not create new agents (forge-agents), does not change the task itself (only
the agent's prompt/behavior toward the same task and metric, unless the change
explicitly redefines the metric), and never auto-adopts a regressing update.
