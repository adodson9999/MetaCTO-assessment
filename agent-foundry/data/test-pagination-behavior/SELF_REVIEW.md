# Self-Review — api-tester / test-pagination-behavior, 2026-06-25

> Phase 6 self-questioning pass. Honest two-axis review, devil's-advocate. Findings
> reported, NOT auto-applied. The user decides what to act on. Coexists with the
> validate-request-payloads build's own SELF_REVIEW at the workspace root.

## Honest assessment

**Completeness:** ~90%. All six phases ran: task pinned (Phase 2, target decided with
the user), the agent prompt authored line-by-line through the real debate gate
(11 lines, all CONSENSUS), four framework agents built on one shared deterministic
harness, judge metric invented + computed, four agents run in parallel against the
live target read-only, leaderboard written, evolution wired (staged), this review.
The deterministic core is validated (reference plan → 100% fidelity; smoke → 3/4
frameworks perfect). Missing: a disjoint held-out/ranking split (the held-out
collections /users,/recipes are also in the ranking set), and the agents have only
been exercised on the Ollama backend.

**Confidence:** High on the plumbing (gold builder, harness, scorer, leaderboard all
verified end-to-end; the math checks — reference plan scores exactly 100%, and the clean
run-2 scored all four agents 100% / 108-of-108). Medium on *separating* the four
frameworks on this task: with the page math fully pinned by the gated prompt and the
target lenient, all four reach the ceiling, so a single easy run produces a tie. The
metric discriminates when an agent's plan diverges (run-1's flake dropped two agents
to 83.33% / 66.67%); to rank the frameworks on skill, harder collections or a stricter
target would be needed. Local-model JSON-mode variance still adds per-run noise.

## Findings

- **[HIGH → RESOLVED] Transient target flake corrupts a whole collection.** In run-1,
  claude_sdk and the subagent emitted *correct* /products (and /posts) plans, but every
  request returned status -1 (connection failure) for that collection, scoring all 18
  scenarios as misses (83.33% / 66.67% instead of ~100%). → **Fixed:** added a
  retry-on-(-1) to `pagination._get` and `build_gold.get` (HTTP error codes like 400 are
  real and returned as-is; only connection failures retry). **Confirmed:** the clean
  re-run (pagination-run-2) scored all four agents at **100% fidelity, 108/108 coverage**
  — the flake, not any plan/code error, caused the run-1 distortion. Further hardening
  option: a per-request health gate or serialized execution under heavy local load.

- **[MEDIUM] Local-model coverage variance.** qwen2.5:14b occasionally returns an
  unparseable/empty plan for a collection (seen once in the 2-collection smoke), which
  scores that collection as 'missing'. This is real framework/run signal the metric is
  meant to capture, but it makes a single run's headline noisy. → Average over several
  runs (the leaderboard already tracks best-so-far + run history); or raise temperature=0
  determinism / add a one-shot reformat retry in each framework wrapper.

- **[MEDIUM] Held-out is not disjoint from the ranking set.** Evolution's held-out
  collections (/users, /recipes) are also scored at rank time, so a SkillOpt edit could
  in principle tune the very items it is graded on. → Carve 1-2 ranking-only collections
  vs evolution-only collections. (Same open item flagged in the payload build.)

- **[LOW] "Pagination Correctness Rate" is the same for every faithful agent.** By
  design (it is a property of the API, ~77.78%), so it cannot rank the four — which is
  exactly why the judge ranks on fidelity-to-gold instead. Documented in metric.json;
  not a defect, but worth restating so the headline is not mistaken for the rank key.

## Ambiguities that may have slipped the gate

- L5 (page arithmetic) assumes `window_size - 2*page_size` is a sensible positive page-3
  size. For the fixed config (page_size 10, window 25 → 5) it is unambiguous; for a
  pathological config (e.g. window < 2*page_size) page3's limit could go negative. The
  brief always supplies 10/25, so no second reading reaches the agent today, but the line
  is only single-interpretation *given the supplied config* — worth a guard if the config
  ever varies.
- L7 pins `<page_size_param>` as "the exact name copied from the brief" and the fourth
  key as the literal "cursor"; Ultron's "rename the cursor key / take <page_size_param>
  literally" readings are denied by that clause. Re-read adversarially: holds.

## What will break first

- **Target availability under long parallel runs** (the run-1 flake) — addressed with
  retries; the next weakest link.
- **Local backend saturation:** 24 LLM calls (6 collections × 4 agents) at concurrency 2
  on a 14B model takes ~10-15 min; raising concurrency risks Ollama OOM/timeouts.
- **EverOS semantic-search scoping** (inherited): notes persist to the shared pool, but
  HTTP semantic search scoping is the same minor follow-up noted in the payload build.

## Recommended next actions (for the user to decide)

1. Re-run a few times and read best-so-far rather than a single run (leaderboard already
   supports it) — local-model variance averages out.
2. Carve a disjoint ranking-vs-held-out collection split before relying on the SkillOpt gate.
3. If a strict-contract demonstration is wanted (agents reaching 100%), point the build at
   a cursor-paginated fixture API — but that is a different Phase-2 target choice than the
   "DummyJSON as-is" one made here.
4. Add a one-shot JSON-reformat retry inside each framework wrapper to cut 'missing'-plan
   variance.
