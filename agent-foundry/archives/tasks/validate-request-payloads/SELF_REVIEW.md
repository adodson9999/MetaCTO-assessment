# Self-Review — API Request-Body Contract Tester · 2026-06-25

Report only. Nothing here is auto-applied; the user decides what to act on.

## Honest assessment (two axes)

**How complete:** ~85%. All six phases ran end-to-end on real data: 22-endpoint
empirical gold set, debate-gated prompts (12 lines/agent, four-lens trails), four
working framework agents, a deterministic fidelity judge, a populated leaderboard,
an in-sandbox EverOS pool, and a *validated* SkillOpt gate (a candidate edit moved
claude_sdk held-out fidelity 83.33→94.44 and was correctly staged, not adopted).

**How confident:** Medium-high on the measurement spine (gold, metric, judge,
sandbox, air-gap). Medium on the *comparison's discriminating power* and Lower on
the evolution loop's depth — see findings. I am deliberately not inflating: the
first run shows the four frameworks nearly tied, which is a real result, not a
polished one.

## Findings

- **[INFO — by design] Fidelity ≈ coverage.** Because all four agents hit the
  *same* live API, a correctly-formed payload always returns gold's class, so the
  metric measures *payload-construction completeness + faithful recording*, not
  bug-catching skill. Every covered case matched gold (112/112, 110/110) — no agent
  ever recorded a *wrong* class, only failed to produce some payloads. This is the
  correct scope for this agent: its job is to **exercise** the contract matrix and
  record real responses, not to **judge** whether the API *should* have rejected.
  Bug-catching / validation-gap judgment is explicitly a **separate agent, out of
  scope for this ticket** (per user, 2026-06-25). No metric change needed here.
- **[HIGH] Low framework separation under a deterministic backend.** Same gated
  prompt + same model + temp 0 ⇒ three agents tie exactly (85.27); langgraph wins
  only because its native Ollama JSON path produced two more `inv_maxlength`
  bodies. The foundry *measures* fairly but currently can't *separate* the
  frameworks much. → Expect separation to come from evolution (per-agent skills
  diverging) and from a harder metric; consider a small temperature or
  multi-sample pass@k to surface reliability differences.
- **[MEDIUM] Held-out overlaps the ranking set.** The leaderboard scores all 129
  cases including the 6 held-out endpoints the SkillOpt gate uses, so an evolved
  skill could tune items that also count at rank time. → Exclude `held_out.jsonl`
  endpoints from the leaderboard denominator (disjoint split).
- **[MEDIUM] Evolution is the pattern, not the vendored optimizer.** `evolve.py`
  implements the SkillOpt loop faithfully (bounded edit → held-out eval → strict
  judge-metric gate → stage) and a SkillClaw shared pool, but the candidate edit
  is one hand-distilled line, not the vendored `skillopt/train.py`
  rollout→reflect→aggregate→select search. → Wire the vendored engine to propose
  edits if deeper optimization is wanted; current loop is correct but shallow.
- **[MEDIUM] claude_sdk & api-tester-validate-request-payloads run in local-fallback mode.** Under
  the air-gapped Ollama backend there is no Anthropic/Claude-Code cloud, so both
  elicit via the local OpenAI-compatible path. They are genuine *artifacts* (SDK
  program; real subagent `.md`) but not exercising native Claude. → Flip
  `config.toml [backend].provider = "claude-haiku"` to run them natively, then
  re-judge.
- **[LOW] EverOS pool populates, but HTTP semantic recall needs scoping work.**
  Fixed: `phase4_run.sh` now starts EverOS and `EVEROS_MEMORY__ROOT` is pinned
  in-sandbox. Verified on re-run `20260625T112730`: the in-sandbox store grew to
  ~860K and `system.db` holds 2 extracted memcells + buffered messages + run
  records (writes attributable per agent via `sender_id`). However, a
  `/api/v1/memory/search` by `agent_id` returned empty — terse status breadcrumbs
  often yield EverOS "no_extraction", and the query scoping/embedding match needs
  tuning. The guaranteed `memory/agent-notes/` breadcrumbs remain the reliable,
  attributable record. → Write richer narrative notes and confirm a known
  add→flush→search round-trip if semantic recall is needed.

## Ambiguities that may have slipped the gate

- **L5 (`inv_missing_required`)** — "exactly one of its required fields removed"
  does not say *which* required field; any single removal is a faithful instance,
  so behavior is well-defined but non-deterministic across endpoints with ≥2
  required fields. Residual reading is benign. → If determinism matters, pin "the
  first required field as listed."
- **L6 (`inv_wrong_type`)** — "a value whose JSON type differs" leaves room for a
  coercible value (e.g. the string "5" for a number) that a lax API might accept.
  Intent (a genuinely rejected wrong type) is clear but not hard-pinned. → Could
  add "and that the schema would not coerce," though that over-specifies.

## What will break first

- **Local model saturation under parallel runs.** One Ollama 14B slot served all
  88 calls; 4-way parallelism thrashed the prompt cache and the full run took
  ~12 min, with langgraph the long pole. → Lower `--max-concurrency` to 2, or run
  agents sequentially with warm prompt caching.
- **Reranker cold-load latency.** `bge-reranker-v2-m3` takes ~10s on first load;
  fine for batch search, painful if called per-query. → Keep a warm process if
  hybrid search becomes interactive.
- **EverOS index lag / schema strictness.** `/add` requires a `role` field and a
  non-empty `session_id`; `/search` requires exactly one of `user_id`/`agent_id`.
  A small wording change in the DTOs would silently drop notes (errors are
  swallowed by design). → Add a startup contract-check that asserts a known
  add→flush→search round-trip before a run.

## Recommended next actions (for the user to decide)

1. ~~Choose the metric's teeth (seeded bugs / payload-correctness).~~ **Resolved:**
   bug-catching is a separate agent, out of scope. Metric stays as coverage +
   recording fidelity for this contract-testing agent.
2. Make the held-out and ranking splits disjoint.
3. Re-run `scripts/phase4_run.sh` now that EverOS auto-starts, to populate the pool
   and confirm an unchanged leaderboard.
4. Optionally flip the backend to `claude-haiku` and re-judge to see native-Claude
   vs local results, and to give the two Claude agents their real substrate.
5. Decide whether to wire the vendored SkillOpt search behind `evolve.py`, or keep
   the lightweight staged gate.
