# Golden Regression Suite

A set of **golden test cases** each agent must pass. Re-run on every model or
system-prompt change to prove the agent's performance has not degraded
(constitution Article III). Golden cases are **auto-derived per agent** from its
`task_spec.md` and judge metric — there is no single fixed task; the suite fits
whatever the agent is tasked to do.

Enforcer: `scripts/golden_run.py`. Cases live in
`tests/golden/<group>/<short-name>/golden.json` inside the foundry workspace.
The suite runs at **build completion (Phase 6)** and again before any evolution
adoption (Phase 5); the build cannot report "done" until it passes
(guardrails item 4).

## Pass rule (metric threshold + structure, never prose)

A golden case passes when **both** hold:

1. **Metric threshold.** Judge metric ≥ recorded baseline − `tolerance`
   (`config.toml [golden].tolerance`, default 0.02 for fraction metrics; direction
   from `metric.json`). The baseline is the post-improvement-loop best
   (`references/improvement-loop.md`).
2. **Deterministic structure.** The structural assertions match exactly:
   counts, labels, constant values, schema shape, file layout. For an API-testing
   agent these are the Phase 2.5 counts (e.g. `N×7` null/empty states, 9
   wrong-type values, 2 missing-required variants per field, the maxlength array,
   boundary-point labels). Free-text LLM prose is never compared.

A case fails if the metric drops below threshold **or** any structural assertion
breaks — even when the number looks fine but the shape drifted.

## Auto-derivation

When an agent is finalized, `golden_run.py --derive` writes its `golden.json`:

```json
{
  "agent": "api-tester/create-postman-collection",
  "derived_from": {"task_spec": "task_spec.md", "metric": "judge/.../metric.json"},
  "baseline": {"metric_name": "exact_match_accuracy", "value": 0.83, "direction": "higher_is_better"},
  "tolerance": 0.02,
  "structure": {
    "required_fields": 8,
    "null_empty_states_per_field": 7,
    "wrong_type_values": 9,
    "missing_required_variants_per_field": 2,
    "expects_labeled_arrays": true
  },
  "cases": [
    {"id": "all-required-covered", "kind": "structure", "assert": "len(inv_all_null) == required_fields"},
    {"id": "metric-not-regressed", "kind": "metric", "assert": "value >= baseline - tolerance"}
  ]
}
```

- **API-testing agents** → structural cases come straight from
  `references/api-testing-standards.md` (the hard counts).
- **General agents** → cases come from the spec's stated correct-output shape plus
  the metric threshold. Where the spec gives concrete examples, those become
  exact-match structural cases.

## Backend for golden runs

Default: the **current Claude Code session**; if the skill is not connected to a
session, fall back to **Ollama** (constitution Article VI). The structural cases
are pure Python (no model calls) so they always run; the metric cases invoke the
resolved backend. Each metric case is wrapped in a determinism review so a "pass"
can't be a lucky single sample.

## Running it

```
forge test                 # run the whole golden suite (all agents)
forge test <group>/<name>  # one agent
golden_run.py --derive     # (re)derive baselines after the improvement loop
```

On regression `golden_run.py` exits non-zero, names the agent + case + the
expected-vs-actual, and the build hard-halts (Phase 6 step 2). Update a baseline
only deliberately (`--rebaseline`), never silently.
