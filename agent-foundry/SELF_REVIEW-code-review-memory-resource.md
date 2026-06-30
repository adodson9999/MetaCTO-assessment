# SELF_REVIEW — code-review-memory-resource

**Built:** 2026-06-29 · **Group:** code-review · **Short name:** memory-resource
**Backend:** not run live (no server started; deterministic gates only)

## What was built

The single-lens agent in all four frameworks (langgraph / crewai / claude_sdk / subagent),
mirroring the error-handling-resilience sibling's substrate:

- `agents/common/memresource_spec.py` — held-out loader, per-case brief, strict
  `{rating, notes}` schema gate + in-band scorer, reference oracle (band midpoint).
- `agents/common/memresource_prompt.py` — 12 debate-gated APPROVED_LINES + user message.
- `agents/common/memresource.py` — deterministic driver. Empty/raising `generate()` → `{}`
  → scores 0.0 (no saturation).
- `agents/code-review/memory-resource/{langgraph,crewai,claude_sdk,subagent}/run.py`.
- `agents/code-review/memory-resource/subagent/code-review-memory-resource.md` — canonical
  prompt; body == APPROVED_LINES verbatim (consistency-checked).
- `judge/code-review/memory-resource/{metric.json,score.py}` — `rating_band_accuracy`,
  tie-break schema-pass → tokens → elapsed; renders leaderboard.
- `results/code-review/memory-resource/held_out.jsonl` — 8 cases.
- `tests/golden/code-review/memory-resource/{run_golden.py,golden.json}`.
- `scripts/run_memresource_agents__code-review-memory-resource.py`.
- `data/code-review-memory-resource/task_spec.md`.
- Registered: `.claude/agents/code-review-memory-resource.md` (host symlink, resolves).

## Verification (deterministic, no model, no server)

- `py_compile` clean on all 10 Python files.
- Golden suite: schema 14/14 (rejects 101, −1, float, string, bool, empty notes, extra key,
  missing notes, empty object; accepts well-formed 100/low/0/retained-ref) + band 6/6
  (oracle in-band + empty scores 0).
- Metric soundness self-test: oracle (band-midpoint) = **1.0**, empty = **0.0**,
  degraded "always 95" = **0.375** → rewards correct, refuses fallback saturation,
  discriminates. Owner seed bands honored exactly (mr-001 [85,100], mr-002 [0,50]).
- Consistency: subagent `.md` body == 12 gated APPROVED_LINES verbatim.

## Held-out coverage (8 cases)

Safe/high: `with open` (mr-001), `try/finally` close (mr-007), bounded `lru_cache(maxsize=128)`
(mr-008). Leaks/low: `f.close()` on happy path only (mr-003), listener registered never
removed (mr-004), allocation sized by an unbounded request header (mr-005), never-evicted
cache (mr-002, seed), use-after-close (mr-006). Five of the six lens bullets are exercised by
≥1 held-out case; the sixth (retained reference that prevents collection) is exercised in the
golden `schema_cases` (`ok-retained-ref`) but is **not** yet a band case.

## Gaps / residual risk

- **HIGH — no live ranking.** No backend started, so no real four-way leaderboard yet. The
  harness is wired: `python scripts/run_memresource_agents__code-review-memory-resource.py`
  then the judge `score.py`, once Ollama (or a Claude shim) is up. Expect a likely high/tied
  field — the prompt is highly determined and the snippets are unambiguous.
- **MEDIUM — retained-reference not in held-out.** Add a band case (e.g. an append to a
  module-level list never cleared) so every lens bullet has a held-out anchor, not just a
  golden schema example.
- **MEDIUM — band width / small set (8).** Bands are generous and the set is small; enough to
  exercise the bullets once, not to separate two strong agents finely. Schema-pass is the
  real discriminator at this size.
- **LOW — Phase 4.5 / Phase 5 not run.** No 10-round tournament or SkillOpt/SkillClaw wiring
  for this lens (matches the recent code-review siblings). Post-golden baseline = oracle 1.0.

## Concrete improvements (not auto-applied)

1. Start a backend and run the four agents + judge to produce the first real leaderboard.
2. Add a retained-reference band case + 3–4 harder cases (release in `finally` that itself
   can raise; cache with TTL but unbounded keyspace; double-close).
3. Tighten bands after observing the live rating distribution.
