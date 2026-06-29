# Task Spec — API Request-Body Contract Tester

> Captured in Phase 2 of forge-agents. This is the single task all four agents
> (LangGraph, CrewAI, Claude Code subagent, Claude Agent SDK) implement, and the
> basis for the judge's numeric metric. **Awaiting sign-off before Phase 3.**

## The task

Given an **OpenAPI spec** and a **running API**, the agent tests every documented
body-taking endpoint by sending one **valid** payload and five **invalid** payloads,
records the real HTTP status of each, and reports which invalid payloads the API
correctly rejected with `400`.

One spec + one live API in → one structured **contract-test report** out.

### Procedure (identical for all four agents)

1. Parse the OpenAPI spec → extract the request-body schema for every endpoint.
2. Generate **1 valid** payload per endpoint that satisfies all schema constraints.
3. Send it via the correct HTTP method; record the status (expect `2xx`).
4. Generate **5 invalid** payloads per endpoint:
   - `inv_missing_required` — drop one required field
   - `inv_wrong_type` — wrong data type on one field
   - `inv_extra_field` — one extra undocumented field
   - `inv_all_null` — all documented fields set to `null`
   - `inv_maxlength` — a string field at `maxLength + 1` chars
     (not applicable to endpoints with no `maxLength` string field — see carts)
5. Send each; record the status (the contract expects `400`).
6. Emit per-case rows: endpoint, method, variant, expected class, **actual code**, pass/fail.

## Inputs

- **Spec:** `data/openapi.json` — OpenAPI 3.0, authored from DummyJSON's routes +
  controllers (22 body-taking endpoints). This is the file the agents parse.
- **Target API:** local DummyJSON in `assessment/MetaCTO-Assessment`, booted
  air-gapped (no Mongo) with:
  `JWT_SECRET=forge_test_secret MONGODB_URI= NODE_ENV=development PORT=8899 LOG_ENABLED=false node index.js`
  `validateEnvVar` only needs the vars *defined*; `connectDB` no-ops on an empty URI.
- **Endpoint set (22):** `auth/login`; and `add`/`PUT`/`PATCH` for products, posts,
  todos, users, recipes, carts, comments. PUT/PATCH use existing `id=1`.

## What a correct / good output looks like

Each agent writes `results/run_<agent>_<ts>.json`:

```json
{
  "agent": "langgraph",
  "metric_headline": {"payload_rejection_rate_pct": 13.08,
                      "invalid_sent": 107, "invalid_rejected_400": 14},
  "cases": [
    {"slug": "auth_login", "method": "POST", "path": "/auth/login",
     "variant": "inv_missing_required", "expected_class": "400",
     "actual_code": 400, "actual_class": "400", "pass": true},
    ...
  ]
}
```

- Every applicable (endpoint × variant) case present (full coverage).
- `actual_code` is the **real** code from a **real** HTTP request — hallucinated
  results are an automatic fail for that case.
- `pass` = (actual_class == expected_class).

## The metric

Two layers, both numeric and machine-read from `results/`:

1. **Headline (each agent emits):** **Payload Rejection Rate** =
   (invalid payloads returning `400` ÷ invalid payloads sent) × 100.
   This is a property of the *target API*; a faithful agent reproduces the gold value.

2. **Judge's rank key — Contract-Test Fidelity (0–100):** the fraction of gold
   cases where the agent's observed `actual_class` equals the gold `actual_class`
   for the same (endpoint, variant). **Missing/unsent cases score 0.** This rewards
   the framework that (a) covers the whole matrix, (b) builds payloads that truly
   match each variant's intent, (c) sends with the right method/path, and (d)
   records results without hallucinating.
   - Tie-breakers, in order: coverage (cases attempted) → valid-payload success
     rate → wall-clock seconds.

> **Why fidelity, not raw rejection rate, ranks the agents:** all four hit the
> same API, so a correct run yields the same rejection rate. What differs between
> frameworks is test fidelity — coverage, payload-construction quality, faithful
> recording. The judge formalizes that in Phase 4.

## Ground truth (already built)

`data/gold.json` + `data/gold/<slug>.json` — produced by `data/build_gold.py`, the
deterministic **reference** (not one of the four agents). It authors the spec,
derives the canonical 6-payload matrix, sends every payload to the live API, and
records the **real** observed status. Rebuild any time with
`BASE_URL=http://localhost:8899 python3 data/build_gold.py`.

**Empirical result:** 22 endpoints · 129 payloads · 107 invalid · **14 rejected →
Payload Rejection Rate = 13.08%.** DummyJSON validates only a subset
(`auth/login`, `carts/*`, `comments/add`, `todos/add`, `posts/add`); products,
users, recipes echo `2xx` for junk. The low rate is the API's real contract — and a
genuine QA finding, not an agent failure.

## Constraints / invariants

- **Local & air-gapped.** Backend = Ollama `qwen2.5:14b-instruct` via `config.toml`.
  Target API is local. No non-local calls.
- **Payload generation is LLM-driven** (the agent uses the backend to produce the
  6 variants from the parsed schema) — this is where the frameworks differ.
  **HTTP send + status assertion + recording are deterministic code.**
- **Fixed matrix:** exactly 6 payloads/endpoint, the 5 invalid variants above.
- **Sandbox:** all agent read/write/exec confined to the `agent-foundry/` workspace
  (plus HTTP to the local target). Shared EverOS memory pool (common
  `project_id`/`app_id`, per-agent `agent_id`).
- **Implementable in all four frameworks** — the procedure is plain orchestration
  (parse → generate → send → assert → emit), portable to each.

## Open defaults flagged for your sign-off

1. LLM-driven payload generation (vs. fully deterministic). Default: LLM-driven.
2. Excluded from the matrix: `/2fa` (301-redirects), `/auth/refresh` (401),
   `/user/login` (dup of `/auth/login`), `/c/generate` (meta). Say if you want any in.
3. Rank key = Contract-Test Fidelity; headline = Payload Rejection Rate.
