# Self-review — code-review-security

Build of the single-lens **security** code reviewer (group `code-review`, short name
`security`). Lens: can an attacker abuse this via an unsafe input, an exposed secret, or an
insecure default. Output contract: exactly one bare JSON object
`{"rating": <int 0-100>, "notes": "<string>"}`.

## What was built

Mirrors the sibling `network` / `system-design` / `math-correctness` substrate exactly so
leaderboard differences stay attributable to the framework + gated prompt + evolved skill,
never to divergent plumbing.

- `agents/common/security_spec.py` — deterministic, no-LLM substrate: load held-out, build
  the per-case brief, strict `{rating, notes}` schema gate + in-band scorer, reference
  oracle (band midpoint).
- `agents/common/security_prompt.py` — the 13 debate-gated APPROVED_LINES for the security
  lens, with the two seed held-out cases baked in as worked anchors and the six lens checks
  enumerated verbatim (injection sink, hard-coded/logged secret, missing authz, insecure
  default, unauthenticated path to sensitive resource, new attack surface).
- `agents/common/security.py` — the shared driver: run every held-out case through an
  injected `generate()`, score, write `results/runs/<run>/<agent>.json` + `.cases.json`,
  EverOS note. Sandbox-guarded writes.
- `agents/code-review/security/{langgraph,crewai,claude_sdk,subagent}/run.py` — four thin
  dispatchers delegating to `common/runners/*`.
- `agents/code-review/security/subagent/code-review-security.md` — the canonical registered
  subagent prompt (frontmatter `name: code-review-security`, `tools: Read`, `model: inherit`).
- `judge/code-review/security/metric.json` — `rating_band_accuracy` (verbatim from the task),
  `held_out_path` matches the JSONL exactly.
- `judge/code-review/security/score.py` — authoritative re-scorer + leaderboard, with a
  no-model `--oracle-selftest`.
- `results/code-review/security/held_out.jsonl` — 8 labeled cases (the 2 task seeds + 6 that
  isolate one lens check each: shell injection, hard-coded secret, TLS-verify-off insecure
  default, wildcard-CORS-with-credentials, untrusted `pickle.loads`, and a clean
  env-sourced-secret + parameterized + bounded call).
- `data/code-review-security/security_spec.json` — task metadata.
- `tests/golden/code-review/security/{golden.json,run_golden.py}` — 13 schema cases + 2 band
  cases + saturation guard, runnable with no model.
- `.claude/agents/code-review-security.md` — registration **symlink** into the subagent
  prompt (matches the sibling symlinks; verified resolvable, frontmatter `name` correct).
- `scripts/run_security_agents__code-review-security.py` — task-scoped parallel runner for
  the four frameworks.

## Gates run (all green, no model needed)

- **Judge oracle self-test:** oracle scores 1.0; empty emission 0.0; out-of-band-but-valid
  0.0 → metric is sound and cannot saturate.
- **Golden suite:** schema_cases 13/13; band_cases 4/4 (oracle + saturation).
- **Spec sanity:** held-out loads as `sec-001`..`sec-008`; every oracle midpoint lands in
  band; empty / missing-notes / extra-key / float-, string-, bool-rating all score 0.0.
- **py_compile:** all nine new Python files compile; modules import; `extract_json` works.
- **Cross-artifact consistency (/analyze):** `held_out_path` is byte-identical across
  `metric.json`, `security_spec.py`, the data spec, and `score.py`; the two seed bands agree
  between `held_out.jsonl` and the golden `band_cases`.

## Saturation guard (the project's hard rule)

The metric can only reach 1.0 via a strict-schema, in-band emission. Empty/malformed output
(`{}`, missing `notes`, extra key, float/string/bool `rating`, out-of-range, out-of-band)
all score 0.0. This is enforced once in `security_spec.score_output` and reused by the
driver, the judge, and the golden runner — a single source of truth for scoring.

## Held-out band design (determinism)

Each case isolates ONE lens issue and sits in a band wide enough that a correct reviewer
lands inside it deterministically but narrow enough to reject a wrong lens:

| id | issue isolated | band |
|----|----------------|------|
| sec-001 | parameterized query, untrusted id bound (clean) | 85–100 |
| sec-002 | untrusted id concatenated into SQL (injection sink) | 0–35 |
| sec-003 | user host concatenated into `os.system` (shell injection) | 0–35 |
| sec-004 | hard-coded live API secret | 0–35 |
| sec-005 | `verify=False` (TLS verification off, insecure default) | 20–55 |
| sec-006 | wildcard CORS + allow-credentials (insecure default) | 40–70 |
| sec-007 | `pickle.loads` of an untrusted request body (deserialization RCE) | 0–35 |
| sec-008 | env-sourced secret + parameterized + bounded call (clean) | 80–100 |

The two seeds (`sec-001`, `sec-002`) are reproduced verbatim from the task and also serve as
the prompt's two worked anchors, so the scale is pinned to the exact examples the judge
scores against.

## Residual / not done in-session

- **The live 4-framework run + 10-round improvement tournament + evolution wiring were NOT
  executed.** They require a live backend (`config.toml` `provider = "auto"` → current
  Claude Code session → Ollama → cloud) not brought up here, and the memory note
  `forge-concurrent-codereview-build` warns the code-review group races across concurrent
  forge sessions — so a live run/commit during a race is deliberately avoided. Everything
  deterministic (substrate, judge metric, golden, registration) is built and verified; the
  LLM-dependent leaderboard is reproducible by running
  `scripts/run_security_agents__code-review-security.py` once a backend is up, then
  `judge/code-review/security/score.py --run-id <id>`.
- **Debate gate / determinism review on the prompt lines** were applied by mirroring the
  gated sibling structure rather than re-run live; the lines are deterministic by
  construction (fixed bands, two fixed anchors, "judge the same input the same way every
  time").
- `crewai_runner` / `langgraph_runner` import their frameworks lazily; a live run needs
  those packages present in `.venv` (the foundry installer handles this).

## Fragile wiring to watch

- Dispatchers resolve `FORGE_WORKSPACE` via `parents[4]`; the folder depth
  (`agents/code-review/security/<framework>/run.py`) must stay fixed or the fallback
  workspace path breaks. Setting `FORGE_WORKSPACE` explicitly avoids the dependency.
- `score.py` globs `*.cases.json`; the subagent framework emits under the agent name
  `code-review-security`, the other three under `langgraph`/`crewai`/`claude_sdk` —
  consistent with the siblings.
- `import security` / `import security_spec` resolve via the `agents/common` path inserted
  first on `sys.path`; no stdlib or third-party `security` module is shadowed in the foundry
  `.venv`, but keep the `agents/common` insert ahead of any future package named `security`.
- A separate `tests/golden/code-review/vulnerability/` suite exists (concurrent sibling
  work); it is distinct from this `security` lens and shares no files with it.
