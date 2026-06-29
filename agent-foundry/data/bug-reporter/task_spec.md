# Task Spec — Bug Reporter ("n602")

**Position:** general
**Workflow:** bug-reporter
**Agent id:** `general-bug-reporter`
**Backend:** Ollama (local / air-gapped). The Ollama server is **never started** by this
build; `scripts/phase4_bugreport_run.sh` only probes `GET /api/tags` read-only and exits
with guidance if it is down. DummyJSON is **never** touched — n602 is a pure transform
over local `results/*` JSON fixtures and makes no HTTP calls of its own.

## The task

For every non-PASSED agent in a CI/CD pipeline run, produce one structured bug report
collecting ten artifacts and write `results/bug-reports/[BUG_ID].json` plus a
consolidated `results/bug-reports/index.json`. The run exits 1 if any report is
CRITICAL or HIGH.

## The split (what the agent does vs the harness)

Mirrors the `run-cicd-pipeline` / `run-regression-suite` precedent — the agent emits the
report decision; a separate deterministic program acts on it.

- **Agent (the measured analytical core).** Given ONE failure's captured artifacts (its
  `status`, `exit_code`, `spec_path`, full stderr/stdout, its registry test cases, the
  Postman lookup, and `database_available`), emit a single five-key JSON **decision**:
  - `title` — by status (timed-out / malformed strings, or the bracketed name + first
    non-empty stderr line truncated to 120, or the exit-code fallback). *(Artifact 8)*
  - `severity` — the **nine ordered rules R1..R9, first match wins** *(Artifact 9)*.
  - `priority` — `CRITICAL→P1, HIGH→P2, MEDIUM→P3, LOW→P4` *(Artifact 10)*.
  - `testing_steps` — the agent's registry test cases sorted by `tc_id`, mapped to the
    seven step keys (or null if none). *(Artifact 1)*
  - `postman_references` — per HTTP test case: an existing-collection ref, or a
    constructed Postman v2.1 `new_item` built only from `step_text`. *(Artifact 2)*

- **Harness / CI program (deterministic, debate-gated OUT of the agent — prompt L15).**
  Reads the pipeline summary / registry / collection / config; generates `BUG_ID` +
  `created_at` *(Artifact 7)*; **materialises** the replay "screenshot" text *(Artifact
  3)*, the asciinema v2 recording *(Artifact 4)*, the concatenated logs *(Artifact 5)*,
  and — only when a `[database]` is configured, which the air-gapped fixture is not — the
  schema dump *(Artifact 6)*; assembles the final report + `artifact_completeness` +
  `complete_artifact_count`; writes the index sorted CRITICAL→HIGH→MEDIUM→LOW; and sets
  the process exit code. The agent never reads/writes files, runs
  convert/pg_dump/mysqldump/asciinema/psql/Newman, or sends HTTP.

## Fixtures (Phase-2, air-gapped)

`data/bug-reporter/fixture.json` (materialised by `build_gold.py`) holds one pipeline run
of **nine** non-PASSED agents exercising every severity rule R1..R9 exactly once
(3 CRITICAL + 3 HIGH + 2 MEDIUM + 1 LOW) plus **two** PASSED agents that must be excluded,
the test-case registry, and the Postman collection. The fixture has **no `[database]`**,
so `DB_AVAILABLE` is false and the DB-dump artifact is null for every report (a
fully-materialised report scores **9/10** → completeness ~90%). Two HTTP cases
(`tc-pipe-001`, `tc-webhook-001`) are deliberately **absent** from the collection to
exercise the `new_item` construction path.

## Metric

- **Judge ranking — Bug-Report Fidelity** = fraction of (failure × decision-field) cells
  matching the deterministic gold (9 × 5 = 45). Tie-breakers: completeness → tokens →
  elapsed. Backend-independent (measures the framework's analytical quality, not the
  fixtures).
- **Task gate metrics** (recorded as findings): Bug Report Completeness Rate ≥ 80%
  (fixture: 90% ✓), Mandatory Field Completeness 100% (✓), Testing Steps Coverage ≥ 95%
  (100% ✓), CRITICAL/HIGH Exit-Code Enforcement (3 CRITICAL + 3 HIGH → `would_exit_code_1`
  true ✓), Postman Reference Rate ≥ 90% (**72.73% by design** — the two absent HTTP cases
  surface the genuine "new items need manual review" finding).

## Run it

```bash
# deterministic (no server): build gold + fixtures
python data/bug-reporter/build_gold.py
# live ranking (requires `ollama serve` running — this script never starts it):
bash scripts/phase4_bugreport_run.sh
```
