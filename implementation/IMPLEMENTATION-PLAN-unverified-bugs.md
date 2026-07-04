# Implementation Plan — Unverified Bug Reporting (missing-docs → categorized bug)

**Status:** Draft for review (expanded edition — adds a second layer of guardrails, golden cases, and unit tests)
**Owner:** Alex
**Scope:** `orchestrator-full.md`, `general-bug-reporter`, `general-documentation-reviewer` (no contract change), shared substrate (`agents/common/bugreport_spec.py`, `agents/common/bugreport.py`), live-pipeline scripts (`scripts/adjudicate.py`, `scripts/report_doc_bugs.py`, `scripts/report_bugs.py`).

> This is the authoritative, expanded copy of the plan. Guardrails now run **HF13–HF26** (plus 3 structural guards), golden cases span **11 case sets** (plus the gate golden), and there are **18 unit-test modules**, tied together by the traceability matrix in §7.7.

---

## 1. Goal

Today, when the documentation-reviewer returns **`missing-docs`** for a mismatch, the pipeline records the outcome, sets `exclude_from_cicd: true`, and **files no bug** — the finding is silently dropped. This plan changes that: a `missing-docs` mismatch is **still reported as a bug**, just **without a documentation citation** — an **"unverified bug"** — classified into one of three categories and written to a new per-run, per-agent folder tree.

The documented-bug path (verdict `yes`, cited against a `source_of_truth`) is unchanged. The `no` path (observed matches docs = expected behavior) is unchanged.

## 2. Locked decisions (from requirements interview)

| # | Decision | Choice |
|---|----------|--------|
| 1 | Trigger for unverified path | **Only `missing-docs`.** `yes` = documented bug (unchanged); `no` = expected behavior (unchanged). |
| 2 | Who classifies | **bug-reporter** (deterministic rules in its shared spec module). Orchestrator prose must state missing-docs is now reported. |
| 3 | Vulnerability definition | A user can **access something they should not**, or **bypass a workflow step** the software requires (e.g., login without a password). |
| 4 | Business vs software split | **User-visible → business-workflow; else → computer-software** (computer-software is the default bucket). |
| 5 | Folder path | `agent-foundry/results/{date_of_run}/{time_run_started}/BugReport/{agent_name}/unverified_bugs/{category}/[BUG_ID].json` |
| 6 | IDs + index | **Per-category prefix** (`VULN-`/`BIZ-`/`SW-`) + a **separate** `unverified-index.json`. Documented bugs keep `BUG-` + their own index. |
| 7 | Artifacts | **Full 10-artifact live-capture for every unverified bug** (same as documented bugs). |
| 8 | CI + exit code | **Report-only.** Unverified bugs never enter CI and never change the exit code. `missing-docs` stays `exclude_from_cicd: true`. |
| 9 | Ordering + severity | **Category-primary** ordering: vulnerability > business-workflow > computer-software; tie-break by existing R1–R9 severity/priority then agent. Each report still carries `severity` + `priority`. |
| 10 | Verified bug location | **Documented bugs mirror the new tree** under `.../BugReport/{agent_name}/verified_bugs/[BUG_ID].json`. RUN_ID state/ledger/staging structure stays as-is. |

Cross-cutting requirement: **every unverified bug must record which agent found it** — satisfied by `{agent_name}` in the path **and** `finding_agent` + `finding_endpoint` fields (hard-enforced by HF21).

---

## 3. Current architecture (grounded in the code)

Flow for one mismatch (`api_correct == false`), realized deterministically in `scripts/adjudicate.py::run()`:

1. **Capability filter** → `ENV-LIMITED` (no bug) if the target lacks the probed capability.
2. **Doc adjudication** — `adjudicate_one(m, corpus)` greps the merged cli/+reference corpus (newest-mtime wins) and returns a verdict:
   - `yes` → `write_bug(...)` writes `results/bug-reports/BUG-<run_id>-<idx>.json`; row `outcome: "BUG"`.
   - `no` → `outcome: "EXPECTED-CORRECTED"`, no bug.
   - **`missing-docs` → `outcome: "missing-docs"`, `exclude_from_cicd: True`, `bug_id: None`** ← **the drop point this plan changes.**
3. **`reconcile()`** enforces HF2/HF3/HF5/HF12 and writes `adjudication-ledger.json` + `results/bug-reports/index.json`.

Key files and responsibilities:

| File | Role | Relevant symbols |
|------|------|------------------|
| `scripts/adjudicate.py` | Deterministic §3 loop (all agents) | `run()`, `adjudicate_one()`, `write_bug()`, `severity()`, `reconcile()`, `_next_bug_index()` |
| `scripts/report_doc_bugs.py` | LLM-reviewer doc-gated bugs | `run()`, `review_one()`, `dedupe()` — writes `results/bug-reports/BUG-*.json` |
| `scripts/report_bugs.py` | Runs the **bug-reporter agent** on a live fixture | builds fixture → `FORGE_BUGREPORT_SPEC` → `agents/general/bug-reporter/subagent/run.py` |
| `agents/common/bugreport_spec.py` | **Pure** decision + scoring (no I/O) | `build_severity()` (R1–R9), `build_reference_decision()`, `score_decision()`, `DECISION_FIELDS`, `SEVERITY_TO_PRIORITY` |
| `agents/common/bugreport.py` | Deterministic materializer/driver | `run_bugreport_test()`, `assemble_report()`, `_write_screenshot/_write_recording/_write_logs`, index writer, `has_critical_or_high()` |
| `agents/general/bug-reporter/subagent/general-bug-reporter.md` | Analytical agent spec (emits 5-key decision) | severity R1–R9 prose |
| `agents/general/documentation-reviewer/subagent/general-documentation-reviewer.md` | Sole doc adjudicator (6-key verdict) | `verdict ∈ {yes,no,missing-docs}` |
| `orchestrator-full.md` | Orchestration prose + guardrails | §3 step 4c, §3.4d, §4 HF*, §8 reconcile |

Existing scaffolding to mirror (do not reinvent):

- Guardrail validator pattern: `.../documentation-reviewer/subagent/code-review-perspectives/guardrails/validate_output.py` (stdlib-only, frozen `Result`, exit 0/1).
- Golden pattern: `.../code-review-perspectives/tests/golden.json` (`schema_cases` run with **no model** and must always pass — the deterministic forcing function — plus model-dependent `band_cases`).
- Gate pattern: `.../code-review-perspectives/forge-gate/code_review_gate.py` (pure-Python core `evaluate()` → `GateResult`, receipt, exit 0/1/2, unit-tested).

---

## 4. Target behavior

Replace the drop with a categorize-and-report step, keeping everything else identical:

```
missing-docs mismatch  →  build_category(signals)  →  full artifact capture  →
    write results/{date}/{time}/BugReport/{agent}/unverified_bugs/{category}/{PREFIX}-{run}-{seq}.json
    append to unverified-index.json (category-first ordering; vulnerability first)
    ledger row keeps outcome="missing-docs", exclude_from_cicd=true, and gains unverified_bug_id + category
    NO CI membership, NO exit-code change  (report-only)
```

### 4.1 Deterministic classification rules (first-match-wins)

Lives in `bugreport_spec.build_category(signals)`. `signals` is normalized from whatever context is available (adjudicate mismatch `m`, or a bug-reporter failure): `{expected, observed, spec_path, agent, scenario_text, stderr}`.

**Rule V — VULNERABILITY** (checked first) if **any**:
- **Access/bypass proxy:** `expected` denotes a deny — contains any of `VULN_DENY_TOKENS = {"401","403","405","407","denied","unauthorized","forbidden","requires auth","must be authenticated"}` — **AND** `observed` denotes success/access — matches `^2\d\d`, or ∈ `{"true","200","201","204"}`, or contains any of `{"returned","granted","data"}`. (Same deny→2xx signal `adjudicate.severity()` already uses for CRITICAL; reuse verbatim.)
- **Spec proxy:** `spec_path` or `agent` contains `"authentication"` or `"authorization"`.
- **Bypass indicator:** `stderr`/`observed`/`scenario_text` contains any of `VULN_BYPASS_SUBSTRINGS = {"data exposed","allowlist bypass","SQL injection","without password","without token","without credential","no auth","bypass"}`.

**Rule B — BUSINESS-WORKFLOW** (else) if **user-visible**: **no** `SYSTEM_SIGNAL_SUBSTRINGS` present **AND** a user-facing signal exists — an HTTP status token in the 2xx/4xx range in `expected`/`observed`, or `scenario_text`/`observed` contains any `USER_VISIBLE_TOKENS = {"data","field","value","product","user","page","pagination","sort","filter","search","result","returned","list","count","order","price","name"}`.

**Rule S — COMPUTER-SOFTWARE** (default / else): everything not caught by V or B — a system/internal signal (`SYSTEM_SIGNAL_SUBSTRINGS = {"500","503","database","connection refused","schema validation","CRUD","traceback","exception","timeout","timed out","OOM","memory","stack trace"}`) or no positively user-visible signal. Per decision #4, computer-software is the catch-all.

Constants live at module top (tunable); golden `category_cases` + `precedence_matrix_cases` pin representative inputs so tuning cannot silently regress. `build_category` returns exactly one of `"vulnerability" | "business-workflow" | "computer-software"`. Severity/priority are still computed by `build_severity()` (R1–R9); category never overrides severity — it only drives ordering (decision #9).

### 4.2 IDs, folders, indexes

- **Prefix map:** `CATEGORY_TO_PREFIX = {"vulnerability":"VULN","business-workflow":"BIZ","computer-software":"SW"}`. IDs: `{PREFIX}-{run_id}-{seq:04d}` with a **per-category** sequence counter. Verified IDs unchanged `BUG-{run_id}-{seq:04d}`.
- **Run tree root:** `results/{date_of_run}/{time_run_started}/BugReport/`, with `date=YYYY-MM-DD` / `time=HH-MM-SS` derived from `RUN_ID` (`RUN-YYYYMMDD-HHMMSS`), overridable by `FORGE_BUG_DATE` / `FORGE_BUG_TIME` for deterministic tests (`FORGE_BUG_DATE` already exists in `bugreport.py`).
- **Paths:** unverified `.../BugReport/{agent}/unverified_bugs/{category}/{PREFIX}-{run}-{seq}.json`; verified `.../BugReport/{agent}/verified_bugs/BUG-{run}-{seq}.json`; indexes `.../BugReport/{unverified-index.json, verified-index.json}`.
- **Ordering:** sort key `(CATEGORY_ORDER[category], SEV_RANK[severity], finding_agent, bug_id)` with `CATEGORY_ORDER = {"vulnerability":0,"business-workflow":1,"computer-software":2}`, `SEV_RANK = {"CRITICAL":0,"HIGH":1,"MEDIUM":2,"LOW":3}`.

### 4.3 Unverified report JSON (superset of the current report + `assemble_report`)

```json
{
  "bug_id": "VULN-<run>-0001", "category": "vulnerability",
  "category_reason": "expected deny (401) but observed 200 with data",
  "reviewer_verdict": "missing-docs", "documentation_cited": false, "source_of_truth": null,
  "run_id": "<run>", "created_at": "<iso>",
  "finding_agent": "<agent>", "finding_endpoint": "<endpoint>", "sub_test": "<scenario>",
  "title": "[<agent>] <scenario> on <endpoint> — expected <expected>, observed <observed> (undocumented)",
  "severity": "CRITICAL|HIGH|MEDIUM|LOW", "priority": "P1|P2|P3|P4",
  "expected": "<expected>", "observed": "<observed>",
  "artifacts": { "testing_steps": [...], "postman_references": [...],
                 "screenshot_path": "...", "recording_path": "...", "log_path": "...", "db_dump_path": null },
  "artifact_completeness": { "...10 keys..." }, "complete_artifact_count": N
}
```

Verified reports gain `documentation_cited: true`, keep `source_of_truth`, and carry **no** `category` key (preserves the scored 5-key contract — see §7.5 regression guard).

---

## 5. File-by-file changes

### 5.1 `agents/common/bugreport_spec.py` (pure; no I/O) — classifier home (decision #2)
Add without touching existing functions: constants (`VULN_DENY_TOKENS`, `VULN_SUCCESS_TOKENS`, `VULN_BYPASS_SUBSTRINGS`, `SYSTEM_SIGNAL_SUBSTRINGS`, `USER_VISIBLE_TOKENS`, `CATEGORY_ORDER`, `CATEGORY_TO_PREFIX`, `UNVERIFIED_CATEGORIES`); `normalize_signals(...)`; `build_category(signals) -> str` (Rules V→B→S); `category_reason(signals, category) -> str`; extend `build_reference_decision(..., verdict=None)` to add `category` on `missing-docs` (default `None` ⇒ today's 5-key output unchanged); extend `score_decision` to score `category` only when present in gold; add `DECISION_FIELDS_UNVERIFIED = DECISION_FIELDS + ["category"]` (leave `DECISION_FIELDS`).

### 5.2 `agents/common/bugreport.py` (materializer)
Path helpers `run_bug_tree/verified_dir/unverified_dir`; `mint_id(kind, run_id, category, counters)`; route by `failure["reviewer_verdict"]` (`missing-docs` → unverified branch with full artifacts via existing `_write_*`; else verified branch); report additions per §4.3; `write_unverified_index`/`write_verified_index` (§4.2 ordering); report-only assertion that unverified never feeds `has_critical_or_high()`/`would_exit_code_1`.

### 5.3 `scripts/adjudicate.py` — primary routing change
`import bugreport_spec`; in `run()` rewrite the `missing-docs` branch to build signals from `m`, `category = build_category(signals)`, call new `write_unverified_bug(...)` (full artifacts), set row `{outcome:"missing-docs", exclude_from_cicd:True, unverified_bug_id, category, reviewer_verdict:"missing-docs"}`; migrate `write_bug()` to `verified_bugs/` via a shared `bug_paths(run_id)` helper; write `unverified-index.json`; extend `reconcile()` with HF13–HF26; `main()` exit code unchanged.

### 5.4 `scripts/report_doc_bugs.py`
Route `missing-docs` through the same unverified writer; verified writes → `verified_bugs/`; append to `unverified-index.json`.

### 5.5 `scripts/report_bugs.py` (+ emitted spec)
Update `bug_reports_out`/`index_out` to the new tree; update the post-run glob; confirm any `missing-docs`-carrying failure routes through the unverified writer.

### 5.6 `agents/general/bug-reporter/subagent/general-bug-reporter.md`
Add a conditional 6th key `category`, emitted **only** when input carries `reviewer_verdict:"missing-docs"`, using Rule V→B→S wording; keep the 5-key contract otherwise; reaffirm the agent writes no files / mints no IDs.

### 5.7 `agents/general/documentation-reviewer/...` — **no contract change**
6-key output and scored baseline untouched (it already emits `missing-docs`). Routing lives in the orchestrator + `adjudicate.py`. (This is itself guardrail G-DOC in §6.)

### 5.8 `orchestrator-full.md`
§1/§2 note missing-docs → report-only categorized unverified bug; §3 step 4c rewrite; §3.4d generalized to fire for missing-docs (full capture); §3 defines two report classes; §4 adds HF13–HF26; §5 Phase 0 creates the new tree + defines date/time; §6 bug-reporter invoked on `yes` **and** `missing-docs`; §8 adds unverified reconciliation; ledger row gains `unverified_bug_id` + `category`.

---

## 6. Guardrails (hard-fail)

Added to `orchestrator-full.md` §4 and enforced in `adjudicate.reconcile()` + the forge gate (§7.2).

### 6.1 Layer 1 — routing & policy (from the base plan)
- **HF13 — Undocumented ≠ dropped.** Every `missing-docs` row carries a non-null `unverified_bug_id` and `category ∈ UNVERIFIED_CATEGORIES`, with a report file at the category path. (Mirrors HF5.)
- **HF14 — Category is deterministic.** `row.category == build_category(normalize_signals(**row_signals))`. Divergence → BROKEN.
- **HF15 — Report-only.** No missing-docs/unverified row has `exclude_from_cicd == false`; unverified never in the CI add-set; unverified never feeds `would_exit_code_1`. (Enforces decision #8.)
- **HF16 — ID/index separation.** Unverified reports carry `VULN-/BIZ-/SW-` and appear only in `unverified-index.json`; `BUG-` only in the verified index.
- **HF17 — Vulnerability visibility.** Every `vulnerability` bug is present and sorted first in `unverified-index.json`. (Enforces decision #9.)

### 6.2 Layer 2 — integrity, provenance & reproducibility (NEW)
- **HF18 — Bidirectional denominator.** `count(unverified report files) == count(missing-docs rows with unverified_bug_id)`, and every index entry maps 1:1 to a file and a row. **No orphan file** (file without a row) and **no dangling row** (row id without a file). Either direction failing → BROKEN. (Strengthens HF13 both ways.)
- **HF19 — ID uniqueness.** No two reports in a run share a `bug_id`; per-category sequences are unique and non-colliding across agents/categories. A duplicate ID → BROKEN.
- **HF20 — Path↔category↔prefix agreement.** For every unverified report, the on-disk `{category}` path segment, the report's `category` field, and the ID's category (via `CATEGORY_TO_PREFIX`) are identical. A misfiled report (e.g., a `SW-` file under `.../vulnerability/`) → BROKEN.
- **HF21 — Finding-agent integrity.** `report.finding_agent` is non-empty and equals the `{agent_name}` path segment **and** the ledger row's `agent`; `finding_endpoint` is present. (Hard-enforces the "label which agent found the bug" requirement.)
- **HF22 — Full-capture parity (decision #7).** Every unverified report meets the same artifact bar as verified: `screenshot`, `recording`, and `logs` present; `db_dump` present iff `db_available`; `complete_artifact_count` ≥ the verified threshold for the same `db_available`. A vulnerability bug missing its recording/screenshot → BROKEN.
- **HF23 — Citation isolation.** Unverified ⇒ `documentation_cited == false` **and** `source_of_truth == null`. Verified ⇒ `documentation_cited == true` **and** `source_of_truth != null`. Any leakage (an unverified bug carrying a citation, or a verified bug missing one) → BROKEN.
- **HF24 — Verdict↔branch agreement.** Only `reviewer_verdict == "missing-docs"` rows may produce `VULN-/BIZ-/SW-` reports; only `yes` rows may produce `BUG-` reports. A `yes` row in the unverified tree (or a missing-docs row in the verified tree) → BROKEN.
- **HF25 — Index integrity & total sort.** Each report file appears exactly once in the correct index; `by_category` counts equal actual per-category file counts; the `bugs` array equals the input sorted by the §4.2 key under a **total** order (ties fully broken by `bug_id`), so ordering is reproducible. Any count mismatch or unstable order → BROKEN.
- **HF26 — Determinism / idempotency.** Re-running the materializer over the same ledger with the same `FORGE_BUG_DATE`/`FORGE_BUG_TIME`/`run_id` produces **byte-identical** report files and indexes. Nondeterminism (e.g., wall-clock leaking into unverified output) → BROKEN.

### 6.3 Non-HF structural guardrails
- **G-VALIDATE — Output shape.** The agent's unverified decision must pass `validate_unverified_decision.py` (§7.1); an invalid shape scores the decision invalid (mirrors the code-review schema gate).
- **G-DOC — Reviewer untouched.** CI check that `general-documentation-reviewer.md` diff is empty for this feature and its judged golden baseline is unchanged (§7.5). Protects the hardened reviewer.
- **G-PATHS — Single path source.** All bug paths come from one `bug_paths(run_id)` helper (no hard-coded `results/bug-reports/` literals in the routing scripts), so layout can't drift between writers and readers.

---

## 7. Golden test cases & unit tests (deliverables)

### 7.1 Output guardrail validator — NEW
`agents/general/bug-reporter/guardrails/validate_unverified_decision.py` (mirror `validate_output.py`): stdlib-only, frozen `Result`, exit 0/1. Validates exactly `{title, severity, priority, category, testing_steps, postman_references}`; `severity ∈ {CRITICAL,HIGH,MEDIUM,LOW}`; `priority` consistent with `severity` via `SEVERITY_TO_PRIORITY`; `category ∈ UNVERIFIED_CATEGORIES`; `testing_steps` null|non-empty list; `postman_references` list. Structure only.

### 7.2 Forge gate — NEW
`agents/general/bug-reporter/forge-gate/unverified_bug_gate.py` (mirror `code_review_gate.py`): pure-Python `evaluate(rows, reports_root, unverified_index, verified_index, db_available) -> GateResult` checking **HF13–HF26** deterministically; writes a receipt under `results/_global/`; exit `0`/`1`/`2`. Ships with `forge-gate/test_unverified_bug_gate.py` and `forge-gate/unverified-bug-gate.golden.json`.

### 7.3 Golden fixture — NEW
`data/bug-reporter/unverified_golden.json` (mirror `golden.json`): `baseline`, `tolerance`, and the case sets below — **all runnable with no model** (pure-Python forcing function that must always pass).

**Layer 1 sets (base plan):**
- **`category_cases`** — `{id, signals, expect_category}`: `vuln-deny-2xx`, `vuln-spec-auth`, `vuln-no-password`, `vuln-precedence`, `biz-wrong-data`, `biz-wrong-4xx`, `sw-500`, `sw-db`, `sw-default`.
- **`layout_cases`** — `{id, run_id, agent, category, expect_path, expect_prefix}` pinning the §4.2 folder path + ID prefix.
- **`index_cases`** — cross-category set with `expect_order` (vuln→biz→sw) and `expect_separation` (no `BUG-`).

**Layer 2 sets (NEW):**
- **`precedence_matrix_cases`** — exhaustive pairwise conflicts: `V+B→V`, `V+S→V`, `B+S(system present)→S`, `B+S(user-visible only)→B`, `all-three→V`. Pins the exact tie-break so a rule reorder is caught.
- **`negative_signal_cases`** — malformed/edge inputs that must resolve without error: empty strings, missing keys, `None` values, non-ASCII/unicode tokens, 10 KB blobs, mixed case, numeric-only. Each `expect_category` defined (default `computer-software`); each must not raise.
- **`severity_retention_cases`** — a `missing-docs` case that is also security-critical: assert `category == vulnerability` **and** `build_severity(...) == CRITICAL` are both emitted (decision #9 severity-as-detail).
- **`ordering_stress_cases`** — many bugs per category with varied severity + agent; `expect_order` fully specified so the agent tie-break (`finding_agent`, then `bug_id`) is proven, not just the category tier.
- **`report_only_cases`** — a run whose bugs are unverified **including a vulnerability (P1)**: assert `would_exit_code_1 == false` and the CI add-set is empty (decision #8; forcing function for HF15).
- **`separation_cases`** — a mixed run (verified + unverified): verified-index has only `BUG-`, unverified-index has only `VULN-/BIZ-/SW-`, zero overlap (HF16/HF25).
- **`idempotency_cases`** — the same ledger materialized twice with fixed date/time env: assert identical file bytes + identical index bytes (HF26).
- **`finding_agent_cases`** — assert `finding_agent`/`finding_endpoint` present and equal to the path segment + row agent (HF21).

### 7.4 Unit tests — NEW (pytest, `agent-foundry/tests/unit/`, `@pytest.mark.unit`)

**Layer 1 (base plan):**
1. `test_bugreport_category.py` — table over `build_category` for every `category_cases`; explicit V>B>S precedence and empty-signal default.
2. `test_unverified_materialize.py` — fixed date/time/run_id → exact path, prefix, full-artifact presence, verified mirror path, exit gate unaffected.
3. `test_unverified_reconcile.py` — clean run passes; each HF13–HF17 violation flagged.
4. `test_validate_unverified_decision.py` — pass/fail table for §7.1.
5. `test_unverified_index_order.py` — ordering + `by_category` + separation.
6. `test_verified_decision_unchanged.py` — regression guard (§7.5).

**Layer 2 (NEW):**
7. `test_precedence_matrix.py` — drives `precedence_matrix_cases`; asserts the full V/B/S conflict table (guards against rule reordering).
8. `test_negative_signals.py` — drives `negative_signal_cases`; asserts `build_category` is **total** (never raises, always returns a legal category) on malformed/edge input.
9. `test_unverified_denominator.py` — HF18: bidirectional file↔row↔index reconciliation; injects an orphan file and a dangling row and asserts both are caught.
10. `test_unverified_id_uniqueness.py` — HF19: no duplicate `bug_id`; per-category sequence integrity across multiple agents.
11. `test_path_category_id_agreement.py` — HF20: path segment == category field == prefix; a deliberately misfiled report is flagged.
12. `test_finding_agent_integrity.py` — HF21: `finding_agent` non-empty and equal across path/report/row; missing value is flagged.
13. `test_full_artifact_capture.py` — HF22: unverified reports carry screenshot/recording/logs; `db_dump` only when `db_available`; parity with verified threshold.
14. `test_citation_isolation.py` — HF23: unverified ⇒ `documentation_cited:false` + `source_of_truth:null`; verified ⇒ inverse; leakage flagged.
15. `test_verdict_branch_agreement.py` — HF24: only missing-docs → VULN/BIZ/SW; only yes → BUG.
16. `test_report_only_semantics.py` — HF15/decision #8: a vulnerability-present run leaves exit code 0 and CI add-set empty.
17. `test_idempotent_materialize.py` — HF26: double materialization is byte-identical (hash compare of files + indexes).
18. `test_unverified_gate_end_to_end.py` — §7.2 gate: clean run → exit 0; each injected HF13–HF26 violation → exit 1; missing reports dir / no rows → exit 2.

**Optional property test:** `test_category_total_function.py` — if `hypothesis` is available, fuzz `build_category` over arbitrary text; else a stdlib randomized loop. Asserts totality + determinism (same input → same output).

### 7.5 Regression guards (the leaderboard/reviewer must not drop)
- `test_verified_decision_unchanged.py` — `build_reference_decision(failure, registry, postman_items)` (no `verdict`) is **byte-identical** to today on existing fixtures; `score_decision` over the 5 `DECISION_FIELDS` unchanged.
- `test_docreviewer_baseline_unchanged.py` (G-DOC) — the documentation-reviewer's judged golden score equals its recorded baseline (its spec is not edited by this feature).
- Inspect/extend `agent-foundry/tests/test_run_layout.py` if it asserts the old `results/bug-reports/` layout.

### 7.6 CI wiring
Add a `pytest -m unit agent-foundry/tests/unit` step plus a `python .../unverified_bug_gate.py --dry-run` step to the pipeline's test stage. The pure-Python golden sets (§7.3) run with no backend and must be green before any model-dependent step.

### 7.7 Traceability matrix (guardrail → enforcing test → golden set)

| Guardrail | Unit test(s) | Golden set |
|-----------|--------------|------------|
| HF13 undocumented≠dropped | `test_unverified_reconcile` | `category_cases` |
| HF14 deterministic category | `test_bugreport_category`, `test_precedence_matrix` | `category_cases`, `precedence_matrix_cases` |
| decision #9 severity retained | `test_bugreport_category` (asserts category + `build_severity` both emitted) | `severity_retention_cases` |
| HF15 report-only | `test_report_only_semantics` | `report_only_cases` |
| HF16 ID/index separation | `test_unverified_index_order` | `separation_cases` |
| HF17 vuln visibility/order | `test_unverified_index_order`, `test_precedence_matrix` | `index_cases`, `ordering_stress_cases` |
| HF18 bidirectional denominator | `test_unverified_denominator` | `separation_cases` |
| HF19 ID uniqueness | `test_unverified_id_uniqueness` | `layout_cases` |
| HF20 path↔category↔prefix | `test_path_category_id_agreement` | `layout_cases` |
| HF21 finding-agent integrity | `test_finding_agent_integrity` | `finding_agent_cases` |
| HF22 full-capture parity | `test_full_artifact_capture` | `layout_cases` |
| HF23 citation isolation | `test_citation_isolation` | `separation_cases` |
| HF24 verdict↔branch | `test_verdict_branch_agreement` | `category_cases` |
| HF25 index integrity/total sort | `test_unverified_index_order` | `ordering_stress_cases` |
| HF26 determinism/idempotency | `test_idempotent_materialize` | `idempotency_cases` |
| G-VALIDATE output shape | `test_validate_unverified_decision` | — |
| G-DOC reviewer untouched | `test_docreviewer_baseline_unchanged` | — |
| all HF via the gate | `test_unverified_gate_end_to_end` | `unverified-bug-gate.golden.json` |

Every guardrail has at least one enforcing test; every Layer-2 golden set has at least one consuming test.

---

## 8. Back-compat & risks

| Risk | Detail | Mitigation |
|------|--------|------------|
| Readers of `results/bug-reports/` | `adjudicate.reconcile()` globs `BUG-*.json`; `report_doc_bugs`, `report_bugs`, `judge/general/bug-reporter/score.py` reference report/index paths. | Centralize in `bug_paths(run_id)` (G-PATHS); **dual-write** legacy `results/bug-reports/index.json` for one release; update globs + layout test; then remove. |
| Leaderboard baseline | `bugreport.py` scored vs gold. | `category` added only on `missing-docs`; `DECISION_FIELDS` untouched; `test_verified_decision_unchanged` enforces byte-identity. |
| `report_bugs.py` output dir | Currently `results/runs/<run>/general-bug-reporter.bug-reports`. | Update emitted spec `bug_reports_out`/`index_out` + post-run glob in the same change. |
| Volume | `missing-docs` common; full capture heavy (decision #7). | Accepted; artifacts are pure file writes (asciinema `.cast`, text replay, logs), no external binaries. |
| Doc-reviewer regression | Editing its contract risks its hardened baseline. | No change to the reviewer (G-DOC + `test_docreviewer_baseline_unchanged`). |

---

## 9. Phasing & sequencing
- **Phase A — Pure classifier (no I/O).** §5.1 + `category_cases`/`precedence_matrix_cases`/`negative_signal_cases` + tests 1,6,7,8 + regression guards. Zero runtime risk.
- **Phase B — Paths/IDs/indexes/materializer.** §5.2 + `layout_cases`/`index_cases`/`ordering_stress_cases`/`idempotency_cases`/`finding_agent_cases` + tests 2,5,9,10,11,12,13,17.
- **Phase C — Wire routing.** §5.3–§5.5 + `reconcile()` HF13–HF26 + tests 3,14,15,16.
- **Phase D — Guards + gate + prose.** §7.1 validator + §7.2 gate (+ test 18) + §5.6 bug-reporter prose + §5.8 orchestrator prose.
- **Phase E — Back-compat migration.** §8 reader updates, drop dual-write, full fixture-run validation + CI wiring (§7.6).

## 10. Definition of done
1. All §7 golden `*_cases` and all 18 unit modules pass; the pure-Python sets run green with **no model**.
2. A fixture run produces verified bugs under `verified_bugs/`, unverified under `unverified_bugs/{category}/`, a separate `unverified-index.json`, category-first ordering with **vulnerability first**.
3. `reconcile()` and the forge gate return pass on a clean run and BROKEN/exit-1 on any injected HF13–HF26 violation (proven by tests 3, 9–18).
4. Exit code and CI add-set unchanged by unverified bugs (report-only); `missing-docs` stays `exclude_from_cicd:true`.
5. Verified leaderboard fidelity + documentation-reviewer baselines unchanged (regression guards green).
6. Every unverified report + index entry records the finding agent (path + `finding_agent`/`finding_endpoint`), hard-enforced by HF21.
7. `build_category` is total and deterministic on arbitrary input (test 8 + optional property test).

## 11. Out of scope
Changing the documentation-reviewer's verdict logic or contract; adding unverified bugs to CI or the exit gate; root-cause analysis or DummyJSON implementation review; altering the `yes`/`no` paths; a new severity taxonomy (R1–R9 retained).
