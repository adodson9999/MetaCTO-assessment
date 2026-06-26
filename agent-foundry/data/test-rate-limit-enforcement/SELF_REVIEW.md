# Self-Review — api-tester / test-rate-limit-enforcement, 2026-06-25

> Phase 6 self-questioning pass. Honest two-axis review, devil's-advocate. Findings
> reported, NOT auto-applied. The user decides what to act on. Coexists with the other
> api-tester builds' SELF_REVIEWs.

## Honest assessment

**Completeness:** ~85%. All six phases ran: task pinned (Phase 2, target/limit/metric
decided with the user), the agent prompt authored line-by-line through the real debate
gate (11 lines, all CONSENSUS), four framework agents built on one shared deterministic
harness, judge metric invented + computed, gold reference built, evolution wired (staged),
this review. **What is NOT done:** a clean four-agent leaderboard run. It is blocked solely
on **Anthropic API credits** — the backend is `claude-haiku` per the user's explicit "no
Ollama" instruction, and the account's balance was exhausted partway through the session
(confirmed: `400 invalid_request_error — credit balance too low`). The deterministic core
is fully validated without the LLM; the agents need credits to elicit their plans.

**Confidence:** High on the plumbing and the target model. The big risk this build carried
— a **wrong Phase-2 premise** — was caught and corrected: the spec assumed "DummyJSON ships
no rate limiter," but it has a real one (`express-rate-limit`, max 100 / 10s, keyed by
`X-Forwarded-For` under trust-proxy, skipped only in `NODE_ENV=development`). The corrected
build tests that real, active limiter (booted `NODE_ENV=production`), and the gold +
single-endpoint harness check both reproduce the full lifecycle **deterministically at
100%** (every endpoint trips at exactly request 101, `Retry-After` present + positive int,
in-window 429, after-window reset → Rate Limit Trigger Precision = PASS). Medium confidence
on *ranking* the four frameworks: the plan is fully pinned by the gated prompt and all four
emitted valid plans in earlier runs, so faithful agents will tie near 100% fidelity; the
metric only separates them when one mis-constructs the burst/probe (which an earlier
mis-extraction in the SDK wrapper, since fixed, demonstrated it does).

## Findings

- **[HIGH → BLOCKING, external] No four-agent run yet — Anthropic credits exhausted.** The
  agents cannot elicit plans without the cloud backend (Ollama is excluded by instruction).
  → **Mitigation:** add credits, then `bash scripts/phase4_ratelimit_run.sh`. Everything
  else is in place; the gold + harness are validated, so a credited run should populate the
  leaderboard directly. (If a quick local sanity run is ever acceptable, flipping
  `config.toml [backend].provider = "ollama"` would let all four run air-gapped — but that
  contradicts the stated constraint, so it is NOT done.)

- **[HIGH → RESOLVED] Wrong target premise.** The signed-off spec assumed DummyJSON had no
  limiter (headline = FAIL/not-enforced). It actually enforces 100/10s, disabled only in
  development mode — exactly how the foundry had been booting it. → **Fixed:** boot
  `NODE_ENV=production` (NODE_ENV does not gate Mongo, so the air-gapped no-Mongo boot
  still works); the phase-4 script now kills any stale instance and asserts `X-RateLimit-*`
  is present before running, so a dev-mode instance can't silently void the test. Spec,
  metric, harness, and gold all corrected to N=100/W=10s. Headline flipped FAIL → PASS.

- **[HIGH → RESOLVED] Probe timing was non-deterministic.** DummyJSON's limiter uses a
  global wall-clock-aligned window and emits a **constant** `Retry-After` (= windowMs/1000),
  not the true time remaining. Timing the within-window probe off `Retry-After` landed it
  after the window had already reset (~20% of the time), so the observed token flipped
  between runs. → **Fixed:** (a) anchor probe timing on `X-RateLimit-Reset` (authoritative
  close); (b) synchronize to a fresh window before each burst; (c) re-burst up to 3× if a
  burst straddles a reset boundary and fails to trip. After these, gold rebuilds at a clean
  **100% / all-101** with no flake. *(That Retry-After ≠ remaining-time is itself recorded
  as a secondary QA finding.)*

- **[MEDIUM → RESOLVED] Claude Agent SDK wrapper dropped the plan.** The SDK returns typed
  message blocks; the wrapper stringified their `repr` instead of extracting `TextBlock.text`,
  so `extract_json` found nothing (0 coverage) the first time the native path ran (the bug
  was latent because pagination only ever used the Ollama path). → **Fixed:** iterate the
  content blocks and collect `.text`; also pass `allowed_tools=[]` so the SDK agent stays a
  pure generator (sandbox parity with the other three). Verified: it then emits a valid plan.

- **[MEDIUM] Held-out is not disjoint from the ranking set.** Evolution's held-out endpoints
  (/users, /recipes) are also scored at rank time, so a SkillOpt edit could tune the very
  items it is graded on. → Carve ranking-only vs evolution-only endpoints. (Same open item
  flagged in the prior builds.)

- **[LOW] "Rate Limit Trigger Precision" is identical for every faithful agent.** By design
  (it is a property of the target — 101/PASS everywhere), so it cannot rank the four; that is
  exactly why the judge ranks on fidelity-to-gold instead. Documented in metric.json.

- **[LOW] The plan's `api_key_value` is decorative on the wire.** The harness sends a
  per-(agent,endpoint) isolated `X-Forwarded-For` for parallel-bucket isolation, overriding
  the plan's echoed value. Observed tokens are bucket-behavior (identical for any private
  bucket), so fidelity is unaffected — but an agent that echoes a wrong key value is not
  penalized. Acceptable given the metric is status-token based; noted for transparency.

## Ambiguities that may have slipped the gate

- L4/L5 pin the burst count to exactly `limit_n` and the over-limit to exactly `1`. Re-read
  adversarially (Ultron: "flood the host"): denied by the exact integer counts. Holds.
- L7 pins the two probe offsets to exactly `-2` and `1`. The *meaning* of "the moment the
  window closes" is resolved by the harness (X-RateLimit-Reset), not the agent — the line is
  single-interpretation for the agent (emit these two offsets); the resolution policy lives
  in deterministic code, not in a gated line. Holds.

## What will break first

- **API credits** — already the binding constraint; nothing runs without them.
- **Heavy parallel contention on the single DummyJSON process.** Four agents firing 100-GET
  bursts plus probes can spike connection resets (-1); mitigated by 5× retry + re-burst, but
  a busier machine could still stretch a burst across a window. The re-burst (3×) is the
  backstop; raise it or serialize agents (max-concurrency 1) if a run shows straddles.
- **Wall-clock cost.** ~25 s/endpoint (window-sync + burst + two timed probes) × 6 endpoints
  ≈ 150 s/agent. Acceptable but the slowest of the api-tester builds.

## Recommended next actions (for the user to decide)

1. **Add Anthropic credits, then `bash scripts/phase4_ratelimit_run.sh`** to produce the
   first valid four-agent leaderboard. Re-run a few times and read best-so-far.
2. Carve a disjoint ranking-vs-held-out endpoint split before relying on the SkillOpt gate.
3. If a credit-free smoke is ever acceptable, temporarily set the backend to Ollama (noting
   it contradicts the "claude only" instruction) to confirm all four agents tie near 100%.
4. Consider serializing the agents (max-concurrency 1) for this task specifically, since the
   real limiter makes the run sensitive to aggregate load in a way the other tasks aren't.
