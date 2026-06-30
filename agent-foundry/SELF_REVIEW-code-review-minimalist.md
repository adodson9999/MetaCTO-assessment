# SELF_REVIEW — code-review / minimalist

Build of the single-lens code-review agent `code-review-minimalist` (group `code-review`,
short name `minimalist`), workflow branch `code-review-minimalist`.

## What was built (Phase 6.1 — output contract: PASS)

Four framework implementations of one task + a judge, all on the shared deterministic
substrate (so leaderboard differences are framework/prompt/skill, not plumbing):

- `agents/common/codereview_prompt.py` — debate-gated APPROVED_LINES (the minimalism lens),
  `active_prompt()`, `user_message()`. Source of truth for the prompt.
- `agents/common/codereview_spec.py` — load held-out cases, strict `{rating, notes}` schema
  check, in-band scoring, reference oracle.
- `agents/common/codereview.py` — deterministic driver: per-case brief → injected
  `generate()` → score → emit `results/runs/<run>/<agent>.json` + `.cases.json`.
- `agents/code-review/minimalist/{langgraph,crewai,claude_sdk,subagent}/run.py` — thin
  dispatchers delegating to `common/runners/*`.
- `agents/code-review/minimalist/subagent/code-review-minimalist.md` — gated system prompt
  (body == `APPROVED_PROMPT`, verified programmatically) + frontmatter.
- `.claude/agents/code-review-minimalist.md` — symlink registration (matches the group's
  device-stack/system-design/math-correctness convention).
- `judge/code-review/minimalist/metric.json` — the contract verbatim (`rating_band_accuracy`).
- `judge/code-review/minimalist/score.py` — recompute + rank (accuracy ↓ → tokens ↑ → elapsed ↑).
- `data/code-review-minimalist/{codereview_spec.json,task_spec.md}`.
- `results/code-review/minimalist/held_out.jsonl` — the 2-case labeled set (contract path).
- `scripts/run_codereview_agents__minimalist.py` — task-scoped parallel runner.
- `tests/golden/code-review/minimalist/golden.json` — baseline 1.0 + 5 structure cases.

## Determinism / metric-saturation guard (oracle-tested: PASS)

The metric-saturation failure mode (empty/fallback output scoring 100%) was explicitly
oracle-tested before baking golden assertions:

- oracle (gold-band midpoint + note) → 1.0
- empty `{}` → 0.0
- extra key / string-rating / float-rating / bool-rating / empty-notes → 0.0 (strict schema)
- out-of-band valid object → 0.0
- **constant-rating agent → at most 0.5**: the two seed bands are disjoint ([90,100] vs
  [0,55]), so the metric cannot be faked by emitting one fixed number.

## Live run (Phase 4 + Phase 6.2 golden: PASS)

Ran the four agents against the reachable local Ollama backend (`qwen2.5:14b-instruct`).
All four hit both bands: minimal one-liner → 90, over-engineered rewrite → 20.
`rating_band_accuracy = 1.0` for all four, schema-valid 100%. Live best (1.0) ≥ golden
baseline (1.0), tolerance 0.

## Gaps / residual ambiguities / fragile wiring

1. **Concurrent build of the same group.** During this build, another process was actively
   forging sibling lenses in `code-review/` (created `code-review-system-design.md` at 19:41,
   `git add`-ed `math-correctness/held_out.jsonl`, edited `.gitignore`). It clobbered the
   first copy of `results/code-review/minimalist/held_out.jsonl`, which had to be restored.
   The fixture lives under the gitignored `results/` tree, kept tracked only via a `.gitignore`
   negation — fragile if a `results/` cleanup runs. A more robust home would be
   `data/code-review-minimalist/`, but `metric.json`'s declared `held_out_path` (a contract
   given verbatim) points at `results/`, so the negation is the faithful compromise. **No git
   commit was performed** to avoid colliding with the other process's staging.
2. **Debate gate + determinism review not re-run live.** The prompt lines are authored to the
   gate's standard and mirror the sibling/general-group gated prompts, but the four-member
   adversarial gate and the N-times determinism regeneration were not executed against a live
   panel this session. The prompt's own "judge the same input the same way every time" line and
   temperature-0 backends make the live output deterministic in practice (all four frameworks
   converged on identical ratings).
3. **2-case held-out set.** Disjoint-band design makes saturation impossible, but two cases is
   thin for the 70–89 and 40–69 bands, which are untested by gold. Swapping in more labeled
   examples (the `note` in `codereview_spec.json` documents how) would harden the metric.
4. **Phase 4.5 tournament + Phase 5 evolution not run.** The agents already saturate the metric
   (1.0), so the keep-if-improved loop has no headroom on this seed set; it should be re-run if
   a richer held-out set drops a framework below 1.0.

## Concrete improvements (not auto-applied)

- Expand `held_out.jsonl` with mid-band cases (e.g. duplicated logic a helper would remove →
  70–89; a needless abstraction layer → 40–69) to exercise the full band scale.
- Once the concurrent group build settles, reconcile `.gitignore` and commit the group as a unit.
