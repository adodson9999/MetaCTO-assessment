# Self-review — code-review-network

Build of the single-lens **network** code reviewer (group `code-review`, short name
`network`). Lens: does the code stay correct when the network is slow, flaky, or down.
Output contract: exactly one bare JSON object `{"rating": <int 0-100>, "notes": "<string>"}`.

## What was built

Mirrors the sibling `system-design` / `math-correctness` substrate exactly so leaderboard
differences stay attributable to the framework + gated prompt + evolved skill, never to
divergent plumbing.

- `agents/common/network_spec.py` — deterministic, no-LLM substrate: load held-out, build
  the per-case brief, strict `{rating, notes}` schema gate + in-band scorer, reference
  oracle (band midpoint).
- `agents/common/network_prompt.py` — the 13 debate-gated APPROVED_LINES for the network
  lens, with the two seed held-out cases baked in as worked anchors and the six lens checks
  enumerated verbatim.
- `agents/common/network.py` — the shared driver: run every held-out case through an
  injected `generate()`, score, write `results/runs/<run>/<agent>.json` + `.cases.json`,
  EverOS note. Sandbox-guarded writes.
- `agents/code-review/network/{langgraph,crewai,claude_sdk,subagent}/run.py` — four thin
  dispatchers delegating to `common/runners/*`.
- `agents/code-review/network/subagent/code-review-network.md` — the canonical registered
  subagent prompt (frontmatter `name: code-review-network`, `tools: Read`, `model: inherit`).
- `judge/code-review/network/metric.json` — `rating_band_accuracy` (verbatim from the task),
  `held_out_path` matches the JSONL exactly.
- `judge/code-review/network/score.py` — authoritative re-scorer + leaderboard, with a
  no-model `--oracle-selftest`.
- `results/code-review/network/held_out.jsonl` — 8 labeled cases (the 2 task seeds + 6 that
  isolate one lens check each: no-timeout, retry-no-backoff on a non-idempotent write,
  N+1 round-trips, missing fallback, timeout-longer-than-deadline, and a clean
  bounded-retry-with-backoff-and-jitter on an idempotent read).
- `data/code-review-network/network_spec.json` — task metadata.
- `tests/golden/code-review/network/{golden.json,run_golden.py}` — 13 schema cases + 2 band
  cases + saturation guard, runnable with no model.
- `.claude/agents/code-review-network.md` — registration **symlink** into the subagent
  prompt (matches the three sibling symlinks; verified resolvable, frontmatter `name`
  correct).

## Gates run (all green, no model needed)

- **Judge oracle self-test:** oracle scores 1.0; empty emission 0.0; out-of-band-but-valid
  0.0 → metric is sound and cannot saturate.
- **Golden suite:** schema_cases 13/13; band_cases 4/4 (oracle + saturation).
- **Spec sanity:** held-out loads as `nw-001`..`nw-008`; every oracle midpoint lands in
  band; empty / missing-notes / extra-key / float-, string-, bool-rating all score 0.0.
- **py_compile:** all nine new Python files compile; modules import; `extract_json` works.
- **Cross-artifact consistency (/analyze):** `held_out_path` is byte-identical across
  `metric.json`, `network_spec.py`, the data spec, and `score.py`; the two seed bands agree
  between `held_out.jsonl` and the golden `band_cases`.

## Saturation guard (the project's hard rule)

The metric can only reach 1.0 via a strict-schema, in-band emission. Empty/malformed output
(`{}`, missing `notes`, extra key, float/string/bool `rating`, out-of-range, out-of-band)
all score 0.0. This is enforced once in `network_spec.score_output` and reused by the
driver, the judge, and the golden runner — a single source of truth for scoring.

## Held-out band design (determinism)

Each case isolates ONE lens issue and sits in a band wide enough that a correct reviewer
lands inside it deterministically but narrow enough to reject a wrong lens:

| id | issue isolated | band |
|----|----------------|------|
| nw-001 | idempotent GET with timeout (clean) | 80–100 |
| nw-002 | infinite retry of a non-idempotent POST, no backoff | 0–35 |
| nw-003 | bounded retry + backoff + jitter on idempotent GET (clean) | 85–100 |
| nw-004 | GET with no timeout → hangs on a slow network | 0–40 |
| nw-005 | retry of a non-idempotent charge, no idempotency key | 0–35 |
| nw-006 | N+1 per-id round-trips | 40–69 |
| nw-007 | optional dependency with no fallback | 55–80 |
| nw-008 | timeout (30s) longer than the caller's 3s deadline | 30–60 |

## Residual / not done in-session

- **The live 4-framework run + 10-round improvement tournament + evolution wiring were NOT
  executed.** They require a live backend (`config.toml` `provider = "auto"` → current
  Claude Code session → Ollama → cloud) not brought up here, and the memory note
  `forge-concurrent-codereview-build` warns the code-review group races across concurrent
  forge sessions — so a live run/commit during a race is deliberately avoided. Everything
  deterministic (substrate, judge metric, golden, registration) is built and verified; the
  LLM-dependent leaderboard is reproducible by running `scripts/run_agents.py` once a
  backend is up, then `judge/code-review/network/score.py --run-id <id>`.
- **Debate gate / determinism review on the prompt lines** were applied by mirroring the
  gated sibling structure rather than re-run live; the lines are deterministic by
  construction (fixed bands, two fixed anchors, "judge the same input the same way every
  time").
- `crewai_runner` / `langgraph_runner` import their frameworks lazily; a live run needs
  those packages present in `.venv` (the foundry installer handles this).

## Fragile wiring to watch

- Dispatchers resolve `FORGE_WORKSPACE` via `parents[4]`; the folder depth
  (`agents/code-review/network/<framework>/run.py`) must stay fixed or the fallback
  workspace path breaks. Setting `FORGE_WORKSPACE` explicitly avoids the dependency.
- `score.py` globs `*.cases.json`; the subagent framework emits under the agent name
  `code-review-network`, the other three under `langgraph`/`crewai`/`claude_sdk` —
  consistent with the siblings.
- The N+1 case (nw-006) and the missing-fallback case (nw-007) both have a valid timeout, so
  a reviewer that only checks timeouts would over-rate them; the bands (40–69, 55–80) are set
  to catch exactly that failure mode in the held-out scoring.
