# Task Spec — API Timeout-Handling Tester

> Position **api-tester**, workflow **test-timeout-handling**. Captured in Phase 2 of
> forge-agents. This is the single task all four agents (LangGraph, CrewAI, Claude Code
> subagent, Claude Agent SDK) implement, and the basis for the judge's numeric metric.
> Coexists with the other api-tester builds (payloads, status, schema, auth, authz,
> pagination).

## The task

Given a **service that calls an upstream** and its documented **upstream-timeout
contract**, the agent produces a **timeout test plan** that, under a 60-second injected
upstream delay, checks every documented endpoint enforces the timeout — returns **504
or 408 within `upstream_timeout_s + buffer_s`** (not an open connection that hangs), with
the **TCP connection closed** and a **safe error body** (a non-empty `message`, no file
path / stack trace / upstream URL) — and then, once the delay is removed, **recovers to
200 in under `restore_max_ms`**.

One service contract in → one structured timeout test plan out → one scored scenario table.

## Phase-2 decisions (user sign-off)

1. **Canonical magnitudes (faithful to the spec example):** `upstream_timeout_s = 10`,
   `buffer_s = 2` → `max_wait_s = 12`, `restore_max_ms = 500`, injected upstream delay
   `= 60s`. A compliant gateway gives up at ~10s, never waiting the 60s out.
2. **Backend = local Ollama** (`config.toml [backend].provider = "ollama"`,
   `qwen2.5:14b-instruct`, air-gapped). Each framework uses its native binding via the
   central `backend_config` (LangGraph→ChatOllama, CrewAI→`ollama/…` LiteLLM,
   claude_sdk/subagent→the Ollama OpenAI-compatible `/v1` endpoint). The Ollama server is
   started **manually** (`ollama serve`), not by the build. _(Initially built on the
   Claude Code account via the `claude` CLI; switched to Ollama on 2026-06-25 — flip
   `provider` back, or `FORGE_PROVIDER=claude-haiku` per-run, to use the cloud backend.)_
3. **Target = a local timeout-gateway fixture, tested as-is, gold = real behavior** —
   the air-gapped Python stand-in for the documented toolchain.

## Target — the local timeout-gateway fixture (read-only, never modified)

`tools/timeout-gateway/gateway.py` is the air-gapped local stand-in for a **WireMock
upstream stub fronted by a Toxiproxy latency toxic**. It fronts a simulated upstream
for the documented endpoints and:

- enforces each service's `upstream_timeout_s`: under a `>timeout` upstream delay a
  **compliant** endpoint returns **504** within `upstream_timeout_s` (≈10s), with body
  `{"message": "Upstream request timed out…"}` and **`Connection: close`**, then a **200
  under 500ms** once the delay is gone;
- has **one deliberately non-compliant endpoint** — `GET /inventory/low-stock` returns
  **500** (not 504/408), **leaks** the upstream URL + a filesystem path + a stack frame
  in the body, and **leaves the connection open** (`Connection: keep-alive`). A real,
  catchable defect (mirrors DummyJSON's lenient pagination in that build).

**Delay injection (the "toxic")** is modeled two ways: a per-request header
`X-Upstream-Delay-Ms` (used by the harness — concurrency-safe, so parallel agents never
corrupt each other), plus the documented `PUT`/`DELETE /__control/toxic` REST lifecycle.
Why a Python fixture, not literal WireMock+Toxiproxy: it keeps the build air-gapped and
deterministic, exactly as DummyJSON stands in for a live API in the pagination build.

## Inputs

- **Contract:** `data/test-timeout-handling/timeout_spec.json` — the service catalogue
  (service name, `upstream_timeout_s`, `buffer_s`, `restore_max_ms`, endpoint list). This
  is what the agents are briefed from. **Compliance flags are not exposed** — whether an
  endpoint actually enforces the timeout is discovered by the harness.
- **Services (3):** `orders-api` (`/orders`, `/orders/recent`), `inventory-api`
  (`/inventory`, `/inventory/low-stock` ← non-compliant), `profile-api` (`/profile`,
  `/profile/preferences`).
- **Target:** the local gateway on `127.0.0.1:8911`.

## What a correct / good agent output looks like

Each agent emits, per service, a single seven-key plan object (the debate-gated "ask"):
`service, upstream_timeout_s, buffer_s, max_wait_s, restore_max_ms, delayed, restore`,
where:

- `max_wait_s` = `upstream_timeout_s + buffer_s` (the agent's one arithmetic step).
- `delayed` and `restore` each = exactly one `{label, method, path}` object **per
  endpoint**, in the brief's order, `method` verbatim-uppercased, `path` verbatim,
  `label` = `"METHOD path"`.

The harness then injects the 60s delay, probes each `delayed` endpoint with a **raw
HTTP/1.1 socket client** (measuring wall-clock latency, parsing the status, and
verifying TCP closure by an actual post-response recv — the netstat-equivalent check),
removes the delay, re-probes each `restore` endpoint, and writes
`results/runs/<run>/<agent>.{json,cases.json}` with the per-(service, scenario) observed
token.

## The metric

Two layers, both numeric and machine-read from `results/`:

1. **Headline (each agent emits): Timeout Enforcement Rate** =
   (endpoints returning 504/408 within `max_wait` **and** with the TCP connection closed
   ÷ endpoints tested under the 60s delay) × 100. A property of the *target gateway*; a
   faithful agent reproduces the gold value (empirically **83.33%** = 5/6 — the
   non-compliant endpoint fails). Pass = 100%; the non-compliant endpoint makes the
   target fail by design, which is the finding.

2. **Judge's rank key — Timeout-Test Fidelity (0–100):** the fraction of gold
   `(service, scenario)` cases where the agent's harness-observed token equals the gold
   token. **Uncovered scenarios score 0.** This rewards the framework that copies the
   contract, computes `max_wait_s` correctly, lists every endpoint once in **both**
   phases with verbatim method/path, and faithfully exercises every scenario. Pass =
   100%; fail = any scenario uncovered or mis-constructed.

> **Why fidelity, not raw enforcement, ranks the agents:** all four drive the same
> gateway under the same delay, so the enforcement rate is a property of the target.
> What differs between frameworks is test fidelity — plan coverage and request-construction.

## Scenario set (39 total — the metric denominator)

Per service: `max_wait_correct` (1). Per endpoint (×6): `delayed_status`,
`delayed_within_max_wait`, `delayed_conn_closed`, `delayed_body_safe`, `restore_status`,
`restore_within_budget`. So 3 + 6×6 = **39**. Defined once in
`agents/common/timeout_spec.py` (shared by gold + harness).

## Ground truth (already built)

`data/test-timeout-handling/gold.json` + `gold/<service>.json` — produced by
`build_gold.py`, the deterministic **reference** (not one of the four agents). It authors
the contract, derives the canonical correct plan, drives it against the live gateway
under the 60s injected delay, and records the **real** observed token per scenario.
Rebuild any time with
`FORGE_TARGET_BASE_URL=http://127.0.0.1:8911 python3 data/test-timeout-handling/build_gold.py`.

**Empirical result:** 3 services · 6 endpoints · 39 scenarios · 36 correct →
**Timeout Enforcement Rate = 83.33%** (5/6 endpoints enforce). The 3 failing scenarios
are all `GET /inventory/low-stock` under delay: `delayed_status` → 500 (not 504/408),
`delayed_conn_closed` → false (connection left open), `delayed_body_safe` → false (leaks
the upstream URL + path + stack). Legitimate QA findings, not agent failures.

## Constraints / invariants

- **Local & air-gapped.** The gateway binds `127.0.0.1`; the harness refuses any non-local
  HTTP host. Model elicitation uses the local Ollama backend (`qwen2.5:14b-instruct`).
- **Gateway is never modified by the agents.** Agents emit plans only; the harness drives
  the probes and the documented toxic lifecycle.
- **Plan generation is model-driven** (each framework elicits the plan) — this is where
  the frameworks differ. **Execution + scoring are deterministic code** (raw-socket
  probes + the shared evaluator).
- **Sandbox:** all agent read/write confined to `agent-foundry/`. Shared EverOS memory
  pool (common `project_id`/`app_id`, per-agent `agent_id`).
- **Implementable in all four frameworks** — plain orchestration (brief → plan), portable.

## Open defaults flagged for sign-off

1. Target = local timeout-gateway as-is, gold = real behavior. Headline enforcement rate
   is 83.33% by design (one non-compliant endpoint), not 100%.
2. Delay injected via a per-request header (concurrency-safe) plus the documented
   `PUT`/`DELETE /__control/toxic` lifecycle; TCP closure verified by a raw-socket recv
   (netstat is the real-world equivalent).
3. Rank key = Timeout-Test Fidelity; headline = Timeout Enforcement Rate.
