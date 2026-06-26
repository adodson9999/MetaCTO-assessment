# Task Spec — API Versioning-Behavior Tester

> Position **api-tester**, workflow **validate-api-versioning-behavior**. Captured in
> Phase 2 of forge-agents. This is the single task all four agents (LangGraph, CrewAI,
> Claude Code subagent, Claude Agent SDK) implement, and the basis for the judge's
> numeric metric. Coexists with the other api-tester builds. **Backend = Ollama**
> (local, air-gapped) for this task per the updated build request ("update the llm to
> Ollama") — set via the `FORGE_PROVIDER=ollama` override in `phase4_versioning_run.sh`,
> so the foundry's global `config.toml` is left untouched. langgraph uses ChatOllama,
> crewai the `ollama/<model>` LiteLLM string, and claude_sdk + the subagent POST the
> local Ollama `/v1` OpenAI-compatible endpoint — no Anthropic key, no proxy, nothing
> leaves the machine. (Originally built on `claude-haiku-4-5`; switched to Ollama on request.)

## The task

Given a **running API** and a per-endpoint **documented versioning contract**, the
agent produces a **versioning test plan** that exercises every version of each
versioned endpoint. A deterministic harness executes the plan with **read-only GET
requests**, validates each 200 body against the documented per-version JSON Schema
with **ajv v8**, reads the **Deprecation** response header, and records, per case,
whether the API:

- returns **200** for the **current** version, its body conforms to the **v2 schema**,
  and it carries **no Deprecation header**;
- returns **200** for the **deprecated** version, its body conforms to the **v1
  schema**, and it carries a **Deprecation header** whose value is a **valid ISO-8601
  date in the future**;
- the v2-only field (`schema_diff_field`) is **present in the v2 body** and **absent
  from the v1 body**, while fields common to both schemas appear in both;
- returns exactly **404** for unsupported numeric versions (`v0`, `v99`) and **400 or
  404** for a non-numeric version token (`vbeta`).

One endpoint contract in → one structured versioning test plan out → one scored
scenario table (13 scenarios/endpoint).

## Target — DummyJSON, tested AS-IS (read-only, never modified)

Per the standing Phase-2 decision (**DummyJSON as-is, gold = real behavior**): the
agents test the local DummyJSON unchanged. **DummyJSON implements no API versioning** —
there is no `/vN` router and no `Deprecation` header anywhere (confirmed in
`src/routes/index.js` and a grep of `src/`). Every version-prefixed URL — current,
deprecated, OR unsupported — therefore falls through to the catch-all `app.get('*')`
handler and returns **404** with an HTML body and no Deprecation header.

The **idealized** strict versioning contract (current → 200 + schema + no Deprecation;
deprecated → 200 + schema + future ISO-8601 Deprecation; unsupported → 404 / 400) is
encoded per-scenario as the `ideal` token. Where the real token differs from the
ideal, that is a **genuine QA finding about DummyJSON**, not an agent failure (mirrors
the validate-request-payloads / pagination / query-parameter philosophy). Empirically
the headline **Version Routing Accuracy ≈ 30.77%** (16/52): only the three unsupported
probes per endpoint match the ideal 404, plus the current-version "no Deprecation
header" scenario (incidentally true because the 404 carries none); the documented
current/deprecated versions wrongly 404, and the schema/Deprecation scenarios have no
200 body to observe.

## Inputs

- **Contract:** `data/validate-api-versioning-behavior/versioning_spec.json` — the
  endpoint catalogue + supported versions (v2 current, v1 deprecated) + unsupported
  versions (v0, v99, vbeta) + the `schema_diff_field` + the documented future
  deprecation date. Authored by `build_gold.py`. This is what the agents are briefed
  from. Per-version response schemas are produced by `versioning_spec.schema_for`
  (v2 adds `schema_diff_field`; v1 omits it).
- **Endpoints (4):** `/products`, `/posts`, `/users`, `/recipes` — the four list
  collections used across the api-tester builds.
- **Target API:** local DummyJSON on `:8899`, booted air-gapped (no Mongo):
  `JWT_SECRET=forge_test_secret MONGODB_URI= NODE_ENV=development PORT=8899 LOG_ENABLED=false node index.js`.

## What a correct / good agent output looks like

Each agent emits, per endpoint, a single four-key plan object (the debate-gated
"ask"): `endpoint, list_field, schema_diff_field, cases`, where `cases` is **exactly
five objects** in fixed order, each `{label, path, version, version_status}`:

1. `current_v2` — path `/v2<endpoint>`, version `v2`, version_status `current`
2. `deprecated_v1` — path `/v1<endpoint>`, version `v1`, version_status `deprecated`
3. `unsupported_v0` — path `/v0<endpoint>`, version `v0`, version_status `unsupported`
4. `unsupported_v99` — path `/v99<endpoint>`, version `v99`, version_status `unsupported`
5. `unsupported_vbeta` — path `/vbeta<endpoint>`, version `vbeta`, version_status `unsupported`

The agent never sends a request, validates a schema, or states a status/header — a
separate deterministic program does, with read-only GETs + ajv v8.

## Metric

**Headline (QA finding, property of the API):** Version Routing Accuracy =
(versioning scenarios where actual code is correct AND schema validates with zero
errors AND Deprecation presence/absence matches the version's status ÷ total) × 100.
**Pass = 100%.** Against unversioned DummyJSON it is ≈30.77% — a **FAIL**, recorded as
the finding (DummyJSON ships no versioning).

**Leaderboard (test quality, property of the framework):** Version-Routing Test
Fidelity = % of gold (endpoint × scenario) tokens the agent reproduces exactly
(including legitimately-`missing` tokens; an agent that fails to emit a case diverges
on that case's routing/status scenario and is penalised). Ties break lexicographically:
**fidelity ↓ → plan-conformance ↓ → tokens ↑ → elapsed ↑**. Computed by
`judge/validate-api-versioning-behavior/score.py`.

## How to run

```
bash scripts/phase4_versioning_run.sh           # boots target, builds gold, runs 4 agents, scores, leaderboard
# or, deterministic plumbing check (no LLM):
BASE_URL=http://localhost:8899 python data/validate-api-versioning-behavior/build_gold.py
```

## Tooling note (from the build request)

The request named Postman/Newman, REST Assured, ajv v8, and swagger-parser. The
foundry's existing harness substrate is honored: **ajv v8 is used verbatim**
(`tools/ajv/ajv_validate.mjs`, draft-07, strict) for per-version schema validation;
HTTP execution + header assertion are done with the same stdlib read-only-GET harness
every api-tester build uses (Postman/Newman/REST Assured are HTTP+assertion runners
the harness already subsumes); swagger-parser's role (spec parsing + $ref resolution)
is met by the authored `versioning_spec.json` contract + `versioning_spec.schema_for`,
since DummyJSON ships no OpenAPI versioning spec to resolve.
