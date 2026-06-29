# Task Spec — API Query-Parameter-Handling Tester

> Position **api-tester**, workflow **validate-query-parameter-handling**. Captured in
> Phase 2 of forge-agents. This is the single task all four agents (LangGraph, CrewAI,
> Claude Code subagent, Claude Agent SDK) implement, and the basis for the judge's
> numeric metric. Coexists with the other api-tester builds. **Backend = Ollama**
> (`qwen2.5:14b-instruct`, local/air-gapped) — set via the `FORGE_PROVIDER=ollama`
> override (also the foundry's global default). The Phase-4 script does not start the
> Ollama server; start it yourself before a run. _(History: this build was originally
> wired to Claude `claude-haiku-4-5`; switched to Ollama on request.)_

## The task

Given a **running API** and a per-collection **documented query-parameter contract**,
the agent produces a **query-parameter test plan** that probes each documented
parameter four ways — required-parameter **absent**, present with the **wrong type**,
present with a **valid** value, and an **undocumented** parameter added. A
deterministic harness executes the plan with **read-only GET requests** and records,
per case, whether the API:

- returns **400** when a required parameter is absent,
- returns **400** when a parameter is present with the wrong type,
- returns **200** for a valid value **and realizes the parameter's filter effect**
  (verified record-by-record), and
- handles an undocumented parameter per the API's **documented policy** (here:
  ignore unknown params → **200**).

One collection contract in → one structured query-parameter test plan out → one scored
scenario table.

## Target — DummyJSON, tested AS-IS (read-only, never modified)

Per the standing Phase-2 decision (**DummyJSON as-is, gold = real behavior**): the
agents test the local DummyJSON unchanged. Its real query-parameter contract (from
`src/middleware/clean-request.js`, applied to every list route) is:

- `limit` — integer, optional (default 30). Non-numeric → **400**.
- `skip` — integer, optional (default 0). Non-numeric → **400**.
- `select` — string (csv field list), optional. Projection filter (always adds `id`).
- `sortBy` — string, optional.
- `order` — string, enum {asc, desc}, optional. Validated **only when `sortBy` is also
  present**; an out-of-enum value then → **400**. `order` alone is silently ignored.
- `q` — string, the search query on the `<collection>/search` route. The **idealized**
  contract declares `q` **required** on `/search`; DummyJSON treats it as optional
  (absent `q` → 200 over the whole collection).
- **Undocumented parameters** (e.g. `unexpected_param`) are silently **ignored → 200**;
  the documented policy for this API is therefore "ignore unknown params" (ideal 200).

The literal request used generic "required query parameters" and strict 400s; those are
mapped onto DummyJSON's real parameter model in the agent brief, and the idealized
contract is encoded per-scenario as the `ideal` token. Where the real token differs
from the ideal, that is a **genuine QA finding about DummyJSON**, not an agent failure
(mirrors the validate-request-payloads / pagination philosophy).

## Inputs

- **Contract:** `data/validate-query-parameter-handling/queryparam_spec.json` — the
  collection catalogue + documented-parameter catalogue (name, type, required, enum) +
  the undocumented-parameter policy. This is what the agents are briefed from.
- **Collections (4):** `/products`, `/posts`, `/users`, `/recipes` — the four list
  collections that **also expose a `/search` route**, so every documented parameter
  (including the idealized-required `q` on `/search`) is uniformly testable. Comments
  and todos have no `/search` route and are excluded.
- **Target API:** local DummyJSON on `:8899`, booted air-gapped (no Mongo):
  `JWT_SECRET=forge_test_secret MONGODB_URI= NODE_ENV=development PORT=8899 LOG_ENABLED=false node index.js`.

## What a correct / good agent output looks like

Each agent emits, per collection, a single five-key plan object (the debate-gated
"ask"): `collection, list_field, id_field, search_path, cases`, where `cases` is
**exactly nine objects** in fixed order:

1. `missing_required_q` — route `search`, type `missing`, params `{}` (q absent)
2. `wrongtype_limit_nonnumeric` — list, wrong_type, `{limit:"abc"}`
3. `wrongtype_skip_nonnumeric` — list, wrong_type, `{skip:"abc"}`
4. `wrongtype_order_badenum` — list, wrong_type, `{sortBy:"id", order:"NOT_A_VALID_VALUE"}`
5. `valid_limit` — list, valid, `{limit:"5"}`, filter `limit`/`5`
6. `valid_select` — list, valid, `{select:"id"}`, filter `select`/`id`
7. `valid_order` — list, valid, `{sortBy:"id", order:"desc"}`, filter `order`/`desc`
8. `valid_q` — search, valid, `{q:"e"}`
9. `undocumented_ignored` — list, undocumented, `{unexpected_param:"test123"}`

The harness then writes `results/runs/<run>/<agent>.{json,cases.json}` with the
per-(collection, scenario) **observed token** from the real read-only requests, plus a
record-by-record **filter verification** for the three valid cases.

## The metric

Two layers, both numeric and machine-read from `results/`:

1. **Headline (each agent emits): Query Parameter Handling Accuracy** =
   (parameter test cases where the API returns the correct response code AND, for valid
   cases, the response body reflects the parameter's filtering effect ÷ total cases) ×
   100. A property of the *target API*; a faithful agent reproduces the gold value.
   Pass = 100%; fail = any required-absent request returning non-400, any wrong-type
   request returning non-400, or any valid filter request returning records that do not
   match the filter value.

2. **Judge's rank key — Query-Parameter Test Fidelity (0–100):** the fraction of gold
   `(collection, scenario)` cases where the agent's harness-observed token equals the
   gold token. **Uncovered scenarios score 0.** This rewards the framework that builds
   the correct nine-case matrix (right routes, exact param names + literal string
   values, the bad-enum order probe paired with `sortBy`, and the filter/filter_value
   pairs the harness verifies), and faithfully exercises every scenario. Pass = 100%;
   fail = any scenario uncovered or mis-constructed.

> **Why fidelity, not raw accuracy, ranks the agents:** all four hit the same API
> read-only, so a correct run yields the same accuracy. What differs between frameworks
> is test fidelity — plan coverage and request-construction quality.

## Scenario set (12 per collection — the metric denominator)

`missing_required_q`, `wrongtype_limit_nonnumeric`, `wrongtype_skip_nonnumeric`,
`wrongtype_order_badenum`, `valid_limit_status`, `valid_limit_filter`,
`valid_select_status`, `valid_select_filter`, `valid_order_status`,
`valid_order_filter`, `valid_q_status`, `undocumented_ignored`. Defined once in
`agents/common/queryparam_spec.py` (shared by gold + harness). The nine emitted cases
expand to twelve scored scenarios because each of the three valid-filter cases yields a
status scenario AND a filter scenario.

## Ground truth (built by build_gold.py)

`data/validate-query-parameter-handling/gold.json` + `gold/<collection>.json` — produced
by `build_gold.py`, the deterministic **reference** (not one of the four agents). It
authors the contract, derives the canonical correct nine-case plan, sends every
read-only request to the live API, verifies the filter effects, and records the **real**
observed token per scenario. Rebuild any time with
`BASE_URL=http://localhost:8899 python3 data/validate-query-parameter-handling/build_gold.py`.

**Expected empirical result:** 4 collections · 12 scenarios each · 48 total · 44
API-correct → **Query Parameter Handling Accuracy ≈ 91.67%**. The single failure per
collection is a real DummyJSON characteristic and a legitimate QA finding:
- `missing_required_q` → 200: the `/search` route does **not** require its `q`
  parameter; an absent-required-parameter request returns the whole collection (200)
  instead of 400.

DummyJSON is strict on parameter **type** (non-numeric `limit`/`skip` and an out-of-enum
`order` with `sortBy` all → 400) — those scenarios pass.

## Constraints / invariants

- **Backend = Ollama** (`qwen2.5:14b-instruct`, local/air-gapped) for this task, via
  `FORGE_PROVIDER=ollama`. langgraph uses ChatOllama; crewai uses `ollama/<model>`;
  claude_sdk + the subagent reach it through the OpenAI-compatible local endpoint
  (Ollama `/v1`). No cloud calls. The Phase-4 script does not start the Ollama server —
  start it (`ollama serve`) and pull the model before running.
- **DummyJSON is never modified.** Read-only GET only; no seeding, no writes.
- **Plan generation is LLM-driven** (each framework's LLM builds the plan from the
  brief) — this is where the frameworks differ. **Execution + scoring are deterministic
  code** (the harness sends read-only GETs, verifies filter effects, records responses).
- **Sandbox:** all agent read/write/exec confined to `agent-foundry/` (plus read-only
  HTTP to the local target). Shared EverOS memory pool (common `project_id`/`app_id`,
  per-agent `agent_id`).
- **Implementable in all four frameworks** — plain orchestration (brief → plan), portable.

## Open defaults flagged for sign-off

1. Target = DummyJSON as-is, gold = real behavior (standing Phase-2 choice). Headline
   accuracy is ~91.67% by the API's real contract, not 100%.
2. Endpoint set = the 4 searchable collections (products/posts/users/recipes), so the
   required-`q` scenario is uniform; comments/todos excluded (no `/search`).
3. Undocumented-parameter policy is **defined** as "ignore → 200" (matches DummyJSON),
   so it is not falsely flagged as a finding. Rank key = Query-Parameter Test Fidelity;
   headline = Query Parameter Handling Accuracy.
