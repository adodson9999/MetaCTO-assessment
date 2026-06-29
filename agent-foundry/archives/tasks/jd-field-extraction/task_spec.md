# Task Spec — JD Field Extraction

> Captured in Phase 2 of forge-agents. This is the single task all four agents
> (LangGraph, CrewAI, Claude Code subagent, Claude Agent SDK) implement, and the
> basis for the judge's numeric metric.

## The task

Given the raw text of **one job description**, extract a structured **ATS Job Record**
(15 fields) as JSON. One JD in → one JSON object out.

## Inputs

- **Form:** plain-text job description (verbatim posting body).
- **Location:** `data/jds/<slug>.txt` — 5 real, diverse JDs pulled from the operator's
  job tooling (`tools/job-scrapper/outputs/enriched/2026-06-14/*_job_description.pdf`,
  converted via `pdftotext`).
- **Set (the eval corpus):**
  | slug | role | seniority | remote | salary (annualized USD) | yrs | visa |
  |---|---|---|---|---|---|---|
  | `10a_labs_ai_red_teamer` | AI Red Teamer, Cyber | mid | remote | 100k–120k | 2 | unspecified |
  | `affirm_qa_specialist_ii` | QA Specialist II | mid | unspecified | 80k–110k | 5 | unspecified |
  | `clickhouse_qa_engineer_core_db` | QA Engineer, Core DB | senior | remote | 141k–230k | — | unspecified |
  | `calendly_senior_sre` | Senior SRE | senior | unspecified | 198k–288k | — | not_offered |
  | `blackthorn_sr_qa_engineer` | Sr. QA Engineer | senior | remote | 69k–84k | 5 | unspecified |
- The agent receives ONLY the JD text. It must not read the gold file or the enriched analysis.

## Output — what "correct/good" looks like

- **Schema:** `data/schema.json` (JSON Schema, draft-07). 15 required fields, `additionalProperties: false`.
- **Ground truth:** hand-labeled gold records in `data/gold/<slug>.json` (one per JD).
- **Good output** = JSON that parses, conforms to the schema, and matches the gold record
  field-for-field. A perfect extraction equals the gold record exactly under the
  comparison rules below.

### The 15 fields
`title`, `company`, `location`, `remote_or_onsite`, `employment_type`, `seniority`,
`salary_min`, `salary_max`, `salary_currency`, `years_experience_min`, `tech_stack[]`,
`must_haves[]`, `nice_to_haves[]`, `visa_sponsorship`, `apply_url`.

### Gold labeling rules (also the rules a correct agent should follow)
1. **Label only from the JD text.** If a field is not stated: scalars → `null`,
   lists → `[]`, enums → `"unspecified"` (or `"not_offered"` for visa when explicitly denied).
2. **Salary → annualized USD.** Monthly × 12. Across multiple geo/tier bands, take the
   overall **min of all lower bounds** and **max of all upper bounds**.
3. **`apply_url` is `null`** for this corpus — no URL appears in any JD body. Emitting a
   URL here is a hallucination and scores as wrong. (Deliberate hallucination probe.)
4. **`employment_type` defaults to `full-time`** when an annual salary + benefits/equity
   indicate a permanent salaried role; otherwise label what's stated.
5. **`seniority`** from title + stated years (e.g. "2–5 yrs" → mid; "Senior"/"Sr." → senior).
6. **`tech_stack`** = concrete named tools/langs/frameworks/platforms only (not soft skills).

## Metric basis (for the judge, Phase 4)

Hard, gold-anchored field-extraction accuracy. The judge formalizes ONE numeric metric;
the intended definition:

- **Per-field score in [0,1]:**
  - Scalars/enums (`title`, `company`, `location`, `remote_or_onsite`, `employment_type`,
    `seniority`, `salary_currency`, `visa_sponsorship`): exact match after case/whitespace
    normalization → 1, else 0. (`null` vs `null` = 1.)
  - Numerics (`salary_min`, `salary_max`, `years_experience_min`): match within **±5%**
    tolerance → 1; `null` vs `null` = 1; one-sided null → 0.
  - Lists (`tech_stack`, `must_haves`, `nice_to_haves`): **set F1** on normalized items
    (token-overlap / fuzzy match for must/nice phrasing; exact-ish for tech).
- **Record score** = mean of the 15 field scores.
- **Metric** = mean record score across the 5 JDs, as a **percentage (0–100)**, higher is better.
- Invalid JSON / schema violation for a record → that record scores **0** (correctness floor).

## Constraints

- **Backend:** local Ollama `qwen2.5:14b-instruct` (OpenAI-compatible at `127.0.0.1:11434/v1`),
  via the central `config.toml [backend]`. Air-gapped; no cloud calls.
- **Sandbox:** all reads/writes confined to the `agent-foundry/` workspace.
- **Emission (skill invariant #4):** each agent writes its result as machine-readable JSON to
  `results/runs/<agent>.<timestamp>.json` — the extracted records plus the per-run metric the
  judge will read. If you can't see how an agent emits its number, the build is wrong.
- **Determinism:** temperature low/0 for reproducible scoring across runs.
- **Same task, four frameworks.** No agent gets a different schema, corpus, or rules.

## Open items deferred to later phases
- Judge formalizes + implements the metric (Phase 4) using `scripts/judge_score.py`.
- Optional: pull `nomic-embed-text` if the hybrid-search meaning leg is exercised during the build.
