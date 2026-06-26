# Task Spec — API Run Regression Suite

> Position **api-tester**, workflow **run-regression-suite**. Captured in Phase 2 of
> forge-agents. This is the single task all four agents (LangGraph, CrewAI, Claude Code
> subagent, Claude Agent SDK) implement, and the basis for the judge's numeric metric.
> Coexists with the other api-tester builds. **Backend = Claude** (`claude-haiku-4-5`)
> for this task per the build request — set via `FORGE_PROVIDER=claude-haiku` so the
> foundry's global default is untouched for other tasks. **DummyJSON is never modified**
> (read-only GET /health only — the deployment-confirmation step).

## The task

Execute the automated regression suite against a new API build (build N) and confirm
that **zero test IDs that passed in the immediately preceding CI build (build N-1) now
fail**. Any such failure is a **regression** that blocks deployment.

The agent's role in the pipeline is the **comparison + report** step. Given the build
N-1 test-result artifact and the build N test-result artifact, it:

1. recovers **PREV_PASSED_IDS** = the test IDs whose status in build N-1 is `passed`,
2. finds the **regressions** = PREV_PASSED_IDS whose status in build N is `failed`
   (a prev-passed test that is **absent**, **skipped**, or **still passing** in build N
   is **not** a regression; an **already-failing** test is **not** a regression),
3. finds **newly_passing** = tests that failed in N-1 and pass in N,
4. emits the **seven-field regression report** (exact field names):
   `build_n_nus_1`, `build_n`, `total_tests_in_suite`, `prev_passed_count`,
   `regressions` (list of `{id, failure_message}`), `newly_passing` (list of ids),
   `overall_status` (`"fail"` iff any regression, else `"pass"`).

One build pair in → one structured regression report out → one scored field set.

The surrounding CI actions (deploy build N, run the suite, set the pipeline exit code,
block the deployment, publish the report, notify the team) are the **deterministic
harness / CI's** job, **not the agent's** — the agent is purely analytical and is
forbidden from deploying, executing, calling hosts, or changing any pipeline state
(debate-gated line L10). The harness sets exit-code semantics from the report:
`overall_status == "fail"` ⇒ block (exit 1); `"pass"` ⇒ allow (exit 0).

## Target / inputs — Phase-2 fork (DummyJSON has no CI-artifact surface)

DummyJSON exposes **no CI build-result-artifact surface** and **must not be modified**,
so — mirroring the **track-defect-density** and **validate-search-and-filter**
precedents — the "test result artifacts" are **local, air-gapped fixtures** under
`data/run-regression-suite/builds/<pair>/`, one `(build N-1, build N)` pair per named
reporter format the task lists:

| pair          | format        | build N-1 → build N | seeded result                                   |
|---------------|---------------|---------------------|-------------------------------------------------|
| newman_junit  | JUnit XML     | ci-1042 → ci-1043   | 2 regressions, 1 newly-passing, 1 already-failing |
| pytest_junit  | JUnit XML     | build-77 → build-78 | 0 regressions, 1 newly-passing (clean: deploy)   |
| jest_json     | Jest --json   | gh-2001 → gh-2002   | 2 regressions, 1 already-failing (excluded)      |
| pytest_json   | pytest-json   | rel-9 → rel-10      | 1 regression; a prev-passed test **removed** in N |

The **"deploy build N + GET /health == 200"** step (How step 2) is honored by the
harness pinging the **live local DummyJSON `/health`** read-only before scoring
(route exists: `src/routes/index.js` maps `/health` → testRoutes). DummyJSON is the
stand-in "deployed build N test environment"; it is never written to.

## Tooling mapping

The task names Postman/Newman (JUnit reporter), pytest (JUnit XML), Jest (`--json`),
GitHub Actions/Jenkins (CI orchestration + artifact storage), and TestRail (history).
The agent is reporter-agnostic: it parses the three artifact formats
(`junit_xml` / `jest_json` / `pytest_json`) and the harness plays the CI-orchestration
role (artifact retrieval, health gate, exit code, leaderboard as the "dashboard",
EverOS note as the "history track"). No external SaaS is contacted — air-gapped.

## Metric

- **Task gate metric — Regression Rate** = (test IDs passed in N-1 and failed in N ÷
  total test IDs passed in N-1) × 100. **Pass = exactly 0** (zero regressions); **Fail
  = any value > 0** (a single regression blocks deployment, no tolerance). Already-
  failing tests are excluded. This is a property of the build-pair fixtures
  (40% / 0% / 50% / 33.33% for ci-1043 / build-78 / gh-2002 / rel-10), so the genuine
  finding is **which build-N deployments must be blocked**: ci-1043, gh-2002, rel-10
  (build-78 may deploy).

- **Forge ranking metric — Regression-Report Fidelity** = % of (build_pair × field)
  cells where the agent's emitted report matches the deterministic gold report
  (denominator = 4 × 7 = 28). Because the task is deterministic and the prompt is
  tightly debate-gated, correctness saturates; the leaderboard breaks ties with
  **report_conformance** (raw structural exactness) → **message_fidelity** → **tokens**
  → **elapsed**. See `judge/run-regression-suite/metric.json`.

## Outputs

- Agents: `results/runs/<run-id>/<agent>.json` (+ `.cases.json` with per-pair detail).
- Judge: `results/leaderboard-run-regression-suite.{json,md}`.
- Gold: `data/run-regression-suite/gold.json` (+ `gold/<pair>.json`).

## Constraints

- **Backend = Claude only** (no Ollama), via `FORGE_PROVIDER=claude-haiku`.
- **DummyJSON untouched** — read-only GET `/health` is the only call to it.
- **Sandboxed** — all agent I/O inside `FORGE_WORKSPACE`.
- **Air-gapped** except the explicit, opt-in cloud Claude backend (skill invariant 5).
