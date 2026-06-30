# RUN-ONE — complete ONE implementation plan per run

This is the prompt to get it started **one implementation plan at a time**. Each time you send the
block below to an agent that has the `update-agent` skill and access to this repo, it completes
exactly one plan end-to-end (load guardrails → run the verbatim prompt → run the test → verify),
records the result in `PROGRESS.md`, and stops. Re-send it to do the next one. It never skips and
never weakens a gate. (For an unattended all-39 sequential run instead, use `RUN.md`.)

```
You are running the api-tester implementation plans ONE AT A TIME. Complete exactly ONE plan this run, then stop.

1. PICK. Open implementation/PROGRESS.md. Going down the table in order, find the FIRST plan whose Status is "[ ]" (pending). That is THIS run's plan. If every row is "[x]", report "All 39 complete" and stop. If the first non-done row is "[~] in progress", treat it as this run's plan (a prior run halted on it) and resume it.

2. CLAIM. Set that plan's Status to "[~] in progress" in PROGRESS.md before doing anything else.

3. LOAD GUARDRAILS. Open implementation/<plan>-implementation-plan.md. Read Section 1 "Guardrails (force no hallucination)" and hold every rule for this run — especially: the feature is supplied at runtime; never assume, hardcode, name, or mention any specific URL, path, host, or feature; plan only and never guess a response; one JSON object on the exact contract; stay in lane and fail closed; deterministic + exhaustive; never fabricate a review receipt.

4. RUN THE PROMPT. Execute the plan's Section 2 "Prompt (run verbatim — miss no detail)" through the update-agent skill. Copy the entire `update-agent api-tester-<name> …` block EXACTLY as written — including its "## Standard compliance & lane-ownership clause (inserted into every agent)", "## Code review", and "## Runtime feature injection" sections. Do not summarize, reorder, or drop any detail.

5. TEST. When update-agent completes, run the plan's Section 3 "Test (verify the job was done correctly)" and confirm ALL of:
   - the agent emits a single JSON object with exactly its required top-level keys;
   - every title-named case is present (by role) with the correct shape and count, and no out-of-lane case appears;
   - the agent names NO specific URL, path, host, or feature anywhere (feature-agnostic);
   - the agent's system prompt (all four frameworks + the judge) contains the verbatim Standard compliance clause, the string references/agent-authoring-standard.md, and the Runtime feature injection clause;
   - a results/_global/ code-review receipt exists with status pass, reviewer set == agents/code-review/, every reviewer ≥85;
   - the golden baseline held or improved (no regression).

6. RECORD + STOP.
   - If everything passed: set the plan's Status in PROGRESS.md to "[x]" and append " — <today's date> · score <before>→<after> · code-review min <n> · test pass". Then STOP and report one line: agent, score before→after, code-review min rating, test pass, regression held/improved.
   - If anything hard-halts (debate-gate ambiguity, a reviewer below 85, a regression below baseline, or a failing test): leave the Status "[~]" and append " — HALTED <today's date>: <exact reason>". Then STOP and report the failing plan and the reason. Do NOT skip it, do NOT move to the next plan, do NOT lower any gate.

Complete ONE plan only, then stop. Send this prompt again to process the next pending plan.
```

## Notes

- **State lives in `PROGRESS.md`** — that ledger is how each run knows what's already done. Don't edit
  it by hand mid-run; let the runner update it.
- **One-at-a-time is the safe default here.** Long unattended runs of all 39 are prone to dropping;
  doing one plan per run keeps each unit small and lets you inspect the receipt + score delta before
  continuing.
- **Resumable.** If a run halts on a plan, the next send resumes that same plan (it stays `[~]`) rather
  than skipping ahead.
- **Prerequisites** (same as RUN.md): `agent-foundry/references/agent-authoring-standard.md`,
  `agent-foundry/registry/coverage-manifest.json`, and the `agents/code-review/` reviewer set must
  exist for the clause and tests to resolve.
