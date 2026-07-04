# MetaCTO Assessment — Multi-Agent API Test Orchestration

This repository pairs a real API under test with a multi-agent QA system that tests it end to end.

- **System under test:** [**DummyJSON**](https://github.com/Ovi/DummyJSON) — Muhammad Ovi's free placeholder-JSON REST API. In this repo it runs **locally and air-gapped** (no MongoDB, no external calls) so the agents exercise the actual server code. The original DummyJSON README is preserved below under [System Under Test](#-system-under-test--dummyjson).
- **The test system:** [`agent-foundry/`](agent-foundry/) — **40 API-tester agents + 4 general agents** that generate, execute, adjudicate, and report tests against every DummyJSON endpoint, producing test cases, a Postman collection, and fully-evidenced bug reports.

> **Note:** the target being tested is **DummyJSON**. Everything under `agent-foundry/` is the assessment's own multi-agent test harness, not part of DummyJSON.

---

## The orchestration test

The full run is driven by the **`orchestration-full`** skill (`agent-foundry/scripts/orchestrate_full.py`). It is *unconditional*: **every agent runs on every endpoint** (all 15 OpenAPI paths / 22 method+path combos in `agent-foundry/data/openapi.json`), with no change-detection or scoping.

Per agent, per endpoint, the pipeline is:

1. **Produce** — `test-case-creator` (the sole producer) authors that agent's test cases; the orchestrator freezes them into the registry.
2. **Execute** — the API-tester agent runs each case one at a time against the live local server and records only the observed `actual` evidence.
3. **Adjudicate** — every mismatch is sent to the **`documentation-reviewer`**, which returns one of:
   - `yes` → the docs state the behavior and it differs → a **documented (verified) bug**, cited to the exact doc file/line + public URL;
   - `missing-docs` → undocumented → a categorized, report-only **unverified bug** (never dropped);
   - `no` → the observed behavior matches the docs → the test's expectation is corrected and re-run.
4. **Report** — `bug-reporter` materializes each bug with real reproduction evidence.
5. **Finalize** — deliverables are assembled and **hard guardrails** must pass or the run is marked `BROKEN` (non-zero exit).

**Backend:** in a Claude Code session the agents run on Anthropic Claude (via a local `claude -p` shim); otherwise a local Ollama model. No secrets ever leave the machine.

### Deliverables (per run, under `agent-foundry/results/<date>/<time>/`)

| Folder | Contents |
|--------|----------|
| `TestCases/<agent>/` | `cases.json` + `cases.md` — every agent's generated test cases |
| `Postman/` | one aligned Postman v2.1 collection (`collection.json`) + `environment.json` |
| `BugReport/<agent>/verified_bugs/` | documented bugs (`BUG-*`), each cited to DummyJSON docs |
| `BugReport/unverified/<category>/` | undocumented findings grouped by category (`vulnerability` / `business-workflow` / `computer-software`), report-only |

Every bug ships **real evidence**: a **PNG screenshot** of the reproduced request/response, an **MP4 screen recording** of the reproduction steps, and (best-effort) the **target server's own request log** for that call.

### Hard guardrails

The finalizer enforces a set of `hard` gates; any failure marks the run `BROKEN`:

- **G13** results layout · **G20** TestCases/Postman/BugReport separation · **G22** no index files under `BugReport/`
- **G24** evidence authenticity (real PNG + watchable MP4 + server-origin logs)
- **G25** unverified-bug layout (all under `BugReport/unverified/{category}/`, category-consistent, co-located artifacts)

### Running it

```bash
# 1. Start the target DummyJSON server locally (air-gapped). Add LOG_ENABLED=true to capture
#    server-side logs for bug evidence.
JWT_SECRET=dev MONGODB_URI= NODE_ENV=development PORT=8899 LOG_ENABLED=true node index.js

# 2. Run the full orchestration (all 44 agents × every endpoint)
FORGE_WORKSPACE="$(pwd)/agent-foundry" FORGE_TARGET_BASE_URL="http://localhost:8899" \
  agent-foundry/.venv/bin/python agent-foundry/scripts/orchestrate_full.py RUN-$(date -u +%Y%m%d-%H%M%S)
```

---

## The agents

Each agent is authored in **four frameworks in parallel** (LangGraph, CrewAI, a Claude Code subagent, and the Claude Agent SDK) and scored by a judge; the winning implementation runs in orchestration. Agents live under `agent-foundry/agents/`.

### 40 API-tester agents (`agent-foundry/agents/api-tester/`)

`validate-request-payloads` · `verify-response-status-codes` · `test-authentication-flows` · `check-authorization-rules` · `validate-json-schema-responses` · `test-pagination-behavior` · `verify-error-message-clarity` · `test-rate-limit-enforcement` · `validate-query-parameter-handling` · `test-idempotency-of-endpoints` · `verify-content-type-negotiation` · `validate-null-empty-fields` · `test-timeout-handling` · `verify-crud-operation-integrity` · `test-concurrent-request-handling` · `validate-header-propagation` · `test-webhook-delivery` · `run-regression-suite` · `track-defect-density` · `validate-api-versioning-behavior` · `test-ssl-tls-enforcement` · `verify-caching-headers` · `validate-correlation-id-propagation` · `test-bulk-operation-endpoints` · `verify-audit-log-generation` · `validate-search-and-filter-queries` · `test-file-upload-and-download` · `verify-sorting-behavior` · `test-event-driven-api-triggers` · `test-ip-allowlist-enforcement` · `test-api-gateway-routing` · `verify-third-party-oauth-integration` · `test-multipart-form-data-handling` · `validate-retry-after-header-compliance` · `test-soft-delete-behavior` · `validate-graphql-depth-limits` · `test-long-polling-support` · `verify-enum-value-restrictions` · `measure-api-consumer-satisfaction` · `create-postman-collection`

### 4 general agents (`agent-foundry/agents/general/`)

| Agent | Role |
|-------|------|
| `test-case-creator` | Sole **producer** of test cases; runs first for every agent+endpoint. |
| `documentation-reviewer` | Sole **doc adjudicator**; judges every mismatch `yes` / `no` / `missing-docs`. |
| `run-cicd-pipeline` | Proposes the CI regression suite (excludes report-only unverified cases). |
| `bug-reporter` | Sole **writer** of bug reports (verified + unverified) with full evidence. |

### How the agents are built and evolved

Agents aren't hand-written once. They're produced by the **`forge-agents`** pipeline: each agent is built in four frameworks in parallel, every instruction line passes an adversarial debate gate, and each implementation **self-improves across a 10-round keep-if-improved tournament** against a judge agent that scores them on a hard numeric metric. Per-agent evolvers live in `agent-foundry/evolvers/` (`evolve_*.py`), and three vendored subsystems (`agent-foundry/vendor/`) drive the self-evolution and shared memory:

| Subsystem | Role |
|-----------|------|
| **EverOS** | Local, air-gapped shared-memory pool (Markdown + SQLite + LanceDB); lets the four framework agents share knowledge yet stay individually scoped. Store lives at `agent-foundry/memory/.everos/`. |
| **SkillOpt** | Per-agent, validation-gated skill optimization — "train skills like neural nets" (epochs/batches/validation) without touching model weights. |
| **SkillClaw** | Collective, cross-agent skill evolution and sharing (`agent-foundry/memory/skillclaw-share/`). |

---

## GitHub sources & credits

**System under test**
- [Ovi/DummyJSON](https://github.com/Ovi/DummyJSON) — the DummyJSON REST API (Muhammad Ovi), run locally as the target.

**Agent frameworks** (each agent is implemented in all four)
- [langchain-ai/langgraph](https://github.com/langchain-ai/langgraph) — LangGraph
- [crewAIInc/crewAI](https://github.com/crewAIInc/crewAI) — CrewAI
- [anthropics/claude-agent-sdk-python](https://github.com/anthropics/claude-agent-sdk-python) — Claude Agent SDK
- [anthropics/claude-code](https://github.com/anthropics/claude-code) — Claude Code (subagents; also the harness runtime)

**Agent self-evolution & shared memory** (vendored under `agent-foundry/vendor/`)
- [EverMind-AI/EverOS](https://github.com/EverMind-AI/EverOS) — local shared-memory pool for the agents
- [microsoft/SkillOpt](https://github.com/microsoft/SkillOpt) — per-agent, validation-gated skill optimization
- [AMAP-ML/SkillClaw](https://github.com/AMAP-ML/SkillClaw) — collective cross-agent skill evolution & sharing

**Harness tooling** (used to build/run `agent-foundry/`)
- [mvanhorn/cli-printing-press](https://github.com/mvanhorn/cli-printing-press) — generated the `CLI/dummyjson-pp-cli` endpoint CLI
- [Egonex-AI/Understand-Anything](https://github.com/Egonex-AI/Understand-Anything) — produced `.understand-anything/knowledge-graph.json` (required by the orchestration)
- [yamadashy/repomix](https://github.com/yamadashy/repomix) — codebase packing for analysis
- [affaan-m/ECC](https://github.com/affaan-m/ECC) — agent-harness skills/rules

**Evidence capture**
- [python-pillow/Pillow](https://github.com/python-pillow/Pillow) — renders the PNG screenshots and MP4 frames
- [FFmpeg/FFmpeg](https://github.com/FFmpeg/FFmpeg) — encodes the MP4 reproduction recordings

DummyJSON's own server dependencies (Express, jsonwebtoken, Mongoose, etc.) are listed in [`package.json`](package.json).

---

## 📚 System Under Test — DummyJSON

*The remainder of this document is DummyJSON's own README, describing the API these agents test.*

[![Uptime Robot status](https://img.shields.io/uptimerobot/status/m793802954-7f701e85a9b8891f77662c72?label=json-server&style=for-the-badge&)](https://dummyjson.com/test)

# DummyJSON

[DummyJSON](https://dummyjson.com) is a free REST API for generating placeholder JSON data — no setup, no auth, just use it.

📘 Docs: [https://dummyjson.com/docs](https://dummyjson.com/docs)

**New**: Now you can generate your own [custom responses](https://dummyjson.com/custom-response) from DummyJSON, [try it now!](https://dummyjson.com/custom-response)

## Why DummyJSON?

* Skip building a backend just to test UI
* Avoid unreliable or rate-limited public APIs
* Get consistent, structured data instantly
* No configuration required
* Works with any framework
* Supports all HTTP methods
* Great for prototyping, testing, and learning

## How to Fetch Data

Use any method you prefer - fetch API, Axios, jQuery AJAX - it all works seamlessly.

Example:

```js
const res = await fetch('https://dummyjson.com/products');
const json = await res.json();
console.log(json);
```

OR

```js
const response = await axios.get('https://dummyjson.com/products');
console.log(response.data);
```

P.S.: Pagination is supported.

## Resources

* [Products (190+)](https://dummyjson.com/docs/products)
* [Users (200+)](https://dummyjson.com/docs/users)
* [Carts (200+)](https://dummyjson.com/docs/carts)
* [Posts (250+)](https://dummyjson.com/docs/posts)
* [Comments (340+)](https://dummyjson.com/docs/comments)
* [Quotes (1400+)](https://dummyjson.com/docs/quotes)
* [Recipes (50+)](https://dummyjson.com/docs/recipes)
* [Todos (250+)](https://dummyjson.com/docs/todos)
* [Auth](https://dummyjson.com/docs/auth)
* [Custom HTTP Response](https://dummyjson.com/custom-response)
* [Dummy Image Generator](https://dummyjson.com/docs/image)
* [Generate Identicon](https://dummyjson.com/docs/image#image-identicon)
* [Mock HTTP Response](https://dummyjson.com/docs/http)

## Features

* Filtering & search
  [https://dummyjson.com/products/search?q=phone](https://dummyjson.com/products/search?q=phone)

* Pagination
  [https://dummyjson.com/products?limit=10&skip=10](https://dummyjson.com/products?limit=10&skip=10)

* Nested resources
  [https://dummyjson.com/users/1/posts](https://dummyjson.com/users/1/posts)

* Delay responses
  [https://dummyjson.com/products?delay=1000](https://dummyjson.com/products?delay=1000)

---

# Generate identicon

https://dummyjson.com/icon/HASH/SIZE

Example: https://dummyjson.com/icon/abc123/150

![Example](https://dummyjson.com/icon/abc123/150)

---

# Dummy Image Generator

Dummy Image Generator is a simple Node.js service for generating placeholder images with customizable options.

## Usage

You can use the service by making HTTP requests to the following URL:

https://dummyjson.com/image

### Examples

https://dummyjson.com/image/200

![Example](https://dummyjson.com/image/200)

https://dummyjson.com/image/300/da5047/030104?text=Hello+Peter&fontFamily=cookie&fontSize=36

![Example](https://dummyjson.com/image/300/da5047/030104?text=Hello+Peter&fontFamily=cookie&fontSize=36)

## Supported Fonts

- Bitter
- Cairo
- Comfortaa
- Cookie
- Dosis
- Gotham
- Lobster
- Marhey
- Pacifico
- Poppins
- Quicksand
- Qwigley
- Satisfy
- Ubuntu

---

## Contributors

<a href="https://github.com/Ovi/DummyJSON/graphs/contributors">
  <img src="https://contrib.rocks/image?repo=Ovi/DummyJSON" />
</a>

---

## License

MIT
