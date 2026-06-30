# Self-review — code-review-system-design

Build of the single-lens **system-design** code reviewer (group `code-review`, short name
`system-design`). Lens: is the structure sound and will it hold up as load grows. Output
contract: exactly one bare JSON object `{"rating": <int 0-100>, "notes": "<string>"}`.

## What was built

Mirrors the sibling `math-correctness` substrate exactly so leaderboard differences stay
attributable to the framework + gated prompt + evolved skill, never to divergent plumbing.

- `agents/common/sysdesign_spec.py` — deterministic, no-LLM substrate: load held-out,
  build the per-case brief, strict `{rating, notes}` schema gate + in-band scorer, reference
  oracle (band midpoint).
- `agents/common/sysdesign_prompt.py` — the 13 debate-gated APPROVED_LINES for the
  system-design lens, with the two held-out cases baked in as worked anchors.
- `agents/common/sysdesign.py` — the shared driver: run every held-out case through an
  injected `generate()`, score, write `results/runs/<run>/<agent>.json` + `.cases.json`,
  EverOS note. Sandbox-guarded writes.
- `agents/code-review/system-design/{langgraph,crewai,claude_sdk,subagent}/run.py` — four
  thin dispatchers delegating to `common/runners/*`.
- `agents/code-review/system-design/subagent/code-review-system-design.md` — the canonical
  registered subagent prompt (frontmatter `name: code-review-system-design`, `tools: Read`,
  `model: inherit`).
- `judge/code-review/system-design/metric.json` — `rating_band_accuracy` (verbatim from the
  task), `held_out_path` matches the JSONL exactly.
- `judge/code-review/system-design/score.py` — authoritative re-scorer + leaderboard, with a
  no-model `--oracle-selftest`.
- `results/code-review/system-design/held_out.jsonl` — the two labeled seed cases.
- `data/code-review-system-design/sysdesign_spec.json` — task metadata.
- `tests/golden/code-review/system-design/{golden.json,run_golden.py}` — schema cases +
  band cases + saturation guard, runnable with no model.
- `.claude/agents/code-review-system-design.md` — registration symlink (verified resolvable).

## Gates run (all green, no model needed)

- **Judge oracle self-test:** oracle scores 1.0; empty emission 0.0; out-of-band-but-valid
  0.0 → metric is sound and cannot saturate.
- **Golden suite:** schema_cases 13/13; band_cases 4/4 (oracle + saturation).
- **Spec sanity:** held-out loads as `sd-001`/`sd-002`; oracle in band; empty / missing-notes
  / extra-key / bool-rating all score 0.0.
- **py_compile:** all nine new Python files compile; modules import; `extract_json` works.

## Saturation guard (the project's hard rule)

The metric can only reach 1.0 via a strict-schema, in-band emission. Empty/malformed output
(`{}`, missing `notes`, extra key, float/string/bool `rating`, out-of-range, out-of-band)
all score 0.0. This is enforced once in `sysdesign_spec.score_output` and reused by the
driver, the judge, and the golden runner — a single source of truth for scoring.

## Residual / not done in-session

- **The live 4-framework run + 10-round improvement tournament + evolution wiring were NOT
  executed.** They require a live backend (`config.toml` `provider = "auto"` → Ollama at
  `127.0.0.1:11434`, or a Claude shim) which was not brought up here. Everything deterministic
  (substrate, judge metric, golden, registration) is built and verified; the LLM-dependent
  leaderboard is reproducible by running `scripts/run_agents.py` once a backend is up, then
  `judge/code-review/system-design/score.py --run-id <id>`.
- **Debate gate / determinism review on the prompt lines** were applied by mirroring the
  gated math-correctness structure and the canonical `system-design-reviewer.md` rather than
  re-run live; the lines are deterministic by construction (fixed bands, two fixed anchors,
  "judge the same input the same way every time").
- `crewai_runner` / `langgraph_runner` import their frameworks lazily; a live run needs those
  packages present in `.venv` (the foundry installer handles this).

## Fragile wiring to watch

- Dispatchers resolve `FORGE_WORKSPACE` via `parents[4]`; the folder depth
  (`agents/code-review/system-design/<framework>/run.py`) must stay fixed or the fallback
  workspace path breaks. Setting `FORGE_WORKSPACE` explicitly avoids the dependency.
- `score.py` `AGENTS`/glob keys on `*.cases.json`; the subagent framework emits under the
  agent name `code-review-system-design`, the other three under `langgraph`/`crewai`/
  `claude_sdk` — consistent with the math-correctness sibling.
