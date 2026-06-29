# Task Spec — API Pagination-Behavior Tester

> Position **api-tester**, workflow **test-pagination-behavior**. Captured in Phase 2
> of forge-agents. This is the single task all four agents (LangGraph, CrewAI,
> Claude Code subagent, Claude Agent SDK) implement, and the basis for the judge's
> numeric metric. Coexists with the api-tester/validate-request-payloads build.

## The task

Given a **running paginated API** and a per-collection **pagination contract**, the
agent produces a **pagination test plan** that walks a 25-record window in pages of
10 and probes invalid pagination parameters. A deterministic harness executes the
plan with **read-only GET requests** and records, per scenario, whether the API:

- returns page 1 = 10 records with a next-page indicator,
- returns page 2 = 10 **non-overlapping** records with a next-page indicator,
- returns page 3 = 5 records with **no** next-page indicator,
- yields a union of all three pages = **25 unique IDs, zero duplicates**, equal to the window,
- returns an error on invalid pagination parameters.

One collection contract in → one structured pagination test plan out → one scored
scenario table.

## Target — DummyJSON, tested AS-IS (read-only, never modified)

Per the Phase-2 decision (**DummyJSON as-is, gold = real behavior**): the agents
test the local DummyJSON unchanged. Its real pagination contract is:

- **Offset pagination** via query params `limit` (page size) and `skip` (offset) —
  there is **no cursor / no `next_cursor`** field.
- Response shape `{ <list_field>: [...], total, skip, limit }`. "Has next page" is
  **derived**: `(skip + returned_count) < total`.
- Invalid-parameter handling is **lenient**: only a non-numeric `limit`/`skip` →
  `400`. `limit=-1` and `limit=0` → `200`; an unknown `cursor` param → `200` (ignored).

**"Seed exactly 25 records"** is honored without touching the target: the datasets
are fixed and read-only, so the harness **designates** a 25-record window via a
read-only `GET <collection>?limit=25&skip=0` and records those IDs as `EXPECTED_IDS`.
**All HTTP is GET only** — no POST/PUT/PATCH/DELETE against the target.

The literal request used `page_size`/`page`/`cursor`/`next_cursor` and strict `400`s;
those names/semantics are mapped onto DummyJSON's real `limit`/`skip` model in the
agent brief, and the idealized contract is encoded per-scenario as the `ideal` token.
Where the real token differs from the ideal, that is a **genuine QA finding about
DummyJSON**, not an agent failure (mirrors the validate-request-payloads philosophy).

## Inputs

- **Contract:** `data/test-pagination-behavior/pagination_spec.json` — the collection
  catalogue + param mapping (`limit`/`skip`), `page_size=10`, `window_size=25`. This is
  what the agents are briefed from.
- **Collections (6):** `/products`, `/posts`, `/comments`, `/todos`, `/users`,
  `/recipes` (each has > 25 records and a sibling `total`).
- **Target API:** local DummyJSON on `:8899`, booted air-gapped (no Mongo):
  `JWT_SECRET=forge_test_secret MONGODB_URI= NODE_ENV=development PORT=8899 LOG_ENABLED=false node index.js`.

## What a correct / good agent output looks like

Each agent emits, per collection, a single eight-key plan object (the debate-gated
"ask"): `collection, list_field, id_field, page_size_param, offset_param, page_size,
window_size, pages, invalid`, where:

- `pages` = exactly three objects — `page1 {skip 0, limit 10}`, `page2 {skip 10,
  limit 10}`, `page3 {skip 20, limit 5}` (page3 capped to the window remainder).
- `invalid` = exactly four single-parameter probes — `{limit:"-1"}`, `{limit:"0"}`,
  `{limit:"abc"}`, `{cursor:"invalid-cursor-xyz"}` (string values, exact).

The harness then writes `results/runs/<run>/<agent>.{json,cases.json}` with the
per-(collection, scenario) **observed token** from the real read-only requests.

## The metric

Two layers, both numeric and machine-read from `results/`:

1. **Headline (each agent emits): Pagination Correctness Rate** =
   (scenarios where the API behaves per the idealized contract ÷ total scenarios) × 100.
   A property of the *target API*; a faithful agent reproduces the gold value
   (empirically **77.78%** — see below).

2. **Judge's rank key — Pagination-Test Fidelity (0–100):** the fraction of gold
   `(collection, scenario)` cases where the agent's harness-observed token equals the
   gold token. **Uncovered scenarios score 0.** This rewards the framework that builds
   the correct three-page matrix (right `limit`/`skip`, page3 capped), the four invalid
   probes (correct param names + literal string values), and faithfully exercises every
   scenario. Pass = 100%; fail = any scenario uncovered or mis-constructed.

> **Why fidelity, not raw correctness, ranks the agents:** all four hit the same API
> read-only, so a correct run yields the same correctness rate. What differs between
> frameworks is test fidelity — plan coverage and request-construction quality.

## Scenario set (18 per collection — the metric denominator)

`page1_status/count/has_next`, `page2_status/count/no_overlap/has_next`,
`page3_status/count/no_overlap/is_last`, `union_unique_count/zero_duplicates/equals_window`,
`invalid_page_size_negative/zero/nonnumeric`, `invalid_cursor`. Defined once in
`agents/common/pagination_spec.py` (shared by gold + harness).

## Ground truth (already built)

`data/test-pagination-behavior/gold.json` + `gold/<collection>.json` — produced by
`build_gold.py`, the deterministic **reference** (not one of the four agents). It
authors the contract, derives the canonical correct plan, sends every read-only
request to the live API, and records the **real** observed token per scenario.
Rebuild any time with
`BASE_URL=http://localhost:8899 python3 data/test-pagination-behavior/build_gold.py`.

**Empirical result:** 6 collections · 18 scenarios each · 108 total · 84 API-correct
→ **Pagination Correctness Rate = 77.78%**. The 4 failures per collection are real
DummyJSON characteristics and legitimate QA findings:
- `page3_is_last` → false: `total` reflects the whole collection (e.g. 194), so a
  logical 25-window never signals "last page" — DummyJSON has no cursor/last-page flag.
- `invalid_page_size_negative` / `invalid_page_size_zero` → 200: `limit=-1`/`limit=0`
  are accepted (lenient validation; `limit=0` means "return all").
- `invalid_cursor` → 200: an unknown `cursor` param is silently ignored.

## Constraints / invariants

- **Local & air-gapped.** Backend = Ollama `qwen2.5:14b-instruct` via `config.toml`.
  Target API is local. No non-local calls.
- **DummyJSON is never modified.** Read-only GET only; no seeding, no writes.
- **Plan generation is LLM-driven** (each framework's LLM builds the plan from the
  brief) — this is where the frameworks differ. **Execution + scoring are deterministic
  code** (the harness sends read-only GETs and records the real responses).
- **Sandbox:** all agent read/write/exec confined to `agent-foundry/` (plus read-only
  HTTP to the local target). Shared EverOS memory pool (common `project_id`/`app_id`,
  per-agent `agent_id`).
- **Implementable in all four frameworks** — plain orchestration (brief → plan), portable.

## Open defaults flagged for sign-off

1. Target = DummyJSON as-is, gold = real behavior (your Phase-2 choice). Headline rate
   is 77.78% by the API's real contract, not 100%.
2. Window realized via read-only `GET ?limit=25` (no seeding, since the target is
   read-only and fixed).
3. Rank key = Pagination-Test Fidelity; headline = Pagination Correctness Rate.
