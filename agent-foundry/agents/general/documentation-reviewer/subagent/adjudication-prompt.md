# update-agent change prompt — documentation-reviewer adjudication fix

This is written for the `update-agent` skill. It is a single free-form change
prompt, scoped to the two adjudication inversions found in the autopsy (BR-002
recency tie-break inverted; BR-004 verdict label contradicting its own reasoning).
Both changes raise correctness, so no metric tradeoff is authorized — the
regression gate should improve or hold, never drop.

## Invocation

```
update-agent general-documentation-reviewer harden the adjudication step so the recency tie-break and the verdict definition can never be inverted, per the change prompt below
```

Inside Claude Code: `/update-agent general-documentation-reviewer <prompt below>`.
Direct/CI: `python scripts/update_agent.py general-documentation-reviewer "<prompt below>" --workspace <repo>/agent-foundry`.

## Change prompt (pass verbatim as <prompt...>)

Update the documentation-reviewer agent's adjudication instructions so the two
failure modes below can never recur, without changing the six-key JSON output
contract, the three verdict strings, the read-only no-tools constraint, or the
three-pass search behavior. Apply these as added or altered instruction lines:

1. Add an instruction that the agent must rank ALL collected matching lines by
   their file's modified timestamp, most-recent first, before selecting a source
   of truth, and must never reduce the matching lines to one line before ranking.

2. Alter the conflict-resolution instruction so it states explicitly that the
   source-of-truth line is the line from the file with the most-recent modified
   timestamp, that a newer file always overrides an older file even when the older
   line is longer or more specific or looks more authoritative, and that every
   other matching line goes into other_matches.

3. Add a self-check instruction that, before committing the verdict, the agent
   confirms "source_of_truth" names the newest matching file and that no line in
   other_matches has a more recent modified timestamp than the source-of-truth
   line; if one does, it has inverted the tie-break and must swap them so the
   source-of-truth timestamp is greater than or equal to every other-match
   timestamp.

4. Add an instruction that "documented_expected" is taken only from the
   source-of-truth line — never from an other_matches line and never from the bug
   report's claimed Expected Result, which is frequently a decoy stating a wrong
   value.

5. Alter the verdict instruction so it states the decision is made by comparing
   the observed Actual Result against documented_expected and nothing else: emit
   "yes" only when observed differs from documented_expected, emit "no" when
   observed matches documented_expected, and give the report's claimed Expected
   Result zero weight in this comparison.

6. Add a final consistency-gate instruction: after drafting "reason", verify its
   wording and the "verdict" string agree before returning — if the reason says
   observed matches or is consistent with the docs then verdict must be "no", and
   if the reason says observed differs from or contradicts the docs then verdict
   must be "yes" — and do not return the JSON object until source_of_truth names
   the newest matching file, documented_expected came only from that line, the
   verdict compares observed against documented_expected rather than the report's
   claim, and the reason text and verdict string say the same thing.

Carry these two worked cases into the instructions as concrete anchors. Recency
case: reference/products.md (modified 2026-06-10) says "limit of 0 returns up to a
maximum of 100" while cli/products.md (modified 2026-06-25) says "passing --limit 0
returns all products, no cap" — the newer cli/products.md is the source of truth
with documented_expected "no cap", and observed "all 194 returned" matches it, so
verdict is "no". Verdict-definition case: reference/auth.md says "accessToken
expires after expiresInMins minutes (default 60)", the report claims it expected 30
minutes, observed is that the token stayed valid until 60 minutes — observed (60)
matches documented_expected (60), so verdict is "no" and "yes" must not be emitted
merely because the report asserted 30.

Do not authorize any metric tradeoff; these changes are expected to raise or hold
the judged exact-match score, so the regression gate must not drop below the
recorded golden baseline.
