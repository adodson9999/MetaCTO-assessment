# Implementation Plan — Unverified Bug Reporting (missing-docs → categorized bug)

**Status:** Draft for review
**Owner:** Alex
**Scope:** `orchestrator-full.md`, `general-bug-reporter`, `general-documentation-reviewer` (no contract change), shared substrate (`agents/common/bugreport_spec.py`, `agents/common/bugreport.py`), live-pipeline scripts (`scripts/adjudicate.py`, `scripts/report_doc_bugs.py`, `scripts/report_bugs.py`).

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

Cross-cutting requirement: **every unverified bug must record which agent found it** — satisfied by `{agent_name}` in the path **and** `finding_agent` + `finding_endpoint` fields in the report and index.

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
| `agents/common/bugreport.py` | Deterministic materializer/driver | `run_bugreport_test()`, `assemble_report()`, `_write_screenshot/_write_recording/_write_logs`, index writer |
| `agents/general/bug-reporter/subagent/general-bug-reporter.md` | Analytical agent spec (emits 5-key decision) | severity R1–R9 prose |
| `agents/general/documentation-reviewer/subagent/general-documentation-reviewer.md` | Sole doc adjudicator (6-key verdict) | `verdict ∈ {yes,no,missing-docs}` |
| `orchestrator-full.md` | Orchestration prose + guardrails | §3 step 4c, §3.4d, §4 HF*, §8 reconcile |

Existing scaffolding to mirror (do not reinvent):

- Guardrail validator pattern: `.../documentation-reviewer/subagent/code-review-perspectives/guardrails/validate_output.py` (stdlib-only, frozen `Result`, exit 0/1).
- Golden pattern: `.../code-review-perspectives/tests/golden.json` (`schema_cases` run with **no model** and must always pass — the deterministic forcing function — plus model-dependent `band_cases`).
- Gate pattern: `.../code-review-perspectives/forge-gate/code_review_gate.py` (pure-Python core `evaluate()` → `GateResult`, receipt, exit 0/1/2).

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
- **Access/bypass proxy:** `expected` denotes a deny — contains any of `VULN_DENY_TOKENS = {"401","403","405","407","denied","unauthorized","forbidden","requires auth","must be authenticated"}` — **AND** `observed` denotes success/access — matches `^2\d\d`, or ∈ `{"true","200","201","204"}`, or contains any of `{"returned","granted","data"}`. (This is the same deny→2xx signal `adjudicate.severity()` already uses for CRITICAL; reuse it verbatim for consistency.)
- **Spec proxy:** `spec_path` or `agent` contains `"authentication"` or `"authorization"`.
- **Bypass indicator:** `stderr`/`observed`/`scenario_text` contains any of `VULN_BYPASS_SUBSTRINGS = {"data exposed","allowlist bypass","SQL injection","without password","without token","without credential","no auth","bypass"}`.

**Rule B — BUSINESS-WORKFLOW** (else) if the mismatch is **user-visible**: **no** `SYSTEM_SIGNAL_SUBSTRINGS` present **AND** a user-facing signal exists — an HTTP status token in the 2xx/4xx range in `expected`/`observed`, or `scenario_text`/`observed` contains any `USER_VISIBLE_TOKENS = {"data","field","value","product","user","page","pagination","sort","filter","search","result","returned","list","count","order","price","name"}`.

**Rule S — COMPUTER-SOFTWARE** (default / else): everything not caught by V or B — i.e., a system/internal signal (`SYSTEM_SIGNAL_SUBSTRINGS = {"500","503","database","connection refused","schema validation","CRUD","traceback","exception","timeout","timed out","OOM","memory","stack trace"}`) **or** no positively user-visible signal. Per decision #4, computer-software is the catch-all.

Constants live at module top so they are tunable; golden `category_cases` pin representative inputs so tuning cannot silently regress. `build_category` returns exactly one of `"vulnerability" | "business-workflow" | "computer-software"`.

Severity/priority are still computed by the existing `build_severity()` (R1–R9) and `SEVERITY_TO_PRIORITY` and stored on the report (decision #9). Category never overrides severity — it only drives ordering.

### 4.2 IDs, folders, indexes

- **Prefix map:** `CATEGORY_TO_PREFIX = {"vulnerability":"VULN","business-workflow":"BIZ","computer-software":"SW"}`. IDs: `{PREFIX}-{run_id}-{seq:04d}` with a **per-category** sequence counter.
- **Verified IDs:** unchanged `BUG-{run_id}-{seq:04d}`.
- **Run tree root:** `results/{date_of_run}/{time_run_started}/BugReport/`. `date_of_run` and `time_run_started` are derived from `RUN_ID` (`RUN-YYYYMMDD-HHMMSS` → `date=YYYY-MM-DD`, `time=HH-MM-SS`); overridable by `FORGE_BUG_DATE` / `FORGE_BUG_TIME` for deterministic tests.
- **Paths:**
  - Unverified: `.../BugReport/{agent}/unverified_bugs/{category}/{PREFIX}-{run}-{seq}.json`
  - Verified (mirrors, decision #10): `.../BugReport/{agent}/verified_bugs/BUG-{run}-{seq}.json`
  - Indexes (run-level, at BugReport root): `.../BugReport/unverified-index.json` and `.../BugReport/verified-index.json`
- **`unverified-index.json` shape:**
  ```json
  {
    "run_id": "...", "generated_at": "...",
    "unverified_bug_count": N,
    "by_category": {"vulnerability": a, "business-workflow": b, "computer-software": c},
    "bugs": [ /* sorted category-first (vuln>biz>sw), then severity rank, then finding_agent, then bug_id */
      {"bug_id","category","finding_agent","finding_endpoint","severity","priority",
       "created_at","complete_artifact_count","report_path"}
    ]
  }
  ```
- **Ordering (decision #9):** sort key = `(CATEGORY_ORDER[category], SEV_RANK[severity], finding_agent, bug_id)` where `CATEGORY_ORDER = {"vulnerability":0,"business-workflow":1,"computer-software":2}` and `SEV_RANK = {"CRITICAL":0,"HIGH":1,"MEDIUM":2,"LOW":3}`.

### 4.3 Unverified report JSON (superset of the current report + `assemble_report`)

```json
{
  "bug_id": "VULN-<run>-0001",
  "category": "vulnerability",
  "category_reason": "expected deny (401) but observed 200 with data",
  "reviewer_verdict": "missing-docs",
  "documentation_cited": false,
  "source_of_truth": null,
  "run_id": "<run>",
  "created_at": "<iso>",
  "finding_agent": "<agent>",
  "finding_endpoint": "<endpoint>",
  "sub_test": "<scenario>",
  "title": "[<agent>] <scenario> on <endpoint> — expected <expected>, observed <observed> (undocumented)",
  "severity": "CRITICAL|HIGH|MEDIUM|LOW",
  "priority": "P1|P2|P3|P4",
  "expected": "<expected>",
  "observed": "<observed>",
  "artifacts": { "testing_steps": [...], "postman_references": [...],
                 "screenshot_path": "...", "recording_path": "...",
                 "log_path": "...", "db_dump_path": null },
  "artifact_completeness": { ...10 keys... },
  "complete_artifact_count": N
}
```

Verified reports gain `documentation_cited: true` and keep `source_of_truth`; no `category` key (keeps the scored 5-key contract intact — see §8 regression guard).

---

## 5. File-by-file changes

### 5.1 `agents/common/bugreport_spec.py` (pure; no I/O) — the classifier home (decision #2)

Add, without touching existing functions:

- Constants: `VULN_DENY_TOKENS`, `VULN_SUCCESS_TOKENS`, `VULN_BYPASS_SUBSTRINGS`, `SYSTEM_SIGNAL_SUBSTRINGS`, `USER_VISIBLE_TOKENS`, `CATEGORY_ORDER`, `CATEGORY_TO_PREFIX`, `UNVERIFIED_CATEGORIES = ("vulnerability","business-workflow","computer-software")`.
- `normalize_signals(*, expected="", observed="", spec_path="", agent="", scenario_text="", stderr="") -> dict`.
- `build_category(signals: dict) -> str` implementing Rules V→B→S (first-match).
- `category_reason(signals, category) -> str` (short deterministic justification for the report).
- Extend `build_reference_decision(failure, registry, postman_items, verdict=None)`: when `verdict == "missing-docs"`, add `"category"` (and keep the 5 existing keys). Default `verdict=None` preserves today's 5-key output exactly.
- Extend `score_decision(agent_decision, gold_decision)`: score `"category"` **only when** `gold_decision` contains it (so verified scoring is byte-for-byte unchanged).
- `DECISION_FIELDS_UNVERIFIED = DECISION_FIELDS + ["category"]` (leave `DECISION_FIELDS` untouched).

### 5.2 `agents/common/bugreport.py` (materializer)

- New path helpers: `run_bug_tree(run_id) -> Path` (`results/{date}/{time}/BugReport`), `verified_dir(run_id, agent)`, `unverified_dir(run_id, agent, category)`.
- New `mint_id(kind, run_id, category, counters) -> str` using `CATEGORY_TO_PREFIX` (unverified) or `BUG` (verified) with per-(kind,category) counters.
- Route by `failure["reviewer_verdict"]`: `"missing-docs"` → unverified branch (category via `build_category`, full artifacts via the existing `_write_*` functions but into `unverified_dir`); `"yes"`/legacy → verified branch into `verified_dir`.
- Report schema additions per §4.3 (`category`, `category_reason`, `finding_agent`, `finding_endpoint`, `documentation_cited`, `reviewer_verdict`).
- `write_unverified_index(...)` and `write_verified_index(...)` with the §4.2 ordering.
- **Report-only guard (decision #8):** `has_critical_or_high()` / `would_exit_code_1` consider **verified reports only** — add an assertion that no unverified report contributes to the exit gate.

### 5.3 `scripts/adjudicate.py` — primary routing change

- `import bugreport_spec` (already on `sys.path`); use `build_category`, `CATEGORY_TO_PREFIX`.
- In `run()`, replace the `missing-docs` `else` branch: build signals from `m`, `category = build_category(signals)`, call new `write_unverified_bug(run_id, category, seq_for_category, m, v)` (full artifacts), set row `{outcome:"missing-docs", exclude_from_cicd:True, unverified_bug_id:<id>, category:<category>, reviewer_verdict:"missing-docs"}`.
- New `write_unverified_bug(...)` writing to the §4.2 unverified path (reuse `bugreport` helpers so adjudicate + agent paths stay identical).
- Write `unverified-index.json` alongside the existing verified index; **also** migrate `write_bug()` to the `verified_bugs/` tree (decision #10) via a shared `bug_paths(run_id)` helper.
- Extend `reconcile()` with **HF13–HF17** (§6).
- `main()` exit code unchanged (0 ok / 2 broken) — unverified never forces non-zero (decision #8).

### 5.4 `scripts/report_doc_bugs.py`

- Same `missing-docs` routing: in `run()`, when `verdict != "yes"` and `verdict == "missing-docs"`, categorize and write an unverified report to the new tree + append to `unverified-index.json` (reuse the adjudicate/`bugreport` writer — single implementation).
- Point verified writes at `verified_bugs/`.

### 5.5 `scripts/report_bugs.py` (+ its emitted spec)

- Update the emitted `bugreport_spec.json` `bug_reports_out`/`index_out` to the new tree; update the post-run `glob` in `run()` accordingly.
- This script keys off guardrail `FAIL/EMPTY/ERROR` (verified-side); if it ever carries a `reviewer_verdict == "missing-docs"` it routes through the same unverified writer. Confirm during implementation.

### 5.6 `agents/general/bug-reporter/subagent/general-bug-reporter.md` (agent prose)

- Add a **conditional 6th key `category`** emitted **only** when the input carries `reviewer_verdict: "missing-docs"` (unverified mode), using the Rule V→B→S first-match wording from §4.1. Keep the 5-key contract for all other inputs.
- Reaffirm the agent still **writes no files** and does not mint IDs or indexes — the harness does (decision #2 keeps *classification* in the agent/its module; *materialization* stays in the deterministic program).

### 5.7 `agents/general/documentation-reviewer/...` — **no contract change**

Its 6-key output (`verdict/source_of_truth/other_matches/documented_expected/observed/reason`) and its scored golden baseline are **untouched** (it already emits `missing-docs`). This is itself a guardrail: the routing change lives in the orchestrator + `adjudicate.py`, not in the reviewer. (Avoids regressing the hardened reviewer baseline noted in its `adjudication-prompt.md`.)

### 5.8 `orchestrator-full.md` (prose + guardrails)

- **§1** bullets (documentation-reviewer, orchestrator, bug-reporter): note `missing-docs` now yields a **categorized, report-only unverified bug**; `yes` unchanged.
- **§2** invariants: add "Every `missing-docs` mismatch yields an unverified bug report (report-only, categorized, excluded from CI)."
- **§3 step 4c:** rewrite from "record outcome, no bug" → "record outcome, `exclude_from_cicd:true`, **and** invoke bug-reporter (unverified mode, full capture) → categorized report in the unverified tree + `unverified-index.json`; no CI, no exit gate."
- **§3 step 4d:** generalize the live-capture detour to also fire for `missing-docs` (full artifacts per decision #7) with `documentation_cited:false`, `source_of_truth:null`, `category` set.
- **§3 bug-trigger note:** define **two** report classes — *documented* (verdict `yes`, cited) and *unverified* (verdict `missing-docs`, categorized, report-only).
- **§4:** add HF13–HF17; amend HF2 so a `missing-docs` terminal now also requires an unverified report; HF12 unchanged (still excluded from CI).
- **§5 Phase 0:** create the `results/{date}/{time}/BugReport/` tree; define `date_of_run`/`time_run_started` from RUN_ID.
- **§6:** bug-reporter now invoked mid-loop on **both** `yes` and `missing-docs`.
- **§8 Phase 3 reconcile:** add unverified reconciliation (counts, category legality, index separation, ordering, report-only).
- **Ledger row schema:** add `unverified_bug_id`, `category`; `outcome` enum unchanged (report attaches to the `missing-docs` row).

---

## 6. Guardrails (hard-fail, added to `orchestrator-full.md` §4 and enforced in `adjudicate.reconcile()`)

- **HF13 — Undocumented ≠ dropped.** Every `missing-docs` row MUST carry a non-null `unverified_bug_id` and a `category ∈ UNVERIFIED_CATEGORIES`, with a report file present at the category path. Missing report → BROKEN. (Mirrors HF5.)
- **HF14 — Category is deterministic.** `row.category == bugreport_spec.build_category(normalize_signals(**row_signals))` recomputed from the same signals. Any divergence → BROKEN. (Blocks silent misclassification / drift.)
- **HF15 — Report-only.** No `missing-docs`/unverified row may have `exclude_from_cicd == false`; no unverified bug may appear in the CI add-set; unverified bugs never contribute to `would_exit_code_1`. Violation → BROKEN. (Enforces decision #8.)
- **HF16 — ID/index separation.** Unverified reports carry a `VULN-/BIZ-/SW-` prefix and appear **only** in `unverified-index.json`; `BUG-` reports appear **only** in the verified index. A verified ID in the unverified index (or vice-versa), or a category ID whose report is absent, → BROKEN.
- **HF17 — Vulnerability visibility.** Every `vulnerability` unverified bug is present and sorted **first** in `unverified-index.json` (category-first ordering). Absent/mis-ordered vulnerability bug → BROKEN. (Enforces decision #9 "order of needed".)

Plus a structural **output guardrail** for the agent (§7.1): the emitted unverified decision must be exactly the 6 keys with a legal `category`, else the harness scores it invalid (mirrors the code-review schema gate).

---

## 7. Guardrails, golden test cases, unit tests (deliverables)

### 7.1 Output guardrail validator — NEW
`agents/general/bug-reporter/guardrails/validate_unverified_decision.py` (mirror `validate_output.py`): stdlib-only, frozen `Result`, exit 0/1. Validates the unverified decision object: **exactly** `{title, severity, priority, category, testing_steps, postman_references}`; `severity ∈ {CRITICAL,HIGH,MEDIUM,LOW}`; `priority ∈ {P1,P2,P3,P4}` and consistent with severity via `SEVERITY_TO_PRIORITY`; `category ∈ UNVERIFIED_CATEGORIES`; `testing_steps` is `null` or a non-empty list; `postman_references` is a list. Structure only — never judges prose.

### 7.2 Forge gate — NEW
`agents/general/bug-reporter/forge-gate/unverified_bug_gate.py` (mirror `code_review_gate.py`): pure-Python core `evaluate(rows, reports_root, unverified_index) -> GateResult` checking HF13–HF17 deterministically; writes a receipt under `results/_global/`; exit `0` pass / `1` gate failure / `2` setup error. Ships with `forge-gate/test_unverified_bug_gate.py` and `forge-gate/unverified-bug-gate.golden.json`.

### 7.3 Golden fixture — NEW
`data/bug-reporter/unverified_golden.json` (mirror `golden.json`): `baseline`, `tolerance`, and three case sets, all runnable with **no model** (pure-Python forcing function that must always pass):

- **`category_cases`** — `{id, signals, expect_category}`, minimum coverage:
  - `vuln-deny-2xx`: expected `401`, observed `200` → `vulnerability`.
  - `vuln-spec-auth`: `spec_path` contains `authentication` → `vulnerability`.
  - `vuln-no-password`: observed contains `without password` → `vulnerability`.
  - `vuln-precedence`: BOTH a bypass indicator AND a `500` present → `vulnerability` (V beats S).
  - `biz-wrong-data`: expected `sorted list`, observed `unsorted list`, no system signal → `business-workflow`.
  - `biz-wrong-4xx`: expected `404`, observed `200`, user-visible → `business-workflow`.
  - `sw-500`: observed `500` → `computer-software`.
  - `sw-db`: stderr `database connection refused` → `computer-software`.
  - `sw-default`: no user-visible and no vuln signal → `computer-software` (default bucket).
- **`layout_cases`** — `{id, run_id, agent, category, expect_path, expect_prefix}` pinning the exact folder path and ID prefix per §4.2.
- **`index_cases`** — a set of unverified bugs across categories with `expect_order` (vuln first, then biz, then sw; severity tie-break) and `expect_separation` (no `BUG-` id present).

### 7.4 Unit tests — NEW (pytest, under `agent-foundry/tests/unit/`, `@pytest.mark.unit`)

- `test_bugreport_category.py` — table-driven over `build_category`; asserts every `category_cases` entry; explicit precedence (V>B>S) and boundary tests (empty signals → `computer-software`).
- `test_unverified_materialize.py` — with fixed `FORGE_BUG_DATE`/`FORGE_BUG_TIME`/`run_id`: assert exact unverified path, per-category prefix, full-artifact presence (screenshot/recording/logs), verified mirror path, and that `would_exit_code_1` is unaffected by unverified bugs (report-only).
- `test_unverified_reconcile.py` — feed synthetic ledger rows; assert `reconcile()` **passes** on a well-formed run and flags each of HF13–HF17 on a corresponding injected violation.
- `test_validate_unverified_decision.py` — pass/fail table for the §7.1 validator (missing `category`, illegal category, extra key, severity/priority mismatch, code-fence, prose prefix, two objects).
- `test_unverified_index_order.py` — assert `unverified-index.json` ordering + `by_category` counts + separation from verified.

### 7.5 Regression guard — the leaderboard must not drop
- `test_verified_decision_unchanged.py` — assert `build_reference_decision(failure, registry, postman_items)` (no `verdict`) is **byte-identical** to today for the existing fixtures, and `score_decision` on the 5 `DECISION_FIELDS` is unchanged. Locks the recorded bug-report fidelity baseline (category is scored only in unverified mode).
- Extend/inspect `agent-foundry/tests/test_run_layout.py` if it asserts the old `results/bug-reports/` layout.

---

## 8. Back-compat & risks

| Risk | Detail | Mitigation |
|------|--------|------------|
| Readers of `results/bug-reports/` | `adjudicate.reconcile()` globs `BUG-*.json`; `report_doc_bugs`, `report_bugs`, and `judge/general/bug-reporter/score.py` reference report/index paths. Moving verified bugs to the new tree can break them. | Centralize all paths in one `bug_paths(run_id)` helper; **dual-write** the legacy `results/bug-reports/index.json` for one release; update globs + add a layout test; then remove the legacy write. |
| Leaderboard baseline | `bugreport.py` is scored vs gold; adding `category` could shift fidelity. | Category is added **only** on `missing-docs`; `DECISION_FIELDS` untouched; §7.5 regression test enforces byte-identical verified output. |
| `report_bugs.py` output dir | Currently `results/runs/<run>/general-bug-reporter.bug-reports`. | Update the emitted spec `bug_reports_out`/`index_out` + post-run glob to the new tree in the same change. |
| Volume | `missing-docs` is common; full capture (decision #7) for all unverified is heavy. | Accepted per decision #7; artifacts are pure file writes (asciinema `.cast` + text replay + logs), no external binaries. Revisit only if runtime regresses. |
| Doc-reviewer regression | Any edit to its 6-key contract risks its hardened baseline. | **No change** to the reviewer spec/body (§5.7); routing lives elsewhere. |

---

## 9. Phasing & sequencing

- **Phase A — Pure classifier (no I/O).** §5.1 additions + §7.3 `category_cases` + §7.4 `test_bugreport_category.py` + §7.5 regression guard. Lands independently, fully unit-tested, zero runtime risk.
- **Phase B — Paths/IDs/indexes/materializer.** §5.2 + §7.3 `layout_cases`/`index_cases` + `test_unverified_materialize.py` + `test_unverified_index_order.py`.
- **Phase C — Wire routing.** §5.3–§5.5 (adjudicate/report_doc_bugs/report_bugs) + `reconcile()` HF13–HF17 + `test_unverified_reconcile.py`.
- **Phase D — Guards + prose.** §7.1 validator + §7.2 gate + §5.6 bug-reporter prose + §5.8 orchestrator prose.
- **Phase E — Back-compat migration.** §8 reader updates, drop dual-write, full fixture-run validation.

Each phase is independently testable; A–B touch no live routing.

## 10. Definition of done (acceptance criteria)

1. All §7 golden `*_cases` and unit tests pass; the pure-Python category/layout/index cases pass with **no model**.
2. A fixture run through `adjudicate.py` produces: verified bugs under `verified_bugs/`, unverified under `unverified_bugs/{category}/`, a separate `unverified-index.json`, category-first ordering with **vulnerability first**.
3. `reconcile()` returns `ok:true` on a clean run and `BROKEN` when any of HF13–HF17 is violated (proven by injected-violation tests).
4. Exit code and CI add-set are **unchanged** by unverified bugs (report-only); `missing-docs` remains `exclude_from_cicd:true`.
5. Verified leaderboard fidelity baseline is unchanged (regression guard green).
6. Every unverified report and index entry records the finding agent (`{agent_name}` in path + `finding_agent`/`finding_endpoint` fields).
7. Documentation-reviewer spec and its scored baseline are untouched.

## 11. Out of scope

Changing the documentation-reviewer's verdict logic or contract; adding unverified bugs to CI or the exit gate; root-cause analysis or DummyJSON implementation review; altering the `yes`/`no` paths; new severity taxonomy (existing R1–R9 retained).
