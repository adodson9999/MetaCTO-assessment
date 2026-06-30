# SELF_REVIEW — code-review / unit-test

Build of the single-lens code-review agent `code-review-unit-test` (group `code-review`,
short name `unit-test`), workflow branch `code-review-unit-test`. Mirrors the `minimalist`
sibling's structure; only the lens, held-out seed, and module names differ.

## What was built (Phase 6.1 — output contract: PASS)

- `agents/common/unittestlens_prompt.py` — debate-gated APPROVED_LINES (the "would the tests
  fail if the code were wrong" lens), `active_prompt()`, `user_message()`. Named
  `unittestlens` to avoid colliding with the stdlib `unittest` module.
- `agents/common/unittestlens_spec.py` — load held-out cases, strict `{rating, notes}` schema
  check, in-band scoring, reference oracle.
- `agents/common/unittestlens.py` — deterministic driver.
- `agents/code-review/unit-test/{langgraph,crewai,claude_sdk,subagent}/run.py` — thin dispatchers.
- `agents/code-review/unit-test/subagent/code-review-unit-test.md` — gated prompt (body ==
  `APPROVED_PROMPT`, verified programmatically) + frontmatter.
- `.claude/agents/code-review-unit-test.md` — symlink registration (group convention).
- `judge/code-review/unit-test/{metric.json,score.py}` — contract verbatim + recompute/rank.
- `data/code-review-unit-test/{unittestlens_spec.json,task_spec.md}`.
- `results/code-review/unit-test/held_out.jsonl` — 2-case labeled set (contract path).
- `scripts/run_unittestlens_agents__unit-test.py` — task-scoped parallel runner.
- `tests/golden/code-review/unit-test/golden.json` — baseline 1.0 + 5 structure cases.

## Determinism / metric-saturation guard (oracle-tested: PASS)

- oracle (gold-band midpoint + note) → 1.0
- empty `{}` → 0.0
- extra key / string-rating / float-rating / bool-rating / empty-notes → 0.0 (strict schema)
- **constant-rating agent → at most 0.5**: the two seed bands are disjoint ([85,100] vs
  [0,30]), so the metric cannot be faked by emitting one fixed number.

## Live run (Phase 4 + Phase 6.2 golden: PASS)

Ran the four agents against the local Ollama backend (`qwen2.5:14b-instruct`). All four hit
both bands: strong test (exact-value asserts across positive/negative/zero) → 85, vacuous
`is not None` test → 5–10. `rating_band_accuracy = 1.0` for all four, schema-valid 100%.
Live best (1.0) ≥ golden baseline (1.0), tolerance 0.

## Gaps / residual ambiguities

1. **Held-out fixture under the gitignored `results/` tree.** As with `minimalist`, the
   contract's `held_out_path` points at `results/code-review/unit-test/held_out.jsonl`; it is
   kept tracked by force-adding the file (no `.gitignore` fight). Fragile if a `results/`
   cleanup runs.
2. **Debate gate + determinism review not re-run live.** Lines are authored to the gate's
   standard; temperature-0 backends produced identical ratings across all four frameworks
   (de facto deterministic).
3. **2-case held-out set.** Disjoint-band design blocks saturation, but the 70–89 and 40–69
   bands are untested by gold. Adding mid-band cases (e.g. tests that cover the happy path but
   miss one error branch → 70–89; a test that asserts only via an over-mock → 40–69) would
   harden the metric.
4. **Phase 4.5 tournament + Phase 5 evolution not run** — agents already saturate the metric
   on this seed; re-run if a richer held-out set drops a framework below 1.0.

## Concrete improvements (not auto-applied)

- Expand `held_out.jsonl` with mid-band cases to exercise the full band scale (missing-branch
  coverage, flaky-by-time test, over-mocked interaction-only test).
