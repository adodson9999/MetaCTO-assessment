# Phase 2.2 — Data Input (optional)

When the user supplies data for the agent to learn from, run this phase to ingest
it, **identify the patterns** relevant to the task, and fold the findings into the
spec and the judge's metric. If no data is supplied, skip the phase entirely.

This phase exists so the four agents can be built around real structure in the
user's data rather than assumptions — it sharpens `task_spec.md` before any agent
line is written.

## Inputs

Accept any of: CSV/TSV, JSONL, JSON, a folder of examples, log files, or a sample
of API request/response pairs. The user points the skill at a path inside the
workspace (data never leaves the sandbox — constitution Article VI / Article I.6).

## Procedure

1. **Profile (deterministic).** `scripts/data_profile.py` computes the mechanical
   facts first — no model needed: columns/fields, types, null rates, value ranges,
   cardinality, obvious keys, min/max lengths, enum-like fields. This is the cheap,
   reliable backbone (built for the simplest model).
2. **Identify patterns (AI, reviewed).** From the profile + a sample, the model
   names the patterns that matter for the task: recurring structures, constraints
   the data implies (e.g. "field `status` is always one of 4 values"), correlations,
   anomalies, and anything that should become a test or a metric. This pattern
   report is an AI artifact → it gets a **determinism review**
   (`references/determinism.md`); an unstable report is re-derived, not trusted.
3. **Fold into the spec.** Merge findings into `task_spec.md` (new constraints,
   concrete examples, edge cases) and flag any that should shape the judge metric
   or become golden structural cases.

## Pattern report format

`workspace/data_patterns.md`:

```markdown
# Data Patterns — <dataset>, <ts>
## Profile (deterministic)
- records: N · fields: [...] · types: {...} · null_rates: {...} · ranges: {...}
## Identified patterns
- [constraint] <field> is always <pattern> (support: X/N)  → becomes golden case
- [correlation] <a> ~ <b> ...                              → informs metric
- [anomaly] <description> (count: K)                       → edge case for agents
## Spec deltas
- add to task_spec: <concrete requirement / example>
```

## Guardrails for this phase

- The deterministic profile is the source of truth for counts; the model may
  interpret but not override the numbers `data_profile.py` produced.
- Every pattern that becomes a requirement must be **checkable** — phrase it so a
  golden structural case or the judge metric can test it.
- Nothing here bypasses the debate gate: when these findings turn into agent
  instruction lines in Phase 3, those lines still pass the gate one at a time.
