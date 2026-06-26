# Task Spec — API Rate-Limit-Enforcement Tester

> Position **api-tester**, workflow **test-rate-limit-enforcement**. Captured in Phase 2
> of forge-agents. This is the single task all four agents (LangGraph, CrewAI,
> Claude Code subagent, Claude Agent SDK) implement, and the basis for the judge's
> numeric metric. Coexists with the prior api-tester builds (validate-request-payloads,
> verify-response-status-codes, test-authentication-flows, check-authorization-rules,
> validate-json-schema-responses, test-pagination-behavior).

> **⚠ Phase-3 correction (supersedes the original Phase-2 premise).** The signed-off spec
> assumed "DummyJSON ships no rate limiter," so the headline would be FAIL/not-enforced.
> That was **factually wrong**: DummyJSON has a **real** limiter (`src/middleware/
> rate-limiter.js`, express-rate-limit) — **max 100 requests / 10s window per client key**,
> keyed by `X-Forwarded-For` (because `app.set('trust proxy', true)`), and **skipped only
> when `NODE_ENV === 'development'`** (which is how the foundry had been booting it). Booting
> the target `NODE_ENV=production` activates it (NODE_ENV does **not** gate Mongo, so the
> air-gapped no-Mongo boot still works). Empirically the limiter **correctly enforces** the
> contract — first 429 on exactly request 101 with `Retry-After`. So this build tests a
> **real, active, correctly-behaving limiter**, and the headline flips from FAIL to **PASS**.
> The contract values below are DummyJSON's REAL ones (N=100, W=10s), not the placeholder
> 10/5 from the original sign-off.

## The task

Given a **running endpoint** and a documented **rate-limit contract** (`N` requests per
`W`-second window per API key), the agent produces a **rate-limit test plan** that:

- fires exactly `N` requests inside the window (the at-limit burst),
- fires one more request immediately (request `N+1`, the over-limit probe),
- inspects the over-limit response for a `429` status and a `Retry-After` header,
- probes once **before** the advertised window closes (expected: still limited),
- probes once **after** the window closes (expected: limit cleared).

A deterministic harness executes the plan with **read-only GET requests** and records,
per scenario, whether the API:

- returns a non-`429` code for every request at or below the limit,
- returns exactly `429` on the first request **above** the limit,
- includes a `Retry-After` header on that `429` whose value is a **positive integer**,
- still returns `429` for a request sent **before** the `Retry-After` window elapses,
- returns a non-`429` code for a request sent **after** the `Retry-After` window elapses.

One endpoint contract in → one structured rate-limit test plan out → one scored
scenario table.

## Target — DummyJSON, tested AS-IS (read-only, never modified)

Per the philosophy of every prior api-tester build (**DummyJSON as-is, gold = real
behavior**): the agents test the local DummyJSON unchanged. DummyJSON's **real** limiter
(`src/middleware/rate-limiter.js`, express-rate-limit) defines its observed contract:

- **N = 100 requests per W = 10-second window** (`max: 100`, `windowMs: 10000`).
- **Keyed by client IP**, and because `app.set('trust proxy', true)`, the key is taken
  from the **`X-Forwarded-For`** header — so a distinct XFF value gets its own 100/10s
  bucket. This is the "per API key" dimension, realized as a per-client-key bucket.
- **Skipped when `NODE_ENV === 'development'`.** The foundry therefore boots the target
  **`NODE_ENV=production`** to exercise the limiter. `NODE_ENV` does not gate Mongo
  (`connectDB()` returns early on empty `MONGODB_URI`), so the air-gapped no-Mongo boot
  is unaffected. The phase-4 script kills any stale instance and verifies `X-RateLimit-*`
  headers are present before running — a dev-mode instance would silently disable the test.
- **Window is global + wall-clock-aligned** (express-rate-limit MemoryStore): all keys
  share the same reset boundary, and `Retry-After` is a **constant** `windowMs/1000` (10),
  NOT the true time remaining — `X-RateLimit-Reset` (epoch) is the authoritative close.
  *(This Retry-After-is-constant behavior is itself a recorded QA finding.)*

**Empirically the limiter correctly enforces the contract:** requests 1..100 → `200`,
request 101 → `429` with `Retry-After: 10`, an in-window probe stays `429`, an
after-window probe resets to `200`. So the genuine QA finding is **"rate limit correctly
enforced; first 429 on exactly request 101 (PASS)"** — not a violation.

**All HTTP is GET only** — no POST/PUT/PATCH/DELETE against the target. Firing `N+1`
read-only GETs does not modify DummyJSON.

**Determinism wiring (harness + gold, identical):** (1) each `(agent, endpoint)` uses an
isolated synthetic `X-Forwarded-For` IP so the four agents never share a bucket when run
in parallel; (2) before each burst the harness **synchronizes to a fresh window** (prime
→ read `X-RateLimit-Reset` → wait to the boundary) so there is always a full window to
place the `−2s` probe; (3) probe timing is anchored on `X-RateLimit-Reset`, not the
constant `Retry-After`. Together these make every observed token reproducible between gold
and agents, so fidelity reflects plan quality, not timing luck.

## Inputs

- **Contract:** `data/test-rate-limit-enforcement/ratelimit_spec.json` — the endpoint
  catalogue + the documented limit (`limit_n=100`, `window_seconds=10`,
  `api_key_header="X-Forwarded-For"`, success code, the `Retry-After` header name). This is
  what the agents are briefed from.
- **Endpoints (6):** `/products`, `/posts`, `/comments`, `/todos`, `/users`, `/recipes`
  — each is an **independent rate-limit subject** exercised under its own isolated client
  key (X-Forwarded-For), so each gets a full 100/10s budget. The window reset is realized by
  per-(agent,endpoint) bucket isolation + per-burst window synchronization (no fixed wait).
- **Target API:** local DummyJSON on `:8899`, booted air-gapped (no Mongo) with the limiter
  ACTIVE:
  `JWT_SECRET=forge_test_secret MONGODB_URI= NODE_ENV=production PORT=8899 LOG_ENABLED=false node index.js`.

## What a correct / good agent output looks like

Each agent emits, per endpoint, a single fixed-key plan object (the debate-gated "ask"):
`endpoint, method, success_code, limit_n, window_seconds, api_key_header, api_key_value,
retry_after_header, at_limit, over_limit, probes`, where:

- `method` is the literal string `"GET"` and `success_code` is the integer `200`.
- `at_limit` = one object `{label:"at_limit", count: limit_n}` — the burst of exactly `N`
  requests fired inside the window.
- `over_limit` = one object `{label:"over_limit", count: 1}` — the single request `N+1`.
- `probes` = exactly two objects, in order:
  - `{label:"within_window", offset_seconds: -2}` — sent at `(window close − 2 s)`.
  - `{label:"after_window",  offset_seconds: +1}` — sent at `(window close + 1 s)`.
  - The harness resolves "window close" from `X-RateLimit-Reset` (authoritative), falling
    back to `Retry-After` then `W`. Offsets are seconds relative to that close.

The agent **never** sends requests, parses headers, or guesses status codes — it only
emits the plan. The harness then writes `results/runs/<run>/<agent>.{json,cases.json}`
with the per-(endpoint, scenario) **observed token** from the real read-only requests.

## The metric

Two layers, both numeric and machine-read from `results/`:

1. **Headline (each agent emits): Rate Limit Trigger Precision** = the **ordinal number of
   the request on which the first `429` is returned**, per endpoint (an integer, or the
   sentinel `none` when no `429` occurs). Pass = the first `429` occurs on **exactly**
   request `N+1` (= 101). This is the metric the user defined verbatim. It is a property of
   the *target API*; a faithful agent reproduces the gold value. Against DummyJSON's real,
   active limiter the ordinal is **`101` on every endpoint → PASS** (the documented limit is
   correctly enforced) — the task's QA finding.

2. **Judge's rank key — Rate-Limit-Test Fidelity (0–100):** the fraction of gold
   `(endpoint, scenario)` cases where the agent's harness-observed token equals the gold
   token. **Uncovered scenarios score 0.** This rewards the framework that builds the
   correct request sequence (exactly `N=100` at-limit requests, the single `N+1=101`
   over-limit request, the `Retry-After` inspection, and the two correctly-timed window
   probes) and faithfully exercises every scenario. Pass = 100%; fail = any scenario
   uncovered or mis-constructed.

> **Why fidelity, not raw precision, ranks the agents:** all four exercise the same limiter,
> each under its own isolated client-key bucket, so the raw Rate Limit Trigger Precision is
> identical (`101` everywhere → PASS) — a property of the target, not the agent. What differs
> between frameworks is test fidelity: plan coverage and request-sequence construction
> quality. The headline Trigger Precision is still emitted by every agent as the QA finding.

## Scenario set (8 per endpoint — the metric denominator)

Defined once in `agents/common/ratelimit_spec.py` (shared by gold + harness). Each carries
the idealized `ideal` token under the documented `N=100 / W=10s` contract; the gold records
DummyJSON's **real** token (which, for the correctly-enforcing limiter, matches the ideal).

| # | scenario | ideal token | meaning |
|---|----------|-------------|---------|
| 1 | `at_limit_all_non_429`    | `true`  | all `N` at-limit requests return non-`429` |
| 2 | `over_limit_status`       | `429`   | request `N+1` returns exactly `429` |
| 3 | `first_429_ordinal`       | `101`   | ordinal of the first `429` (= `N+1`) |
| 4 | `trigger_precision_exact` | `true`  | first `429` occurs on exactly request `N+1` |
| 5 | `retry_after_present`     | `true`  | the `429` carries a `Retry-After` header |
| 6 | `retry_after_positive_int`| `true`  | that `Retry-After` value is a positive integer |
| 7 | `within_window_still_429` | `429`   | probe at `(window close − 2 s)` is still `429` |
| 8 | `after_window_non_429`    | `true`  | probe at `(window close + 1 s)` is non-`429` |

`6 endpoints × 8 scenarios = 48` total scenarios = the fidelity denominator.

## Ground truth (built in Phase 4)

`data/test-rate-limit-enforcement/gold.json` + `gold/<endpoint>.json` — produced by
`build_gold.py`, the deterministic **reference** (not one of the four agents). It authors
the contract, derives the canonical correct plan, sends every read-only request to the
live API at real wall-clock timing, and records the **real** observed token per scenario.
Rebuild any time with
`BASE_URL=http://localhost:8899 python3 data/test-rate-limit-enforcement/build_gold.py`.

**Expected empirical result** (DummyJSON, real limiter `N=100 / W=10s`, `NODE_ENV=production`):
for every endpoint — `first_429_ordinal = 101`, so **Rate Limit Trigger Precision = PASS**
on all 6. All 8 scenarios match the ideal (100 non-429, request 101 → 429, `Retry-After`
present + positive int, in-window probe 429, after-window probe non-429). Per-endpoint
correctness = `8/8 = 100%`; headline finding: **the documented rate limit IS correctly
enforced; first 429 on exactly request 101.** A secondary recorded finding: DummyJSON's
`Retry-After` is a constant `windowMs/1000` (10), not the true time remaining — accurate
within-window timing requires `X-RateLimit-Reset`.

## Constraints / invariants

- **Backend = Claude, not Ollama** (per the user's explicit instruction for this task).
  `config.toml [backend].provider = "claude-haiku"` (`claude-haiku-4-5`). This is a cloud
  backend; the user has explicitly opted in (skill invariant 5). All other I/O stays local
  and air-gapped: the target API is local, memory is local EverOS, evolvers are local.
- **DummyJSON is never modified.** Read-only GET only; no seeding, no writes, no auth
  mutation. Firing `N+1` GETs in a loop does not change the target.
- **Plan generation is LLM-driven** (each framework's LLM builds the plan from the brief)
  — this is where the frameworks differ. **Execution, timing, and scoring are deterministic
  code** (the harness fires the read-only GETs at real wall-clock offsets, parses
  `Retry-After`, and records the real responses + ordinals).
- **Timing is real but bounded.** Each endpoint = window-sync wait (≤ `W=10s`) + a ~100-GET
  burst (~0.3s) + the within probe (~`W−2s`) + the after probe (~`W+1s`) ≈ `~25s`; six
  endpoints ≈ `~150s` per agent (agents run in parallel in Phase 4, each on isolated buckets).
- **Sandbox:** all agent read/write/exec confined to `agent-foundry/` (plus read-only HTTP
  to the local target). Shared EverOS memory pool (common `project_id`/`app_id`, per-agent
  `agent_id`).
- **Implementable in all four frameworks** — plain orchestration (brief → plan), portable.

## Decisions of record (post-correction)

1. **Target = DummyJSON as-is, gold = real behavior** — consistent with every prior build.
   The Phase-3 finding that DummyJSON HAS a real limiter (100/10s, `X-Forwarded-For`-keyed,
   dev-skipped) flips the headline to **PASS / correctly enforced**, and the build now tests
   that real, active limiter rather than a non-existent one.
2. **Documented contract = `N=100` requests per `W=10s` window per client key** — DummyJSON's
   REAL values (`express-rate-limit max:100, windowMs:10000`), not the placeholder `10/5`.
3. **6 endpoints, each an independent rate-limit subject** with its own isolated client-key
   bucket; window reset via bucket isolation + per-burst window synchronization.
4. **Metric:** rank key = Rate-Limit-Test Fidelity (0–100); headline = Rate Limit Trigger
   Precision (ordinal of the first `429`, pass iff `= N+1 = 101`). Empirically PASS.
5. **Backend = `claude-haiku`** (not Ollama) per your instruction — flips
   `config.toml [backend].provider`; this is the one non-air-gapped element and is opt-in.
6. **Target boot = `NODE_ENV=production`** so the limiter is active (it is skipped in
   development). The phase-4 script kills any stale instance and asserts `X-RateLimit-*` is
   present before running.
