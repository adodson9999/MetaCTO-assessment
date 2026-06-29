# /analyze — Cross-Artifact Consistency Gate

Borrowed from spec-kit's `/analyze`, this gate runs in **Phase 3.5** (after the
four agents are authored, before the judge is built). It proves that every
artifact the build has produced so far agrees with every other and with the
constitution. It is **additive** to the Phase 6 self-review, not a replacement.

Enforcer: `scripts/analyze.py`. It writes `results/_global/analyze-<TS>.json` and,
on a contradiction, **hard-halts and asks the user** (constitution Article V
exception 2).

## What it cross-checks

1. **Spec ↔ agents.** Every requirement in `task_spec.md` is addressed by all four
   agent prompts; no agent prompt invents scope the spec never asked for.
2. **Agents ↔ agents.** The four are doing the *same* task — no framework shell
   has drifted the task (e.g. one agent emits 6 payload types, another 5).
3. **Agents ↔ metric.** The judge's metric can actually be computed from the
   fields the agents emit. If the metric needs `field X` and no agent emits it,
   that is a contradiction.
4. **Everything ↔ constitution.** No artifact violates an Article. Article I items
   are checked mechanically; Articles II–VII are checked by the model with a
   short justification recorded.
5. **Coverage.** No orphaned requirement (in spec, in no agent) and no orphaned
   capability (in an agent, in no requirement).
6. **API-testing standards (when applicable).** The ten standards in
   `references/api-testing-standards.md` are satisfied by each agent — counts,
   labels, exclusion rules, thresholds.

## Output

```json
{
  "status": "pass | fail",
  "ts": "<iso8601>",
  "checks": [
    {"id": "spec-agents", "status": "pass"},
    {"id": "agents-metric", "status": "fail",
     "detail": "metric exact_match needs 'expected' field; crewai prompt omits it",
     "fix_hint": "add 'expected' to crewai labeled-array schema"}
  ],
  "constitution": [{"article": "I.4", "status": "pass"}]
}
```

## Failure behavior

```
run analyze.py
if status == fail:
    HARD-HALT
    show each failed check with its detail + fix_hint
    ask the user to approve the fix or rewrite the offending artifact
    re-run analyze.py
# pass is required before Phase 4 (judge build)
```

`verify_build.py` later confirms that an `analyze-<TS>.json` with `status: pass`
exists (guardrails item 3), so a build cannot skip this gate.
