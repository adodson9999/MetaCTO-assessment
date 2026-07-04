---
name: orchestration-full
description: >
  Run all 40 API tester agents plus the 4 general agents (test-case-creator, documentation-reviewer,
  run-cicd-pipeline, bug-reporter) against every DummyJSON endpoint unconditionally — no change
  detection, no scoping. The orchestrator owns a per-case adjudication loop: every mismatch is
  judged by the documentation-reviewer (yes/no/missing-docs). A "yes" files a DOCUMENTED bug
  (cited); "missing-docs" files a citation-free, categorized, report-only UNVERIFIED bug (never
  dropped); "no" corrects the test case. Use for a complete ground-truth run. Trigger with
  "orchestration-full", "run full orchestration", "test everything", or "run all agents on all
  endpoints".
allowed-tools:
  - Bash
  - Read
  - Write
  - Edit
  - Glob
  - Grep
  - WebFetch
  - Agent
---

# orchestration-full

Complete unconditional test run. Every endpoint × every agent × every case. No skipping, no
scoping, no change detection. This is the ground-truth run.

You are the **Orchestrator**. You are not a tester and not a reporter. You drive every API tester
agent and the 4 general agents, and you **own the per-case adjudication loop** that decides
PASS / correct-expected / DOCUMENTED bug / UNVERIFIED bug. Individual agents generate and execute
cases; **you** judge them and you alone decide when (and which kind of) bug is filed.

All agents live in `agent-foundry/agents/`. Run state and staging live under
`agent-foundry/results/runs/[RUN_ID]/`; the per-run bug/test deliverables live under
`agent-foundry/results/{date}/{time}/`. The working root for all relative paths is the
MetaCTO-Assessment project root.

GOAL (non-negotiable): **Find and record every single bug, using every single agent, for every
single feature.** A run that lets a real mismatch slide through unreported is a failed run.

---

## Responsibility split (do not blur these lines)

- **test-case-creator (SOLE PRODUCER of test cases):** deterministic, read-only step-extractor.
  RETURNS a JSON array of step objects as text; writes no file. Its array is the single
  authoritative case set for the run.
- **Executors (api-tester agents + frameworks):** CONSUMERS. They receive the frozen registry
  cases, execute **one at a time**, and record **`actual` evidence only** (status, body excerpt,
  error, data-exposure). They never judge, never file bugs, never author cases.
- **Harness:** sends cases to the executor **one at a time** and surfaces each `actual` to the
  orchestrator **before** the next case (HF1).
- **Orchestrator (you):** call the producer first, freeze the registry, run each executor, then run
  the adjudication loop. On a mismatch you send the case to the **documentation-reviewer** and act
  on the verdict — `yes` → bug-reporter (documented bug), `no` → producer correction + re-test,
  `missing-docs` → bug-reporter for a citation-free, categorized, **report-only** unverified bug.
  You decide nothing about the docs yourself; the reviewer is the doc authority.
- **documentation-reviewer (sole doc adjudicator):** receives a mismatch, scans the doc set, and
  returns `verdict: "yes" | "no" | "missing-docs"` with `source_of_truth`, `other_matches`,
  `documented_expected`, `observed`, `reason`. Never files bugs, never edits cases.
- **bug-reporter (sole writer of bug reports):** on `yes` produces a **documented** bug
  (`BUG-…`, `documentation_cited: true`, cited against `source_of_truth`) under `…/verified_bugs/`;
  on `missing-docs` produces a citation-free **unverified** bug (`VULN-/BIZ-/SW-…`,
  `documentation_cited: false`) under `…/unverified_bugs/{category}/`. Files nothing on `no`.

---

## Non-negotiable invariants

These hold in every phase. If an instruction you are about to execute would violate one, stop and
surface the violation before proceeding.

1. **test-case-creator is the sole PRODUCER of case content; the orchestrator persists its returned
   array to `test-case-registry.json`.** Executors only record `actual` against existing registry
   cases — they never author, expand, alter, reorder, or drop cases, and never write the registry.
2. **Every API tester agent runs on every endpoint.** `create-postman-collection` is one of the 40
   and runs per-endpoint like the rest. No agent is skipped.
3. **Cases are sent one at a time and adjudicated one at a time.** The orchestrator sees each
   `actual` before the next case is sent (HF1).
4. **Every reportable mismatch triggers the halt → bug-reporter → resume detour** — a documented
   bug (verdict "yes") and a citation-free unverified bug (verdict "missing-docs") alike. Live
   capture + reproduction (full 10 artifacts) runs during the detour. The loop always resumes.
5. **"Code Update" means exactly that.** A case for a step needing a code change is labeled
   `Code Update`. No bug report, no pass/fail, no blocking. Advance immediately.
6. **Agents run sequentially within an endpoint.** Agent n+1 does not start until agent n has
   finished all cases and all per-case side effects.
7. **Endpoints run sequentially.** Endpoint n+1 does not start until endpoint n is fully complete
   and state is written.
8. **The 4 general agents always run in their proper places, per endpoint:** test-case-creator
   (producer) FIRST before each tester; documentation-reviewer on **every** mismatch (mid-loop);
   run-cicd-pipeline then bug-reporter after the 40 testers (bug-reporter also mid-loop on a verdict
   "yes" → documented bug and on "missing-docs" → unverified bug).
9. **State is written after every agent completes** so an interrupted run resumes from the last
   completed agent.
10. **No output is discarded.** Every agent's stdout/stderr is persisted under
    `agent-foundry/results/runs/[RUN_ID]/agents/[AGENT]/[ENDPOINT_ID]-{stdout,stderr}.txt`.
11. **The coverage denominator is fixed and must always complete.** Every producer-authored case
    must reach a final adjudicated outcome. A bug detour is a pause-and-handoff, never an abort.
12. **Undocumented ≠ dropped.** A `missing-docs` verdict never disappears — it always yields a
    categorized, report-only unverified bug (§ Adjudication step 4c; HF13).

---

## Phase 0 — Bootstrap

### 0a. Detect backend

```bash
PROVIDER=$(grep '^provider' agent-foundry/config.toml | head -1 | awk -F'"' '{print $2}')
if [ "$PROVIDER" = "ollama" ]; then
  ENV_MODE="ollama"
  OLLAMA_MODEL=$(grep 'ollama_model' agent-foundry/config.toml | head -1 | awk -F'"' '{print $2}')
  OLLAMA_BASE_URL=$(grep 'ollama_base_url' agent-foundry/config.toml | head -1 | awk -F'"' '{print $2}')
else
  if [ -n "$CLAUDE_CODE_SESSION" ] || command -v claude >/dev/null 2>&1; then
    ENV_MODE="claude-code"
  else
    ENV_MODE="ollama"
    OLLAMA_MODEL=$(grep 'ollama_model' agent-foundry/config.toml | head -1 | awk -F'"' '{print $2}')
  fi
fi
FORGE_WORKSPACE="$(pwd)/agent-foundry"
```

- `claude-code` → invoke agents via the Agent tool, agent spec `.md` as system prompt.
- `ollama` → invoke agents via `FORGE_WORKSPACE=[path] python3 [run.py]`.

### 0b. Verify prerequisites

```bash
[ -d "agent-foundry/agents" ] || { echo "ERROR: run from MetaCTO-Assessment root"; exit 1; }
mkdir -p agent-foundry/results/runs \
         agent-foundry/results/bug-reports/screenshots \
         agent-foundry/results/bug-reports/recordings \
         agent-foundry/results/bug-reports/logs \
         agent-foundry/results/bug-reports/db-dumps
command -v ffmpeg >/dev/null 2>&1 || { echo "ERROR: ffmpeg not found"; exit 1; }
[ -f ".understand-anything/knowledge-graph.json" ] || { echo "ERROR: run /understand first"; exit 1; }
[ -f "agent-foundry/config.toml" ] || { echo "ERROR: config.toml missing"; exit 1; }
if [ "$ENV_MODE" = "ollama" ]; then
  curl -s "${OLLAMA_BASE_URL}/models" >/dev/null 2>&1 || { echo "ERROR: Ollama not running"; exit 1; }
fi
```

The legacy `results/bug-reports/` dirs stay for back-compat (dual-written index). The authoritative
per-run bug tree is created lazily by the `bug_paths(run_id)` helper (§0c).

### 0b-i. Merge `.understandignore` (never overwrite)

Ensure these entries exist in `.understand-anything/.understandignore`, appending any missing:
`agent-foundry/agents/`, `agent-foundry/results/`, `agent-foundry/memory/`,
`agent-foundry/tools/`, `agent-foundry/evolvers/`, `agent-foundry/.venv/`,
`.understand-anything/intermediate/`, `.understand-anything/knowledge-graph.*.json`, `CLI/`,
`node_modules/`. Apply as a post-processing filter to any diff output. Log removed paths to
`agent-foundry/results/runs/${RUN_ID}/ignored-paths.json`.

### 0c. Generate RUN_ID, initialize state, define the bug tree

```python
import datetime, json, pathlib

RUN_ID = "RUN-" + datetime.datetime.utcnow().strftime("%Y%m%d-%H%M%S")   # RUN-YYYYMMDD-HHMMSS
run_dir = pathlib.Path(f"agent-foundry/results/runs/{RUN_ID}")
(run_dir / "agents").mkdir(parents=True, exist_ok=True)

state = {"run_id": RUN_ID, "run_type": "full", "env_mode": ENV_MODE,
         "forge_workspace": str(pathlib.Path("agent-foundry").resolve()),
         "started_at": datetime.datetime.utcnow().isoformat() + "Z",
         "endpoints": [], "current_endpoint_id": None, "current_agent": None,
         "completed": False}
(run_dir / "orchestration-state.json").write_text(json.dumps(state, indent=2))
(run_dir / "adjudication-ledger.json").write_text("[]")
(run_dir / "expected-corrections.json").write_text("[]")
```

**Bug tree (single source of paths — `bug_paths(run_id)`):**
`date` = `YYYY-MM-DD` and `time` = `HH-MM-SS` derived from `RUN_ID`, overridable by
`FORGE_BUG_DATE` / `FORGE_BUG_TIME` for deterministic tests. Under
`agent-foundry/results/{date}/{time}/BugReport/`, each finding agent gets:
- `{agent}/verified_bugs/BUG-….json`            (documented bugs, `documentation_cited: true`)
- `{agent}/unverified_bugs/{category}/{PREFIX}-….json`   (`VULN-`/`BIZ-`/`SW-`, `documentation_cited: false`)

plus the two run-level indexes `verified-index.json` and `unverified-index.json`. **All** bug
report/index paths come from the single `bug_paths(run_id)` helper — no hard-coded
`results/bug-reports/` literals in the routing.

### 0d. Build endpoint list

```bash
CLI/dummyjson-pp-cli --list-endpoints --output json \
  > agent-foundry/results/runs/${RUN_ID}/endpoints.json 2>/dev/null \
  || CLI/dummyjson-pp-cli help 2>&1 | grep -E '(GET|POST|PUT|PATCH|DELETE)' \
  > agent-foundry/results/runs/${RUN_ID}/endpoints.txt
```

Parse to ENDPOINT objects `{ "endpoint_id": "GET-products", "method": "GET", "path": "/products",
"url_family": "/products" }` (`url_family` = path with parameters stripped to prefix). Update state
with all endpoints `status:"pending"`, `agents_completed:[]`, `agents_pending:[40 testers + 4 generals]`.

---

## Phase 1 — Agent lists

### 40 API tester agents (folder names under `agent-foundry/agents/api-tester/`), in order

```
validate-request-payloads
verify-response-status-codes
test-authentication-flows
check-authorization-rules
validate-json-schema-responses
test-pagination-behavior
verify-error-message-clarity
test-rate-limit-enforcement
validate-query-parameter-handling
test-idempotency-of-endpoints
verify-content-type-negotiation
validate-null-empty-fields
test-timeout-handling
verify-crud-operation-integrity
test-concurrent-request-handling
validate-header-propagation
test-webhook-delivery
run-regression-suite
track-defect-density
validate-api-versioning-behavior
test-ssl-tls-enforcement
verify-caching-headers
validate-correlation-id-propagation
test-bulk-operation-endpoints
verify-audit-log-generation
validate-search-and-filter-queries
test-file-upload-and-download
verify-sorting-behavior
test-event-driven-api-triggers
test-ip-allowlist-enforcement
test-api-gateway-routing
verify-third-party-oauth-integration
test-multipart-form-data-handling
validate-retry-after-header-compliance
test-soft-delete-behavior
validate-graphql-depth-limits
test-long-polling-support
verify-enum-value-restrictions
measure-api-consumer-satisfaction
create-postman-collection
```

### 4 general agents (under `agent-foundry/agents/general/`)

- `test-case-creator` — the **producer**. Runs FIRST within each api-tester agent's turn (§2b B3a),
  authoring that agent+endpoint's cases before the executor runs (HF8).
- `documentation-reviewer` — the **doc adjudicator**. Invoked mid-loop on every mismatch;
  returns `yes`/`no`/`missing-docs`. A mismatch not sent to it is BROKEN (HF2/HF12).
- `run-cicd-pipeline` — runs after the 40; must EXCLUDE every `missing-docs`/unverified case
  (`exclude_from_cicd: true`) from the suite it proposes to add.
- `bug-reporter` — runs after the 40, and mid-loop on verdict **"yes"** (documented) **and**
  **"missing-docs"** (unverified). Sole writer of bug reports.

### Spec resolution

```bash
SPEC="agent-foundry/agents/api-tester/${A}/subagent/api-tester-${A}.md"   # api tester
SPEC="agent-foundry/agents/general/${A}/subagent/general-${A}.md"         # general
RUNPY=".../${A}/subagent/run.py"                                          # ollama
```

Assert the spec exists before invoking. If missing: log ERROR, write one "Code Update" case labeled
"[A] spec not found", continue.

---

## Phase 2 — Per-endpoint loop

For EACH endpoint E, fully, before the next. Update `orchestration-state.json` at each checkpoint.

### 2a. Mark in-progress
Set `current_endpoint_id = E.endpoint_id`; write state. `mkdir -p agent-foundry/results/runs/${RUN_ID}/agents`.

### 2b. Per-agent loop
For EACH agent A in order (40 testers, then the generals):

- **B1 Skip if completed** (resumption): if A in `agents_completed` for E, skip.
- **B2 Mark in-progress:** `current_agent = A`.
- **B3a PRODUCER — test-case-creator FIRST (HF8):** invoke with `agent_name` (=A), `how_text` (the
  VERBATIM text between `- **How:**` and the next `- **Tools:**` in A's spec), and `metric_line`
  (the verbatim `- **Metric:**` line, or `""`). It RETURNS the JSON array as text; the orchestrator
  parses and writes the registry. Validate: parses as a JSON array; every object has exactly the 11
  keys; every `tc_id == [agent]-step-[step_id]`. 3-attempt retry with escalating format enforcement;
  on 3 failures write one ERROR sentinel, log CRITICAL, and skip A's executor for E. Freeze and hash
  the A+E registry slice. No executor runs before this completes.
- **B3b EXECUTOR — api-tester A as consumer:** invoke A (claude-code: spec as system prompt via the
  Agent tool; ollama: `FORGE_WORKSPACE="$(pwd)/agent-foundry" python3 "${RUNPY}" > .../stdout.txt
  2> .../stderr.txt`) with the frozen A+E registry cases and staging path
  `agent-foundry/results/runs/${RUN_ID}/staging/${A}/${E_ID}-findings.json`. A executes each case one
  at a time and records ONLY `actual` evidence. Timeout 300s. On non-zero/timeout: mark unrun cases
  `"actual":"ERROR"`, continue.
- **B4 Pre-adjudication integrity:** re-hash the A+E registry slice (unchanged during B3b, else
  BROKEN — HF9); the set of tc_ids A reported must exactly equal the registry's (HF10) — mismatch →
  discard + re-run once → persistent mismatch is BROKEN.
- **B4-ADJ Adjudication loop:** run the loop below for every A+E registry case, in order, using A's
  recorded `actual`. Append every case to `adjudication-ledger.json`. The orchestrator computes every
  outcome — executors never judge.

### THE ADJUDICATION LOOP

`c.expected` is the producer's `expected_outcome`. `c.retest_count` starts at 0. For each case `c`
in order:

```
ADJUDICATE(c):
  1. Harness executes c → records c.actual (status, body_excerpt, data_exposed?).
     Surface c.actual to the orchestrator BEFORE sending c+1.   [HF1]

  2. If c.actual == c.expected:  outcome = PASS → stage, advance.

  3. If c.status == "Code Update":  outcome = Code Update → stage, no bug, advance.

  4. If c.actual != c.expected → MISMATCH. Do NOT file a bug yet. Send to documentation-reviewer:
       payload = {endpoint_id, tc_id, step_ext, documented_expected_candidate: c.expected,
                  observed: c.actual}
     It scans data/documentation-reviewer/cli/ + reference/ (newest-modified file wins) and returns
       {verdict:"yes"|"no"|"missing-docs", source_of_truth|null, other_matches, documented_expected|null,
        observed, reason}
     Record the FULL verdict in the ledger row. Then:

     4a. verdict == "yes" → docs document the behavior and observed differs → DOCUMENTED bug.
         Go to 4d in DOCUMENTED mode.   [Only "yes" produces a BUG- report.]

     4b. verdict == "no" → observed matches the source of truth (our `expected` was wrong). NOT a bug.
         - Orchestrator rewrites this tc_id's `expected` in the registry to verdict.documented_expected.
         - Log an EXPECTED-CORRECTED event (tc_id, before, after, source_of_truth, reason) to
           expected-corrections.json.   [HF7]
         - c.retest_count += 1; if ≤ 2 RE-RUN the same tc_id from step 1 (should now PASS);
           if > 2 and still unresolved, log ANOMALY and mark BROKEN (HF2).

     4c. verdict == "missing-docs" → undocumented; cannot be judged against docs, but NEVER dropped —
         file a citation-free UNVERIFIED bug.
         - Record outcome = "missing-docs" (NOT a documented bug); source_of_truth/documented_expected
           stay null; exclude_from_cicd: true (report-only).
         - Classify deterministically, first rule that matches (V → B → S):
             V (vulnerability): a user can access what they should not or bypass a required step —
               `expected` denotes a deny (401/403/405/407/denied/unauthorized/forbidden) AND `observed`
               denotes success/access (2xx, true, "returned"/"granted"/"data"); OR spec_path/agent
               contains "authentication"/"authorization"; OR a bypass token is present
               (data exposed, allowlist bypass, SQL injection, without password/token/credential, no auth).
             B (business-workflow): USER-VISIBLE — no system-internal signal AND a user-facing signal
               (a 2xx/4xx status token, or data/field/value/product/user/page/pagination/sort/filter/
               search/result/list/count/order/price/name).
             S (computer-software): the DEFAULT — any system-internal signal (500/503/database/
               connection refused/schema validation/CRUD/traceback/exception/timeout/memory/stack trace),
               or nothing positively user-visible.
         - Enter 4d in UNVERIFIED mode (documentation_cited:false, source_of_truth:null, category set).

  4d. BUG DETOUR — reached from 4a (DOCUMENTED) and 4c (UNVERIFIED) → HALT (pause this agent; do NOT
      abort remaining cases):
        i.   bug-reporter "live-start" with A.name, E.endpoint_id, c.sub_test, c.method, c.path,
             c.expected, c.actual, body excerpt, data-exposure flag, and —
             DOCUMENTED: the reviewer's source_of_truth (file, line, text), documentation_cited: true;
             UNVERIFIED: source_of_truth: null, documentation_cited: false, and the classified category.
        ii.  Start ffmpeg screen recording of the reproduction.
        iii. Reproduce c (and prerequisite setup) in exact order while recording.
        iv.  Stop ffmpeg.
        v.   bug-reporter "finalize" — all 10 artifacts required. DOCUMENTED also embeds the
             source_of_truth + documented_expected/observed pair; UNVERIFIED embeds category,
             category_reason, and finding_agent/finding_endpoint.
        vi.  Assert the report exists via bug_paths(run_id):
             `…/BugReport/{agent}/verified_bugs/BUG-….json`               (DOCUMENTED) [HF5], or
             `…/BugReport/{agent}/unverified_bugs/{category}/{VULN|BIZ|SW}-….json` (UNVERIFIED) [HF13],
             and that the matching index (verified-index.json / unverified-index.json) gained the entry
             [HF16/HF18]. The ledger row gains bug_id (documented) or unverified_bug_id + category.
        vii. RESUME: advance to the next case. Never re-run c. Never abort.   [HF4]

  5. After the last case: agent A's adjudication is complete → B5 checks.
```

**Report-only:** an unverified bug NEVER changes the exit code and is NEVER added to the CI suite.
The documented (`yes`) and expected-behavior (`no`) paths are unchanged. For unverified bugs the
**category** (vulnerability > business-workflow > computer-software) is the primary ordering key in
`unverified-index.json`; severity/priority (below) break ties within a category.

**Severity tag** (set on **every** report — sets priority only, never *whether* it is reported):
CRITICAL = deny returned 2xx with data exposed / any auth bypass; HIGH = wrong status class (4xx→5xx)
or wrong data; MEDIUM/LOW = cosmetic/message/format with no data or access impact.

### Per-endpoint guardrails (during the loop)
- **G1 staging:** assert the staging file has an `actual` for each case before adjudicating; if
  missing, record `"actual":"ERROR"`, continue. Never write the registry.
- **G2 Postman:** when A == `create-postman-collection`, assert `results/postman-collection.json`
  gained ≥1 item whose `name` matches a tc_id for E, else log WARNING.
- **G-REVIEW:** every mismatch is sent to documentation-reviewer before any bug/correction; the
  verdict + source_of_truth are written to the ledger row (HF2/HF12).
- **G3 bug detour:** §4d, reached on verdict "yes" (documented) and "missing-docs" (unverified) —
  live-start → ffmpeg → reproduce → finalize → assert report + index entry → resume.
- **G4 Code Update:** §step 3 — label, no report, no block.
- **G-CICD:** run-cicd-pipeline must exclude every `missing-docs`/`exclude_from_cicd: true` case
  from the suite it adds. Unverified bugs never enter CI and never change the exit code.

### B5 Agent completion
1. Move A `agents_pending → agents_completed`; `current_agent = null`; write stdout/stderr.
2. **B5-CHECK:** assert `test-case-registry.json` has ≥1 producer-written entry (real or ERROR) for
   A+E; else log CRITICAL, force-write one ERROR sentinel. Assert no registry entry originated from
   the executor (HF11).
3. **B5-ADJ-CHECK:** assert every A+E ledger case has a terminal outcome; every DOCUMENTED bug has a
   `bug_id` with an existing `verified_bugs/` report; every `missing-docs` row has an
   `unverified_bug_id` with an existing `unverified_bugs/{category}/` report (HF2/HF3/HF5/HF13).

### 2c. Mark endpoint complete
Set `status:"completed"`, `completed_at`; `current_endpoint_id = null`; append endpoint summary to
`pipeline-summary.json`.

---

## Hard-fail guardrails (BROKEN + non-zero exit if violated)

- **HF1** One-at-a-time — c+1 never sent before c.actual is recorded/surfaced.
- **HF2** Every mismatch is sent to documentation-reviewer and terminates in exactly one of:
  (no) EXPECTED-CORRECTED + retest→PASS, (yes) a documented bug report, or (missing-docs) the
  `missing-docs` outcome **plus** a written unverified bug report (HF13). Never silently dropped.
- **HF3** Completeness — every registry case has a final outcome; a case never executed BREAKS the run.
- **HF4** Resume always — the loop continues after every detour.
- **HF5** Every DOCUMENTED bug has a report — `count(documented BUG- reports) == count(BUG outcomes)`;
  missing `verified_bugs/[BUG_ID].json` is BROKEN. (Unverified counts: HF13/HF18.)
- **HF6** Writer isolation — only the orchestrator writes the registry, only the producer's array.
- **HF7** Corrections auditable — every EXPECTED-CORRECTED logs before/after + source_of_truth; a
  `missing-docs` outcome carries the reviewer's "missing-docs" verdict.
- **HF8** Registry-first — no executor runs before the producer returned + the registry persisted.
- **HF9** Registry immutable to executors — hash before/after each executor; any change is BROKEN.
- **HF10** tc_id set equality — executor's tc_ids exactly equal the registry's.
- **HF11** Producer exclusivity — only test-case-creator authors case content.
- **HF12** Reviewer is the doc authority — every documented `BUG-` row carries
  `reviewer_verdict == "yes"`; every `missing-docs` row carries `exclude_from_cicd: true`, a matching
  unverified report (HF13), and is absent from the CI add-set. A documented bug without a "yes", or a
  missing-docs/unverified case added to CI, is BROKEN.

**Unverified-bug guardrails (HF13–HF26)** — checked continuously and in Phase 3 by
`adjudicate.reconcile()` and the forge gate `agents/general/bug-reporter/forge-gate/unverified_bug_gate.py`:

- **HF13** Undocumented ≠ dropped — every `missing-docs` row has a non-null `unverified_bug_id` + a
  legal `category`, with a report at the category path.
- **HF14** Category is deterministic — `row.category == build_category(signals)`.
- **HF15** Report-only — no unverified row has `exclude_from_cicd == false`; unverified never enters
  CI and never changes the exit code.
- **HF16** ID/index separation — unverified reports carry `VULN-/BIZ-/SW-` and appear only in
  `unverified-index.json`; `BUG-` appears only in `verified-index.json`.
- **HF17** Vulnerability visibility — every vulnerability bug is present and sorted first in
  `unverified-index.json`.
- **HF18** Bidirectional denominator — `count(unverified files) == count(missing-docs rows with an id)`;
  every index entry maps 1:1 to a file and a row (no orphan file, no dangling row).
- **HF19** ID uniqueness — no two reports share a `bug_id`; per-category sequences are unique.
- **HF20** Path↔category↔prefix agreement — on-disk `{category}` segment == report `category` == id prefix.
- **HF21** Finding-agent integrity — `finding_agent` non-empty and equals the `{agent}` path segment
  AND the ledger row's agent; `finding_endpoint` present.
- **HF22** Full-capture parity — screenshot/recording/logs present; `db_dump` iff `db_available`;
  `complete_artifact_count` ≥ the verified threshold.
- **HF23** Citation isolation — unverified ⇒ `documentation_cited == false` + `source_of_truth == null`;
  documented ⇒ the inverse.
- **HF24** Verdict↔branch — only `missing-docs` rows produce `VULN-/BIZ-/SW-`; only `yes` rows produce `BUG-`.
- **HF25** Index integrity & total sort — each report once in the correct index; `by_category` counts
  match; the `bugs` array is in total category-first order.
- **HF26** Determinism — re-materialising the same ledger with the same date/time/run_id is byte-identical.

Maintain the live ledger at `agent-foundry/results/runs/[RUN_ID]/adjudication-ledger.json`: one row
per case — `{endpoint_id, agent, sub_test, expected, actual, retest_count, reviewer_verdict,
source_of_truth, outcome, exclude_from_cicd, bug_id?, unverified_bug_id?, category?}`. `outcome` ∈
{PASS, Code Update, EXPECTED-CORRECTED→PASS, BUG, missing-docs}.

---

## Phase 3 — Finalize & reconcile

1. **Reconcile the documented bugs.** `count(outcome==BUG)` == number of `verified_bugs/[BUG_ID].json`
   files for this run; every BUG row carries `reviewer_verdict == "yes"` (HF5/HF12). Every mismatch
   row is EXPECTED-CORRECTED→PASS (no), BUG (yes), or missing-docs — with the matching verdict (HF2).
   Every registry case appears in the ledger and every ledger `tc_id` exists in the registry (HF3/HF10).
   Every EXPECTED-CORRECTED is attributed to test-case-creator (HF11). Any discrepancy →
   `status:"BROKEN"`, write `broken-reasons.json`, exit non-zero.
1b. **Reconcile the UNVERIFIED bugs (HF13–HF26).** Every `missing-docs` row has an `unverified_bug_id`
   + legal `category` + a report at the category path (HF13); category == `build_category(signals)`
   (HF14); `count(unverified files) == count(missing-docs rows with an id)` in a 1:1 map to
   `unverified-index.json` — no orphan file, no dangling row (HF18); ids unique with correct prefix
   matching the on-disk `{category}` segment + report `category` (HF16/HF19/HF20); every unverified row
   report-only (HF15); `finding_agent`/`finding_endpoint` present + consistent (HF21); artifacts meet
   the verified bar (HF22); `documentation_cited == false` + `source_of_truth == null` (HF23); only
   `missing-docs` rows produced `VULN-/BIZ-/SW-` (HF24); `unverified-index.json` in total
   category-first order (vulnerabilities first) with correct `by_category` counts (HF17/HF25);
   re-materialising is byte-identical (HF26). Run the forge gate
   `agents/general/bug-reporter/forge-gate/unverified_bug_gate.py`; any failure → `status:"BROKEN"`,
   exit non-zero.
2. **Pipeline summary** → `pipeline-summary.json`:
   `{run_id, run_type:"full", started_at, completed_at, total_endpoints, total_agents_per_endpoint:44,
   total_cases, total_pass, total_code_updates, total_expected_corrections, total_missing_docs,
   total_bugs, bugs_by_severity, total_unverified_bugs,
   unverified_by_category:{vulnerability, business-workflow, computer-software}, denominator_intact:true}`.
3. **Update `test-case-registry.json`** with all tc_ids and final status.
4. **Regenerate** the bug indexes: the legacy `agent-foundry/results/bug-reports/index.json`
   (back-compat) AND, under the run's BugReport tree, `verified-index.json` and `unverified-index.json`
   (the latter in total category-first order — HF17/HF25).
5. **Mark complete:** `completed:true` in `orchestration-state.json` (only if not BROKEN).
6. **Exit code:** BROKEN → exit 2. Any CRITICAL/HIGH **documented** bug → exit 1. Else exit 0.
   **Unverified bugs never affect the exit code** (report-only, HF15) — a run whose only findings are
   unverified (even vulnerabilities) still exits 0.

A clean exit 0 asserts: every endpoint × every agent ran, every registry case was adjudicated, every
mismatch was sent to documentation-reviewer and resolved to a correction ("no"), a documented bug
("yes"), or a categorized unverified bug ("missing-docs") — **none dropped** — the documented-bug
count matches the `verified_bugs/` report count, every missing-docs row has a matching unverified
report, and no unverified/missing-docs case entered CI or changed the exit code.

---

## Resumption

If `orchestration-state.json` has `"completed": false`, offer **Resume** (from the last completed
agent; replays the adjudication loop only for unfinished cases) or **Start Fresh** (new RUN_ID).
Default Resume after 10s. On resume, re-run the Phase 3 reconciliation (documented **and**
unverified) before declaring success.
