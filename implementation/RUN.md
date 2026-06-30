# RUN — complete ALL 39 plans in one pass, strictly one at a time

This is the prompt to get it started. Paste the block below **once** to an agent that has the
`update-agent` skill and access to this repo. It works through **all 39** implementation plans in a
single run, but **strictly one at a time** — it fully completes and verifies a plan, and records it in
`PROGRESS.md`, before it touches the next. It never runs two plans at once, never skips, and never
weakens a gate. Because it tracks state in `PROGRESS.md`, if the run is interrupted you just send the
prompt again and it resumes with no repeats.

(Prefer a manual step-through — one plan per send? Use `RUN-ONE.md` instead.)

```
You are running ALL api-tester implementation plans in ONE pass, but strictly ONE AT A TIME: fully complete and verify a plan — and record it — before you touch the next. Never run two plans at once. Work through every pending plan, then stop.

Repeat this loop until every plan in implementation/PROGRESS.md is "[x]" done (or you hard-halt):

A. PICK. In implementation/PROGRESS.md, going down the table in order, take the FIRST plan whose Status is "[ ]" pending. If the first non-done row is "[~] in progress" (left by an interrupted run), resume that one. If no pending/in-progress rows remain, output the final summary table and stop.

B. CLAIM. Set that plan's Status to "[~] in progress" in PROGRESS.md before doing anything else.

C. LOAD GUARDRAILS. Open implementation/<plan>-implementation-plan.md and hold every rule in its Section 1 — especially: the feature is supplied at runtime, so never assume, hardcode, name, or mention any specific URL, path, host, or feature; plan only and never guess a response; emit one JSON object on the exact contract; stay in lane and fail closed; deterministic + exhaustive; never fabricate a review receipt.

D. RUN THE PROMPT. Execute the plan's Section 2 "Prompt (run verbatim — miss no detail)" through the update-agent skill. Copy the entire `update-agent api-tester-<name> …` block EXACTLY — including its "## Standard compliance & lane-ownership clause (inserted into every agent)", "## Code review", and "## Runtime feature injection" sections. Summarize nothing; drop no detail.

E. TEST. When update-agent completes, run the plan's Section 3 and confirm ALL of:
   - the agent emits a single JSON object with exactly its required top-level keys;
   - every title-named case is present (by role) with the correct shape and count, and no out-of-lane case appears;
   - the agent names NO specific URL, path, host, or feature anywhere (feature-agnostic);
   - the agent's system prompt (all four frameworks + the judge) contains the verbatim Standard compliance clause, the string references/agent-authoring-standard.md, and the Runtime feature injection clause;
   - a results/_global/ code-review receipt exists with status pass, reviewer set == agents/code-review/, every reviewer ≥85;
   - the golden baseline held or improved (no regression).

F. RECORD, then continue.
   - If everything passed: set the plan's Status in PROGRESS.md to "[x]" and append " — <today's date> · score <before>→<after> · code-review min <n> · test pass"; add one line to your running report; then GO BACK TO STEP A for the next plan.
   - If anything hard-halts (debate-gate ambiguity, a reviewer below 85, a regression below baseline, or a failing test): leave the Status "[~]" and append " — HALTED <today's date>: <exact reason>"; STOP the whole run; and report the failing plan and the reason. Do NOT skip it, do NOT continue to other plans, do NOT lower any gate.

Never start a plan until the previous one is recorded "[x]". When every row is "[x]", output the final summary table — agent | score before→after | code-review min rating | test pass | regression held/improved — and confirm all 39 completed with none skipped.

If this run is interrupted, send this prompt again: it reads PROGRESS.md and resumes from the first not-done plan with no repeats.
```

## Notes

- **One prompt, one pass, one plan at a time.** A single send drives all 39 sequentially; each plan is
  finished and recorded before the next begins.
- **State + resumability live in `PROGRESS.md`.** That ledger is how the run knows what's done; don't
  hand-edit it mid-run. If the run drops, re-sending the prompt continues where it left off.
- **Fail-closed.** A hard-halt stops the whole run on the offending plan so you can decide — it never
  skips a plan or weakens a gate to keep going.
- **Prerequisites:** `agent-foundry/references/agent-authoring-standard.md`,
  `agent-foundry/registry/coverage-manifest.json`, and the `agents/code-review/` reviewer set must
  exist for the clause and tests to resolve.
