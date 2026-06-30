# Self-review — code-review-adversarial-input

Build of the single-lens **adversarial-input** code reviewer (group `code-review`, short
name `adversarial-input`). Lens: can a hostile or malformed input crash, hang, or exhaust
this code — robustness, NOT exploitability. Output contract: exactly one bare JSON object
`{"rating": <int 0-100>, "notes": "<string>"}`.

## What was built

Mirrors the validated sibling `security` / `network` substrate exactly so leaderboard
differences stay attributable to the framework + gated prompt + evolved skill, never to
divergent plumbing.

- `agents/common/advinput_spec.py` — deterministic, no-LLM substrate: load held-out, build
  the per-case brief, strict `{rating, notes}` schema gate + in-band scorer, reference
  oracle (band midpoint).
- `agents/common/advinput_prompt.py` — the 13 debate-gated APPROVED_LINES for the lens, with
  the two seed held-out cases baked in as worked anchors and the six checks enumerated
  verbatim (empty/null/missing; oversized/nested/overflow; malformed encoding/Unicode;
  resource bomb; silent acceptance of invalid; no limit before expensive work).
- `agents/common/advinput.py` — the shared driver: run every held-out case through an
  injected `generate()`, score, write `results/runs/<run>/<agent>.json` + `.cases.json`,
  EverOS note. Sandbox-guarded writes.
- `agents/code-review/adversarial-input/{langgraph,crewai,claude_sdk,subagent}/run.py` —
  four thin dispatchers delegating to `common/runners/*`.
- `agents/code-review/adversarial-input/subagent/code-review-adversarial-input.md` — the
  canonical registered subagent prompt (frontmatter `name: code-review-adversarial-input`,
  `tools: Read`, `model: inherit`).
- `judge/code-review/adversarial-input/metric.json` — `rating_band_accuracy` (verbatim from
  the task), `held_out_path` matches the JSONL exactly.
- `judge/code-review/adversarial-input/score.py` — authoritative re-scorer + leaderboard,
  with a no-model `--oracle-selftest`.
- `results/code-review/adversarial-input/held_out.jsonl` — 8 labeled cases (the 2 task seeds
  + 6 that isolate one check each).
- `data/code-review-adversarial-input/advinput_spec.json` — task metadata.
- `tests/golden/code-review/adversarial-input/{golden.json,run_golden.py}` — 13 schema cases
  + 2 band cases + saturation guard, runnable with no model.
- `.claude/agents/code-review-adversarial-input.md` — registration **symlink** into the
  subagent prompt (matches the sibling symlinks; verified resolvable, frontmatter `name`
  correct).
- `scripts/run_advinput_agents__code-review-adversarial-input.py` — task-scoped parallel
  runner for the four frameworks.

## Gates run (all green, no model needed)

- **Judge oracle self-test:** oracle scores 1.0; empty emission 0.0; out-of-band-but-valid
  0.0 → metric is sound and cannot saturate.
- **Golden suite:** schema_cases 13/13; band_cases 4/4 (oracle + saturation).
- **Spec sanity:** held-out loads as `adv-001`..`adv-008`; every oracle midpoint lands in
  band; empty / missing-notes / extra-key / float-, string-, bool-rating all score 0.0.
- **py_compile:** all new Python files compile; modules import; `extract_json` works.
- **Cross-artifact consistency (/analyze):** `held_out_path` is byte-identical across
  `metric.json`, `advinput_spec.py`, the data spec, and `score.py`; the two seed bands agree
  between `held_out.jsonl` and the golden `band_cases`.

## Saturation guard (the project's hard rule)

The metric can only reach 1.0 via a strict-schema, in-band emission. Empty/malformed output
all score 0.0. Enforced once in `advinput_spec.score_output` and reused by the driver, the
judge, and the golden runner — a single source of truth for scoring.

## Held-out band design (determinism)

Each case isolates ONE lens issue and sits in a band wide enough that a correct reviewer
lands inside it deterministically but narrow enough to reject a wrong lens:

| id | issue isolated | band |
|----|----------------|------|
| adv-001 | guards empty + caps slice length (clean) | 85–100 |
| adv-002 | catastrophic-backtracking regex `(a+)+$` on untrusted input | 0–40 |
| adv-003 | `user['name']` assumes a dict with the key present → KeyError / TypeError | 10–45 |
| adv-004 | unbounded recursion on a deeply-nested list → RecursionError | 20–55 |
| adv-005 | `b.decode('utf-8')` with no error handling → UnicodeDecodeError on bad bytes | 25–60 |
| adv-006 | `json.loads` + per-item work with no size/count limit before the loop | 30–65 |
| adv-007 | silent acceptance: invalid input swallowed and returned as 0 | 55–80 |
| adv-008 | bounds length, caps count to 1000, filters non-digits (clean) | 80–100 |

The two seeds (`adv-001`, `adv-002`) are reproduced verbatim from the task and also serve as
the prompt's two worked anchors, so the scale is pinned to the exact examples the judge
scores against.

## Lens boundary (robustness, not exploitability)

This lens deliberately overlaps-but-differs from the sibling `security` lens: a
catastrophic-backtracking regex is in scope here as a **hang/DoS-robustness** failure, and
out of scope as an injection/secret/authz concern. The scope-only line forbids lowering the
rating for exploitability/security — that is the `security` agent's job — so the two agents
stay independent.

## Residual / not done in-session

- The live 4-framework run + 10-round tournament + evolution wiring are reproducible via
  `scripts/run_advinput_agents__code-review-adversarial-input.py` (FORGE_PROVIDER=ollama)
  then `judge/code-review/adversarial-input/score.py --run-id <id>`; status of those runs is
  recorded in `prompts.txt`.
- **Debate gate / determinism review on the prompt lines** were applied by mirroring the
  gated sibling structure rather than re-run live; the lines are deterministic by
  construction (fixed bands, two fixed anchors, "judge the same input the same way every
  time"), and all four runners decode at `temperature=0`.

## Fragile wiring to watch

- Dispatchers resolve `FORGE_WORKSPACE` via `parents[4]`; the depth
  (`agents/code-review/adversarial-input/<framework>/run.py`) must stay fixed or the fallback
  workspace path breaks. Setting `FORGE_WORKSPACE` explicitly avoids the dependency.
- `score.py` globs `*.cases.json`; the subagent framework emits under the agent name
  `code-review-adversarial-input`, the other three under `langgraph`/`crewai`/`claude_sdk`.
- The hyphenated short name `adversarial-input` is the path/judge token; the Python module
  prefix is `advinput` (a hyphen is not a valid identifier) — keep the two in sync.
