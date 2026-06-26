# Task Spec — API SSL/TLS-Enforcement Tester

> Position **api-tester**, workflow **test-ssl-tls-enforcement**. Captured in Phase 2 of
> forge-agents. This is the single task all four agents (LangGraph, CrewAI, Claude Code
> subagent, Claude Agent SDK) implement, and the basis for the judge's numeric metric.
> Coexists with the prior api-tester builds (validate-request-payloads,
> verify-response-status-codes, test-authentication-flows, check-authorization-rules,
> validate-json-schema-responses, test-pagination-behavior, validate-query-parameter-handling,
> test-rate-limit-enforcement, test-idempotency-of-endpoints, …).

## The task

Given a **TLS-enforcing endpoint** and a documented **TLS-enforcement contract**, the agent
produces a **TLS test plan** that:

- probes **plain HTTP** (must be refused or redirected to HTTPS, returning no API data),
- probes **TLS 1.0** and **TLS 1.1** (must be refused),
- probes **TLS 1.2** and **TLS 1.3** (must be accepted and serve the endpoint),
- asserts the **certificate** is non-expired, CN/SAN-matched to the host, chain-of-trust ok,
  and not self-signed,
- forbids the weak cipher families **RC4, DES, 3DES, EXPORT, NULL**.

A deterministic harness executes the plan with **TLS handshakes and read-only GET requests**
(openssl + curl + Python ssl as the primary, testssl.sh + sslyze as recorded enrichment) and
records, per scenario, the real observed token. One target contract in → one structured TLS
test plan out → one scored 17-scenario table.

## Target — a LOCAL TLS fixture in front of UNMODIFIED DummyJSON (read-only)

Per the Phase-2 decision and the user's explicit constraints — **do not use the public
`https://dummyjson.com`, and do not modify the DummyJSON app itself** — SSL/TLS enforcement is
tested against a local, air-gapped **TLS fixture** that stands *in front of* the untouched
DummyJSON:

- `data/test-ssl-tls-enforcement/tls_fixture.py` generates a private mini-CA + a leaf cert
  (CN=`localhost`, SAN `localhost`/`dummyjson.local`/`127.0.0.1`, non-expired, CA-signed),
  terminates TLS on `:9443` accepting **only TLS 1.2/1.3** with **strong-only ciphers**,
  forwards each request to DummyJSON (`:8899`) with a **read-only GET**, and runs an HTTP
  listener on `:9080` that **301-redirects to HTTPS** and returns no API data.
- DummyJSON itself is plain HTTP and is **never touched**; the fixture supplies the TLS
  surface under test (a TLS terminator is a normal part of a real deployment).

This makes SSL/TLS enforcement genuinely testable locally and air-gapped. The harness trusts
the fixture's own `ca.pem` as its CA bundle, so chain-of-trust verifies against a real CA the
fixture controls (issuer ≠ subject → not self-signed).

**All probing is handshake + GET only** — no POST/PUT/PATCH/DELETE reaches the target; the
fixture's proxy rejects any non-GET method, so nothing mutates DummyJSON.

## Inputs

- **Contract:** `data/test-ssl-tls-enforcement/tls_spec.json` — the target (host, tls_port,
  http_port, endpoint_path, ca_bundle) + `documented_min_tls`. This is what the agents are
  briefed from.
- **Target:** the local TLS fixture `https://localhost:9443` (+ `http://localhost:9080`) →
  upstream DummyJSON `http://localhost:8899`. Start with
  `python3 data/test-ssl-tls-enforcement/tls_fixture.py start`.

## What a correct / good agent output looks like

Each agent emits a single fixed-key plan object (the debate-gated "ask"): `target_host`,
`target_port`, `http_port`, `endpoint_path`, `protocol_probes`, `certificate_assertions`,
`forbidden_weak_ciphers`, where:

- `protocol_probes` = exactly five objects in order — `plain_http`/http/none/**reject**,
  `tls1_0`/https/tls1/**reject**, `tls1_1`/https/tls1_1/**reject**,
  `tls1_2`/https/tls1_2/**accept**, `tls1_3`/https/tls1_3/**accept**.
- `certificate_assertions` = exactly `["not_expired","cn_or_san_match","chain_of_trust_ok","not_self_signed"]`.
- `forbidden_weak_ciphers` = exactly `["RC4","DES","3DES","EXPORT","NULL"]`.

The agent **never** opens a connection, runs openssl/curl, or guesses a result — it only emits
the plan. The harness then writes `results/runs/<run>/<agent>.{json,cases.json}` with the
per-scenario **observed token** from the real handshakes + read-only GETs.

## The metric

Two layers, both numeric and machine-read from `results/`:

1. **Headline (each agent emits): TLS Enforcement Rate** = (TLS test cases returning the
   correct accept/reject result ÷ total TLS test cases) × 100, over the 17 scenarios. Pass =
   100%. Critical (P1) fail on any one of: a successful TLS 1.0/1.1 handshake, any API data
   over plain HTTP, an expired or self-signed cert, a failed chain of trust, or any weak
   cipher (RC4/DES/3DES/EXPORT/NULL) offered. This is the metric the user defined verbatim.
   It is a property of the *target*; a faithful agent reproduces the gold value. Against the
   correctly-configured fixture the rate is **100%** — a clean positive finding.

2. **Judge's rank key — TLS-Test Fidelity (0–100):** the fraction of gold scenarios where the
   agent's harness-observed token equals the gold token. **Uncovered scenarios score 0.** This
   rewards the framework that builds the complete, correct seven-key plan (all five protocol
   probes with the right expected accept/reject, all four cert assertions, all five forbidden
   weak-cipher families) so the harness exercises every scenario. Pass = 100%.

> **Why fidelity, not raw enforcement rate, ranks the agents:** all four probe the same
> fixture, so the raw TLS Enforcement Rate is identical (a property of the target). What
> differs between frameworks is test fidelity: plan completeness and correct probe
> construction. The headline TLS Enforcement Rate is still emitted by every agent as the
> task's QA finding.

## Scenario set (17 — the metric denominator)

Defined once in `agents/common/tls_spec.py` (shared by gold + harness):

| # | scenario | ideal | meaning |
|---|----------|-------|---------|
| 1 | `plain_http_refused_or_redirected` | `true` | plain HTTP 301-redirects (or is refused), not 200-with-data |
| 2 | `plain_http_zero_api_data` | `true` | no JSON body returned over the plaintext channel |
| 3 | `tls1_0_refused` | `refused` | TLS 1.0 handshake fails |
| 4 | `tls1_1_refused` | `refused` | TLS 1.1 handshake fails |
| 5 | `tls1_2_accepted` | `accepted` | TLS 1.2 handshake succeeds |
| 6 | `tls1_3_accepted` | `accepted` | TLS 1.3 handshake succeeds |
| 7 | `tls1_2_http_200` | `200` | GET over TLS 1.2 returns 200 |
| 8 | `tls1_3_http_200` | `200` | GET over TLS 1.3 returns 200 |
| 9 | `cert_not_expired` | `true` | notAfter is in the future |
| 10 | `cert_cn_or_san_match` | `true` | CN or a SAN entry matches the host |
| 11 | `cert_chain_of_trust_ok` | `true` | chain verifies against the trusted CA bundle |
| 12 | `cert_not_self_signed` | `true` | issuer ≠ subject (CA-signed) |
| 13 | `no_weak_cipher_rc4` | `true` | RC4 not offered |
| 14 | `no_weak_cipher_des` | `true` | DES not offered |
| 15 | `no_weak_cipher_3des` | `true` | 3DES not offered |
| 16 | `no_weak_cipher_export` | `true` | EXPORT not offered |
| 17 | `no_weak_cipher_null` | `true` | NULL not offered |

## Ground truth (built in Phase 4)

`data/test-ssl-tls-enforcement/gold.json` + `gold/target.json` — produced by `build_gold.py`,
the deterministic **reference** (not one of the four agents). It derives the canonical correct
plan, runs every probe through the SAME shared harness, and records the **real** observed token
per scenario. Rebuild with `python3 data/test-ssl-tls-enforcement/build_gold.py` (fixture up).

**Empirical result** (the local fixture): every scenario meets the idealized contract →
**TLS Enforcement Rate = 100%** on all 17. This is the opposite of the rate-limit / idempotency
findings (where DummyJSON *failed* its idealized contract): a correctly-configured TLS deployment
*passes* enforcement, and the test confirms it.

## Constraints / invariants

- **Backend = Claude, not Ollama** (per the user's explicit instruction). `config.toml
  [backend].provider = "claude-haiku"` (`claude-haiku-4-5`); LangGraph + CrewAI reach it
  natively (Anthropic SDK), claude_sdk + the subagent through the documented OpenAI-compatible
  LiteLLM shim used **in-process** (`litellm.completion`, no proxy server). This is a cloud
  backend; the user has explicitly opted in (skill invariant 5).
- **Network egress = the one local fixture only.** The harness allowlists exactly
  `localhost`/`127.0.0.1`/`dummyjson.local` and refuses any other host. No public host is
  contacted; the LLM backend is the only cloud element. testssl.sh and sslyze probe only the
  local fixture.
- **DummyJSON is never modified.** Handshake + read-only GET only; the fixture's proxy rejects
  every non-GET method.
- **Plan generation is LLM-driven** (each framework's LLM builds the plan from the brief) —
  this is where the frameworks differ. **Execution and scoring are deterministic code** (the
  harness runs the handshakes/GETs and records the real results).
- **Tooling:** openssl + curl + Python `ssl` are the deterministic primary (always present);
  testssl.sh (Homebrew) and sslyze (pipx) are installed per the user's request and run once per
  run for recorded enrichment / server-side cross-check. macOS has no GNU `timeout`, so testssl
  is driven via sockets (its own scan timing) and all commands are bounded by Python subprocess
  timeouts.
- **Sandbox:** all agent read/write/exec confined to `agent-foundry/` (plus handshake + read-only
  GET to the local fixture). Shared EverOS memory pool (common `project_id`/`app_id`, per-agent
  `agent_id`).

## Open defaults flagged for sign-off

1. **Target = a local TLS fixture in front of unmodified DummyJSON** (your Phase-2 choice: not
   the public dummyjson.com, do not touch DummyJSON). The fixture enforces TLS correctly →
   Enforcement Rate 100%, a positive finding.
2. **Metric:** rank key = TLS-Test Fidelity (0–100); headline = TLS Enforcement Rate (verbatim
   user formula; P1 fail on any insecure result).
3. **Backend = `claude-haiku`** (not Ollama) per your instruction — the one non-air-gapped
   element, opt-in.
4. **testssl.sh + sslyze installed and used** (per your instruction) as enrichment over the
   openssl/curl/Python-ssl deterministic core.
