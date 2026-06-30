# Code-Review Gate — guardrail / golden / test review (Part 4)

Every guardrail, golden case, and unit test added when wiring the code-review gate
into `update-agent` is listed below with the one-line reason it exists and what it
proves. None is a tautology: each would fail if the stated logic broke. Together
they prove there is **no way around running every reviewer in `agents/code-review/`**
(empty-set, missing-reviewer, added-reviewer, receipt≠folder) for **every affected
agent**, while the existing regression gate still runs.

## Completion-contract guardrails (`scripts/update_agent.py`)

| Guardrail (function) | Real contract condition it checks | Proves |
|---|---|---|
| `code_review_contract_ok` → receipt is not None | a `results/_global/code-review-<TS>.json` receipt exists | the update cannot complete without the gate having run |
| `code_review_contract_ok` → `status == "pass"` when `applies` | every target ≥85 on every reviewer | sub-85 code cannot complete |
| `code_review_contract_ok` → `receipt_matches_folder()` | receipt's reviewer set == current `agents/code-review/` | a stale/short receipt that omitted a reviewer cannot bypass |
| per-affected `is_regression(after, floor, tradeoff)` | each affected agent held-or-improved its baseline | the touched behavior didn't silently degrade (additive to the existing regression gate, never replacing it) |
| `self_aware_ok` (code-producing affected agents) | prompt references `agents/code-review/` and `85` | the agent's prompt states all its code is reviewed at ≥85 (self-awareness) |
| `affected_agents(primary, extra)` | every affected agent enumerated once, primary first | multi-agent fan-out runs the gate + regression for each, deduped |
| `record_memory(...)` | a memory record is written each run | every review + the update is recorded to the shared EverOS pool |

The gate run itself (`run_code_review_gate`) discovers the reviewer set with
`discover_perspectives()` at run time — no hardcoded count or list — and writes the
receipt the contract then verifies.

## New golden cases (`tests/golden/code-review-gate.golden.json`, appended)

| Case id | Proves |
|---|---|
| `multi-agent-all-affected-pass` | passes only when **every** affected agent's code is ≥85 on **every** discovered reviewer |
| `multi-agent-one-affected-one-reviewer-below-fails` | one reviewer <85 on **one** affected agent fails the whole update (no exception) |
| `multi-agent-missing-target-for-one-affected-fails` | an affected agent with **no verdicts** is a failure, not a skip |
| `multi-agent-dynamic-arbitrary-count-all-pass` | per-affected every-reviewer-≥85 holds for **any** reviewer count (here 5, not the default set) |
| `multi-agent-dynamic-missing-one-reviewer-on-one-affected-fails` | a discovered reviewer that **did not run** on one affected agent fails (no skip) |

Mutation-tested: an "always-pass" gate is caught by the multi-agent fail-cases, and a
"skip-missing-reviewer" gate is caught by the two missing-reviewer/target cases.

## New unit tests (`tests/test_code_review_gate.py`, appended; existing tests unchanged)

| Test | Proves (and why it fails if logic broke) |
|---|---|
| `test_discovery_is_exactly_the_folder_set_ignoring_noise` | required set == exactly the canonical reviewer dirs; fails if a README/half-built dir were counted |
| `test_per_affected_every_reviewer_at_85_any_count_passes` (1/3/7/25) | every reviewer ≥85 on both affected agents passes at any count; fails if count/agent ignored |
| `test_per_affected_one_reviewer_below_on_one_agent_fails` (3/7/25) | one 84 on one of two agents fails at any count; fails if sub-85 slipped through |
| `test_multi_agent_missing_verdict_for_one_agent_fails` | a no-verdict affected agent fails; fails if zero-verdict were treated as pass |
| `test_multi_agent_empty_reviewer_set_cannot_pass` | empty folder cannot pass even with code targets; fails if zero-reviewer bypass allowed |
| `test_contract_missing_receipt_fails` | no completion without a receipt; fails if None accepted |
| `test_contract_status_not_pass_fails` | status != pass blocks; fails if status ignored |
| `test_contract_receipt_neq_folder_fails` | short/stale receipt rejected; fails if no-bypass cross-check skipped |
| `test_contract_pass_when_receipt_matches_and_passes` | a correct receipt passes; fails if valid updates were wrongly blocked |
| `test_contract_does_not_apply_still_needs_receipt` | a does-not-apply receipt passes but must exist |
| `test_existing_regression_gate_still_runs` | regression predicate intact (below→regress, tradeoff→allowed, ≥→ok); fails if dropped/inverted |
| `test_affected_agents_fanout_dedup_primary_first` | every affected agent enumerated once, primary first; fails if dropped/duplicated |
| `test_self_aware_clause_required_for_code_producing_prompt` | code-producing prompt must cite `agents/code-review/` + ≥85; fails if a prompt lacking the clause were accepted |

## Run commands

```bash
pytest -q tests/test_code_review_gate.py            # 51 passed
python scripts/code_review_gate.py --workspace <foundry> --agent <group>/<name> --dry-run
```

Dry-run note: on a real agent with created code, the dry-run **discovers the full
reviewer set and writes a folder-matching receipt**, then reports `status: fail`
(exit 1) because no verdicts were produced — this is the no-bypass property, not a
wiring error: a run that did not actually review the code is never a pass. A green
exit happens only for a genuine does-not-apply agent (no created/produced code).
