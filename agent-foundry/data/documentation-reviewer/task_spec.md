# Task Spec — general / documentation-reviewer (n603)

## Task
Validate one bug report against this repository's documentation and decide whether the bug
is valid. Emit a single six-key JSON verdict object.

## Input (dynamic)
A bug report in the canonical template (Title; Environment; Steps to Reproduce; Expected
Result; Actual Result; Severity; Priority; Evidence; Notes/Workaround — the Notes line
carries the agent name and whether the bug occurred with one framework or all). Accepted as
pasted text, a file path (.md/.json/.txt), or a ticket ID to fetch. The harness parses the
report into: title, steps, claimed Expected Result, observed Actual Result, notes.

## What to search
Every file in the `cli/` folder (all CLI command docs) AND every file in the `reference/`
folder (all reference docs), in full. Nothing outside those two folders. The harness loads
the entire corpus (every line of every file, each file tagged with its modified timestamp)
and hands it to the agent as read-only data — the agent does no file I/O itself.

## Procedure
1. Identify the single specific behavior under dispute (the behavior whose Actual Result the
   report contests). Never substitute the report's claimed Expected Result for the docs.
2. Search both folders in full for the documenting line(s); up to 3 full passes before
   concluding undocumented.
3. Collect ALL matching lines. On conflict, the line from the most-recently-modified file is
   the source of truth; still list every other match.
4. Compare the documented expected behavior to the observed behavior.

## Verdict rules (exactly one)
- `yes`          → docs state an expected behavior AND observed differs → bug is valid.
- `no`           → docs state an expected behavior AND observed matches → bug is not valid.
- `missing-docs` → after 3 passes no line documents the behavior → cannot determine.

## Output (JSON only)
`{ verdict, source_of_truth: {file,line,text}|null, other_matches: [...], documented_expected,
observed, reason }`

## Judge metric
`verdict_accuracy_pct` — % of labeled reports whose emitted verdict matches the gold verdict.
Discriminator: `source_of_truth_match_pct` (correct verdict AND correct source-of-truth
file), then tokens, then elapsed. Gold lives in `data/documentation-reviewer/gold.json` —
SWAP that file to plug in the interview's real labeled examples; harness, scorer, and golden
suite read it verbatim.

## Constraints
- The agent emits JSON only; no file/network/subprocess I/O (the harness loads the corpus).
- Deterministic, sandboxed to `FORGE_WORKSPACE`.
- schema_mode = light (presence/shape + enum-constrained verdict), matching the other agents.
