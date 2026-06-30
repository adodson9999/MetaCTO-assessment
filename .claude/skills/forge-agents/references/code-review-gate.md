# Code-Review Gate — created code passes every reviewer in agents/code-review/ at ≥85

> Install target: `.claude/skills/forge-agents/references/code-review-gate.md`

A build-completion gate (Phase 6). **No code-producing build reports "done" until
every code file it created scores ≥ 85 on every code-review agent present in
`agents/code-review/` — the set discovered at run time, however many there are, no
exception.** This is the LLM-graded companion to the mechanical
aislop 95 gate (Article II): aislop scores the code statically; this gate runs the
real review agents over it.

Enforcer: `scripts/code_review_gate.py`. Receipt:
`results/_global/code-review-<TS>.json`. Governing rule: **constitution Article
I.10**. On failure: **hard-halt and ask the user** (Article V exception 2) — the
code is rewritten until it passes; the gate is never waived or lowered.

## When the gate applies (the trigger)

The gate runs on every build and always writes a receipt. It **applies** (status
can fail the build) when **either** is true:

1. **Created code, always.** The build itself wrote code files for the agent under
   construction (the four `run.py` dispatchers, `judge/<group>/<name>/score.py`,
   and any other source the build generated). "Any code that is created has to
   pass" — these are created code.
2. **The built agent produces code.** The agent under construction is a
   code-producing agent — a QA-automation agent, a software-engineer agent, a
   refactoring/codegen agent, or anything whose task is to write, generate, or
   modify code. Detected from `task_spec.md` (keywords: code, script, implement,
   refactor, codegen, "qa automation", "software engineer", "test automation",
   programming, compile, function/class/module) or forced by
   `config.toml [code_review_gate].applies = true`. When it applies this way, the
   agent's **produced code** (its outputs on the held-out/golden inputs, written to
   `results/<group>/<name>/produced/`) is also a gate target.

If neither holds (e.g. the agent emits only JSON verdicts or prose, never code),
the receipt records `applies: false` and the gate does not block — but the receipt
must still exist.

## The threshold — 85, a floor, no exception

- Every gate target × **every reviewer discovered in `agents/code-review/`** must
  score **≥ 85**. The set is enumerated fresh at run time — however many there are —
  never a hardcoded count or list.
- **Every discovered reviewer must run for every target.** A discovered reviewer
  that did not run is a failure, not a skip; you cannot pass by running fewer
  reviewers, and an empty folder cannot pass.
- `config.toml [code_review_gate].threshold` defaults to **85** and may be **raised,
  never lowered**. A target that cannot reach 85 on some lens is **rewritten** until
  it does (same discipline as the 95 aislop floor); the gate is not waived.

## The reviewer set is dynamic (group `code-review`)

The reviewers live at
`agents/code-review/<short-name>/subagent/code-review-<short-name>.md` and each
emits exactly `{"rating": <int 0-100>, "notes": "<string>"}`. The required set is
**discovered from the folder at run time** by `discover_perspectives()` — every
directory holding a canonical `code-review-<name>.md` is a required reviewer. The
count is never hardcoded: add a reviewer and it is required on the next run; remove
one and the set shrinks. The gate fails if the folder is empty — it must not be
bypassable with zero reviewers.

The set present today, for reference only (not an enforced list):

```
minimalist, math-correctness, system-design, device-stack, network, security,
vulnerability, unit-test, performance, logic-error, concurrency,
error-handling-resilience, data-integrity, memory-resource, maintainability,
api-contract, observability, dependency-supply-chain, adversarial-input,
domain-requirements, chaos-engineering
```

Each reviewer's emitted output is validated against the `{rating, notes}` schema
before its number is trusted (an output that fails the schema scores 0 for that
target × reviewer, which fails the gate).

## Targets (what gets reviewed)

For the agent under build at `agents/<group>/<name>/`:

- **Created code (always a target):** `agents/<group>/<name>/**/run.py`,
  `judge/<group>/<name>/score.py`, and any other source file the build wrote for
  this agent.
- **Produced code (target only when the agent is code-producing):** every file
  under `results/<group>/<name>/produced/` — the code the agent emitted on its
  held-out/golden inputs.

A target is reviewed as a whole file.

## Receipt schema (`results/_global/code-review-<TS>.json`)

```json
{
  "gate": "code-review",
  "applies": true,
  "threshold": 85,
  "status": "pass | fail",
  "ts": "<iso8601>",
  "agent_under_build": "<group>/<name>",
  "perspectives": ["... the reviewer set discovered in agents/code-review/ ..."],
  "perspective_count": 21,
  "targets": ["agents/<group>/<name>/subagent/run.py", "..."],
  "ratings": [
    {"target": "<path>", "perspective": "minimalist", "rating": 92, "notes": "..."}
  ],
  "min_rating": 87,
  "failures": [
    {"target": "<path>", "perspective": "security", "rating": 80, "notes": "<why + fix>"}
  ]
}
```

`status` is `pass` only when `applies` is `false`, OR every **discovered** reviewer
is present for every target and `min_rating >= threshold`. Any rating `< threshold`,
any missing reviewer/target, or an empty discovered set makes `status: fail`. The
receipt records the reviewer set it used; `verify_build` rejects it (via
`receipt_matches_folder`) if that set does not equal the current contents of
`agents/code-review/` — no stale or short-receipt bypass.

## How to run

```
forge code-review-gate                 # gate the current build (writes the receipt)
python scripts/code_review_gate.py --workspace <repo>/agent-foundry --agent <group>/<name>
```

The script discovers targets, runs the 21 reviewers over each (resolved backend,
Article VI), validates each `{rating, notes}`, applies the threshold, and writes
the receipt. The threshold/aggregation logic is pure Python and deterministic; only
the ratings come from the model. Each reviewer run is wrapped by the determinism
review (`references/determinism.md`) so a pass is not a lucky single sample.

## Failure behavior

```
run code_review_gate.py
if status == fail:
    HARD-HALT
    show each failure: target, perspective, rating, and the reviewer's notes (the fix)
    rewrite the offending code (never waive, never lower the threshold)
    re-run the gate
# a code-producing build cannot report "done" while status == fail
```

`verify_build.py --phase 6` confirms a `code-review-<TS>.json` receipt exists and,
when `applies` is true, that `status == pass`. The gate cannot be skipped.

## Interaction with other gates

- **aislop 95 gate (Article II):** mechanical, no LLM, static quality. This gate is
  LLM-graded review at 85 across 21 lenses. Both must pass.
- **Golden suite / determinism:** the gate's own pass/fail logic has golden cases
  and unit tests (`tests/golden/code-review-gate.golden.json`,
  `tests/test_code_review_gate.py`); each reviewer invocation is determinism-reviewed.
- **Improvement loop:** a self-revision that drops any reviewed file below 85 on any
  lens is rejected, exactly as a metric regression is.
