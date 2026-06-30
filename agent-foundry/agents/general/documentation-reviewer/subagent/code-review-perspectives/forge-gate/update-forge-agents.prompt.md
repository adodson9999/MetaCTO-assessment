# Claude Code prompt — add the code-review gate to the `forge-agents` skill

> Hand this entire file to Claude Code with the repository open. Everything here is
> **additive**: do not remove, weaken, or reorder anything already in the skill.

---

You are Claude Code, working in the repository that contains the `forge-agents`
skill at `.claude/skills/forge-agents/`. Add the code-review gate into the skill's
flow by doing Parts 1–4 below, in order. The gate's reviewer set is **dynamic** —
it is every agent discovered in `agents/code-review/` at run time, however many
there are; never hardcode a count or list.

## Part 1 — Create the gate package in the skill

The canonical files already exist in this repo at:
`agent-foundry/agents/general/documentation-reviewer/subagent/code-review-perspectives/forge-gate/`

Copy them into the skill (create `tests/` and `tests/golden/` if missing):

| source (forge-gate/)            | target (in `.claude/skills/forge-agents/`)     |
|---------------------------------|------------------------------------------------|
| `code-review-gate.md`           | `references/code-review-gate.md`               |
| `code_review_gate.py`           | `scripts/code_review_gate.py`                  |
| `test_code_review_gate.py`      | `tests/test_code_review_gate.py`               |
| `code-review-gate.golden.json`  | `tests/golden/code-review-gate.golden.json`    |

These provide: the enforcer (`code_review_gate.py`, which discovers the reviewer
set from `agents/code-review/` via `discover_perspectives()`, applies the ≥85
threshold, loops on failure, writes a `results/_global/code-review-<TS>.json`
receipt, and exposes `receipt_matches_folder()` for the no-bypass check), the spec
(`code-review-gate.md`), deterministic golden cases, and unit tests.

Prerequisite: the reviewers must exist at
`agents/code-review/<short>/subagent/code-review-<short>.md`. If they do not, build
them first from
`agent-foundry/agents/general/documentation-reviewer/subagent/code-review-perspectives/forge-starters.md`.
The gate hard-errors (exit 2) if `agents/code-review/` is empty.

## Part 2 — Wire the gate into the skill (additive edits)

**2a. `references/constitution.md` — add invariant Article I.10** (after I.9, do not
change the existing nine):

> 10. **Code-producing builds pass the code-review gate at ≥85, no exception.** Any
>     code an agent produces — and, when the built agent is code-producing, the code
>     it generates — must score **≥85 on every code-review agent present in
>     `agents/code-review/`** (the set discovered at run time, however many — no
>     fixed count) before the build reports "done". On a failure the flow hard-halts
>     and loops until every reviewer is ≥85. The threshold is a floor (may be raised,
>     never lowered); the gate is never waived. Enforced by
>     `scripts/code_review_gate.py`; verified by `verify_build.py`. See
>     `references/code-review-gate.md`.

**2b. `references/guardrails.md` — add deliverable item 9:**

> ### 9. Code-review gate (Article I.10)
> - `results/_global/code-review-<TS>.json` exists (the gate always runs, writes a receipt).
> - The receipt's reviewer set equals the current contents of `agents/code-review/` (no stale/short-receipt bypass).
> - When `applies` is true, `status` must be `pass`: every code target scored ≥85 on every reviewer discovered in `agents/code-review/`. Any rating <85, any missing reviewer/target, or an empty set hard-halts the build. Never waived or lowered.

**2c. `SKILL.md` — add a spec-kit table row and a Phase 6 completion step:**

- Table row: `| checklist | **Phase 6.5 — code-review gate** | every reviewer in agents/code-review/ ≥85 over all created/produced code |`
- Phase 6, new step 4: "**Code-review gate (Phase 6.5).** `scripts/code_review_gate.py --agent <group>/<name>` discovers and runs every reviewer in `agents/code-review/` over every code file the build created (and the agent's produced code when code-producing). Pass = every target ≥85 on every discovered reviewer. On any sub-85: hard-halt, show the reviewer notes, rewrite, loop until all ≥85. See `references/code-review-gate.md`."

**2d. `references/cli.md` — add the command row:**
`| `forge code-review-gate` | `scripts/code_review_gate.py` | 6.5 |`

**2e. `scripts/verify_build.py` — recognize the group and check the receipt (no
bypass):**

1. Add `"code-review"` to the groups in `agent_dirs()`:
   `for group in ("api-tester", "general", "code-review"):`
2. Add this check and call it inside the `if args.phase == 6:` block (after `check_quality(ws, r)`):

```python
def check_code_review_gate(ws: Path, r: Report) -> None:
    import sys as _sys
    _sys.path.insert(0, str(ws / "scripts"))
    try:
        import code_review_gate as crg
    except Exception:
        crg = None
    receipts = sorted(glob.glob(str(ws / "results" / "_global" / "code-review-*.json")))
    r.check(bool(receipts), "code-review gate receipt", "no code-review-*.json (gate not run)")
    if not receipts:
        return
    try:
        data = json.loads(Path(receipts[-1]).read_text())
    except Exception as e:
        r.check(False, "code-review gate receipt parseable", str(e)); return
    applies = bool(data.get("applies")); status = data.get("status")
    r.check((not applies) or status == "pass",
            "code-review gate >=85 (every reviewer in agents/code-review/, no exception)",
            f"status={status}, min_rating={data.get('min_rating')}; rewrite code below 85")
    if applies and crg is not None:
        r.check(crg.receipt_matches_folder(data, ws),
                "code-review reviewer set matches agents/code-review/",
                "receipt set != folder (stale/short receipt) — re-run the gate")
```

**2f. Optional config** in the generated `agent-foundry/config.toml`:
`[code_review_gate]\napplies = false   # auto-detect from task_spec; true forces the gate\nthreshold = 85    # floor; may be raised, never lowered`

## Part 3 — Enforce the flow at EVERY point (the requirements)

Add the gate into the skill's flow so all of the following hold:

1. **Dynamic reviewer set, no bypass.** The required reviewers are exactly the agents
   in `agents/code-review/`, enumerated at run time. Every discovered reviewer must
   run and score ≥85 for every code target. Fail if the folder is empty, if any
   discovered reviewer produced no verdict, or if the receipt's set ≠ the folder. No
   hardcoded count or list anywhere.
2. **Pass rule — every reviewer ≥85, no exception.** One reviewer below 85 fails the
   build; a discovered reviewer that did not run is a failure, not a skip.
3. **On failure — hard-halt and loop.** Show the failing reviewers' notes, rewrite
   the code, re-run the full set; loop with **no cap** until every reviewer is ≥85.
   The build cannot report "done" while any reviewer is below 85.
4. **At every point — all four frameworks and the judge.** This is not a single
   step. At every phase where any agent creates or modifies code, state and enforce
   the gate and require it to pass before that code is accepted — repeating it in the
   text of each such phase. This includes Phase 3 authoring for **each of the four
   framework implementations** (LangGraph, CrewAI, Claude Code subagent, Claude Agent
   SDK — every `run.py` and any code each produces), Phase 4 building **the judge**
   (its `score.py` and any code it generates), the Phase 4.5 improvement loop
   (**every** self-revision, in all four frameworks and the judge), and any other
   code-emitting point. For an agent that is itself a coding agent, wrap the gate
   around **every single point of its coding process** in all four frameworks and the
   judge. No agent the skill touches, no framework, no judge step, and no line of
   created code is exempt.
5. **Code-producing agents carry the gate in their own flow.** When the agent under
   build will itself produce code (detect from `task_spec.md` or
   `config.toml [code_review_gate].applies = true`), bake this same dynamic gate into
   that agent's own runtime flow so its produced code is gated at ≥85 every time.
6. **Memory.** After every gate run, write to the shared EverOS pool
   (`references/memory-everos.md`): the discovered reviewer set, the code reviewed,
   each reviewer's rating and notes, which failed, the fixes that reached ≥85, and
   the final pass — under the shared `project_id`/`app_id` with the agent's
   `agent_id`, so any future agent or build can read what it will be tested against.
7. **Self-awareness.** Add to every agent's own system prompt — across all four
   frameworks and the judge — an explicit statement that ALL code it creates will be
   reviewed by **every agent in `agents/code-review/`** (however many) and must score
   ≥85 on each, no exception, looping until it does. Point to `agents/code-review/`
   and to the shared memory, so the agent knows the standard before writing code.

## Part 4 — Verify, review the tests, and only then report done

1. Run and require green: `pytest -q tests/test_code_review_gate.py`;
   `python scripts/code_review_gate.py --agent code-review/minimalist --workspace <foundry> --dry-run`;
   `python scripts/verify_build.py --phase 6 --workspace <foundry>`.
2. **Review and verify the new guardrails, golden cases, and unit tests — do not add
   them blindly.** For each, record in one line the reason it exists and what it
   proves, including that it proves there is no way around running every reviewer in
   the folder (the empty-set, missing-reviewer, added-reviewer, and
   receipt≠folder cases). Confirm each unit test would fail if the logic broke (no
   tautologies) and each guardrail checks a real contract condition. Reject or
   rewrite anything whose logic does not hold or whose reason cannot be stated.
3. Do not report the change complete until Parts 1–4 are done, the gate is referenced
   and enforced at every code-producing point across all four frameworks and the
   judge, and all tests/guardrails pass.

Constraints: additive only; preserve every existing phase, gate, and file; reviewer
set discovered from `agents/code-review/` at run time with no hardcoded count and no
way to skip/omit a reviewer; enforced at every code-producing point across all four
frameworks and the judge; every review recorded in shared memory; every agent's
prompt states it will be reviewed by every reviewer in the folder at ≥85 no
exception; reuse the copied forge-gate package; and do not accept any guardrail,
golden case, or unit test until its logic and reason are reviewed, justified, and
verified to pass.
