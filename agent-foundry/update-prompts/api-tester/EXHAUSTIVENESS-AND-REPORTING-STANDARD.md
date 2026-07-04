# Exhaustiveness & Professional Reporting Standard (applies to every api-tester agent)

This clause is appended to every agent's `update-agent` change prompt. It makes each agent test its
lane as aggressively as possible — find **every** reportable bug in its lane — while staying
professional (no false positives, evidence-backed) and keeping a **complete, self-describing record of
every test case** so findings can be reported correctly. It never expands an agent beyond its declared
lane; "go maximal" always means "go maximal **in lane**."

Paste the block below verbatim at the END of an agent's change prompt (after its ADD/REMOVE lists).

---

ALSO ADOPT THE EXHAUSTIVENESS & PROFESSIONAL REPORTING STANDARD (in addition to everything above; it
never widens this agent's lane — it only makes coverage inside the lane exhaustive and the report
complete):

A. MAXIMAL IN-LANE ENUMERATION ("find every bug in this lane, and only this lane").
- Enumerate the FULL documented surface that falls in this lane: every documented resource × every
  documented method in scope, every documented field/parameter including nested paths and date/range
  bounds, and every documented capability. A documented capability that is unimplemented, 404s, or is
  silently ignored is itself a `missing_capability` deviation — emit that case, do not skip it.
- For every element, cover all applicable case shapes: positive (valid), negative (invalid), boundary
  (min/max/just-over/just-under/empty/max-length), and negative-of-omission (a documented thing that
  isn't there). Include the interaction cases that change behavior within the lane (e.g. two
  in-lane parameters that combine), using pairwise combinations where a full cross-product is
  unbounded — never leaving the lane to do so.
- Remove any artificial fixed case cap. The canonical count is "the complete enumeration computed from
  the target's documented in-lane surface," not a magic number. A case is omitted ONLY when a required
  runtime input for it is absent; when that happens, record the omission explicitly (an
  `omitted[]` entry with the case id and the missing input) and fail the count/coverage check rather
  than fabricating a surface or silently dropping it.
- Repeat every case the configured soak count and flag any result that varies across repeats as a
  `flaky`/`intermittent` deviation.
- MECE guardrail is absolute: never emit a case whose canonical identity belongs to a sibling agent.
  When an adjacent concern appears, hand it off by name in the de-dup notes; do not test it here.

B. PROFESSIONAL DISCIPLINE (credible, low-false-positive findings).
- Every expected outcome comes from the contract-oracle (`references/contract-oracle.md`), never from
  the target's own docs or observed behaviour; carry `expected_by_docs` only when the docs differ, and
  never let an `also_accept` swallow a standard code.
- Prove every effect BLACK-BOX by read-back (create→GET returns it, delete→GET 404, update→GET
  reflects it); where a black-box assertion is impossible, degrade to the nearest observable signal
  rather than skipping the assertion.
- Recipes are deterministic and drawn only from the closed vocabulary; emit no real tokens/secrets and
  perform no live network calls in the plan (the harness executes). Do not state or guess a concrete
  observed status/body/header/count.
- Rate every finding: `severity` ∈ {critical, major, minor}, with a short standards-cited `note`
  (e.g. "RFC 9110 §15.3.2: creation returns 201; observed 200"). Distinguish a product bug
  (observed ≠ expected_by_contract) from a spec bug (expected_by_docs ≠ expected_by_contract) — report
  both, never absorb either.

C. REMEMBER EVERY TEST CASE + REPORT IT CORRECTLY (the ledger — this is a hard output-contract rule).
- Every case is self-describing and carries a STABLE, unique `id` (a slug that does not change between
  runs) plus its `lane`, so a finding can be traced to its case across runs and reports.
- The emitted JSON object is a complete plan + execution + log + report contract. In addition to the
  `cases[]` plan (each with its granular `steps`/assertions and `expected_by_contract`), the run
  aggregates a `deviations[]` findings channel; each finding carries: `case` (the stable id),
  `operation`, `request` (method + role + inputs, no secrets), `expected_by_contract`,
  `expected_by_docs` (only if it differs), `observed` (filled by the harness), `verdict`,
  `deviation_kind` (status_code|persistence|ordering|filter|schema|missing_capability|leak|header|
  flaky|other), `severity`, `soak` (repeats + whether stable), a `reproduction` step list, and a
  human-readable `note`.
- Completeness invariant: EVERY planned case appears in the report with a verdict (pass or deviation);
  a deviation is ALWAYS surfaced, NEVER absorbed by a lenient oracle; nothing is silently dropped.
- Run-level summary: emit counts of total cases, passes, deviations by `severity`, `flaky` count, and
  any `omitted[]` entries with their missing inputs — enough for a reader to reproduce and triage
  every finding without re-deriving it.
- Keep the single-JSON-object output contract, the feature-agnostic role-only references, the
  fail-closed out-of-lane sentinel, and the self-awareness / code-review ≥85 clause exactly as before —
  this standard extends them, it does not replace them.
