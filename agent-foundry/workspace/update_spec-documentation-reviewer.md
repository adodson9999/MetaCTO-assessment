# Update Spec — documentation-reviewer (n603)

Agent: `general/documentation-reviewer`
Backup: `archives/update-documentation-reviewer-20260628T142703/`
Tradeoff authorized: **false** (changes raise correctness; regression gate must hold or improve)

## User prompt (verbatim)

> Update the documentation-reviewer agent's adjudication instructions so the two
> failure modes below can never recur, without changing the six-key JSON output
> contract, the three verdict strings, the read-only no-tools constraint, or the
> three-pass search behavior. Apply these as added or altered instruction lines:
>
> 1. Add an instruction that the agent must rank ALL collected matching lines by
>    their file's modified timestamp, most-recent first, before selecting a source
>    of truth, and must never reduce the matching lines to one line before ranking.
> 2. Alter the conflict-resolution instruction so it states explicitly that the
>    source-of-truth line is the line from the file with the most-recent modified
>    timestamp, that a newer file always overrides an older file even when the older
>    line is longer or more specific or looks more authoritative, and that every
>    other matching line goes into other_matches.
> 3. Add a self-check instruction that, before committing the verdict, the agent
>    confirms "source_of_truth" names the newest matching file and that no line in
>    other_matches has a more recent modified timestamp than the source-of-truth
>    line; if one does, it has inverted the tie-break and must swap them so the
>    source-of-truth timestamp is >= every other-match timestamp.
> 4. Add an instruction that "documented_expected" is taken only from the
>    source-of-truth line — never from an other_matches line and never from the bug
>    report's claimed Expected Result, which is frequently a decoy stating a wrong
>    value.
> 5. Alter the verdict instruction so it states the decision is made by comparing
>    the observed Actual Result against documented_expected and nothing else: emit
>    "yes" only when observed differs from documented_expected, emit "no" when
>    observed matches documented_expected, and give the report's claimed Expected
>    Result zero weight in this comparison.
> 6. Add a final consistency-gate instruction: after drafting "reason", verify its
>    wording and the "verdict" string agree before returning; do not return the JSON
>    object until source_of_truth names the newest matching file, documented_expected
>    came only from that line, the verdict compares observed against documented_expected
>    rather than the report's claim, and the reason text and verdict string say the
>    same thing.
>
> Carry the two worked cases (limit=0 newest-file-wins → "no"; token-expiry
> default-60 ignore-claimed-30 → "no") into the instructions as concrete anchors.
> Do not authorize any metric tradeoff.

## Parsed summary

### Add
- Rank-all-matches-by-mtime-before-selecting line (change 1).
- Newest-file-wins self-check before committing verdict (change 3).
- documented_expected sourced only from source-of-truth, claimed-Expected is a decoy (change 4 — strengthens existing L17/L19).
- Final consistency gate: reason wording must agree with verdict string; return only when all four invariants hold (change 6).
- Two worked anchors: BR-002 (limit=0) and BR-004 (token expiry).

### Alter
- Conflict-resolution line: newer file overrides older even when older is longer/more specific/more authoritative; all other matches → other_matches (change 2 — strengthens L12).
- Verdict line: decide by comparing observed vs documented_expected only; claimed Expected gets zero weight (change 5 — strengthens L14).

### Invariants held (must NOT change)
- Six-key JSON output contract: verdict, source_of_truth, other_matches, documented_expected, observed, reason.
- Three verdict strings: yes | no | missing-docs.
- Read-only, no-tools, no-subprocess, no-HTTP constraint.
- Three-full-pass search behavior.

## Baseline (FLOOR)
- Golden baseline `verdict_accuracy_pct` = **100.0** (oracle ceiling).
- Latest live judged score (RUN-20260628-025411) = **50.0%** — BR-002 + BR-004 failing (the two inversions this change fixes).
- The update must not end below FLOOR; expected direction is 50 → 100 once re-judged live.

## Failure modes targeted (from the autopsy)
- **BR-002 (recency tie-break inverted):** gold source_of_truth = `cli/products.md` (mtime 2026-06-25, "no cap"); the older `reference/products.md` (2026-06-10, "max 100") must go to other_matches. observed "all 194 returned" matches "no cap" → verdict `no`.
- **BR-004 (verdict label contradicts its reasoning):** docs say default 60 min; report *claims* it expected 30; observed expired at 60 → observed matches docs → verdict `no`. "yes" must not be emitted merely because the report asserted 30.
