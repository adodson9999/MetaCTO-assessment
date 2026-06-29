# Code-Quality Gate (aislop-style) — every deterministic file

Inspired by **scanaislop/aislop**: a deterministic (regex + AST + standard
tooling, **no LLM**) quality gate that scores code 0–100 and blocks anything that
regresses below a baseline. In forge, **every piece of deterministic code the
foundry generates passes this gate** before it is committed: the scripts, the four
`run.py` dispatchers, the shared runners, `score.py`, `metric.json` loaders, the
golden runner, the verify/analyze/determinism scripts — all of it.

This sits beside the **determinism review** and they are different on purpose:

| Gate                    | Question                                   | Method |
|-------------------------|--------------------------------------------|--------|
| Determinism review      | Is the AI *output* stable across samples?  | re-sample N times, compare |
| Code-quality gate (this)| Is the generated *code* clean, not slop?   | static regex + AST, no model |

Both are deterministic-friendly and both are mandatory (constitution Article II
+ Article I.8).

## What it catches (the slop)

Six deterministic engines, run in parallel, exactly in aislop's spirit:

| Engine        | Checks |
|---------------|--------|
| Formatting    | style consistency (ruff/black for Python, gofmt, etc.) |
| Linting       | language lint issues (ruff, oxlint, golangci-lint, clippy) |
| Code quality  | function/file size limits, deep nesting, dead code, unused files/deps |
| AI slop       | narrative/trivial comments, dead patterns, unused imports, `as any`/bare `except:`, leftover `print`/`console.log`, TODO stubs, hallucinated imports, generic names |
| Security      | `eval`, injection, risky calls, dependency audit |
| Architecture  | forge-specific structural rules (below) |

## Forge-specific architecture rules (opt-in engine)

Encode the foundry's own invariants as static rules so the slop gate enforces them
on generated code with zero model calls:

- `run.py` files **must** be thin dispatchers (no inline framework boilerplate;
  must `import ... from runners.*`). A fat `run.py` is slop.
- No bare `export FORGE_PROVIDER=` in any shell script (constitution Article I.7).
- No absolute path above `FORGE_WORKSPACE` (sandbox, Article I.6).
- No hardcoded model id (must resolve via `llm_config.py`).
- No leaderboard/result write to `results/` root (judge.md guardrails).

## How it runs

`scripts/slop_scan.py` wraps the gate (and may shell out to `npx aislop scan
--json` when Node is available, falling back to its own bundled regex+AST checks so
it works fully offline/air-gapped). Per the autoresearch/aislop pattern:

1. **Scan** every generated deterministic file → a 0–100 score + a list of issues.
2. **Auto-fix the mechanical** (formatters, unused imports, dead code) in place.
3. **Hand off the rest** to the build agent with full diagnostic context — the
   agent fixes the issues that need judgement, then the file is re-scanned.
4. **Gate at 95.** The pass bar is **95**. `config.toml [quality].fail_below = 95`.
   A file (and the build) that scores **below 95 requires a rewrite** — not a
   patch, not a waiver. The file is regenerated from scratch and re-scanned until
   it reaches 95+. There is no "good enough below 95"; 95 is the floor for
   anything that ships.

## When it runs

- **Per file, at write time** (the aislop per-edit hook idea): right after the
  foundry writes any deterministic file, `slop_scan.py` runs on it; mechanical
  issues are auto-fixed, the rest handed back before moving on.
- **At build completion**: `verify_build.py` runs `slop_scan.py` across the whole
  workspace and records `results/_global/quality-<TS>.json`. A score **below 95**
  is an output-contract failure → **hard-halt and ask the user**, and the offending
  files must be rewritten (guardrails). The score is also a permanent build
  artifact (like aislop's badge); the badge only goes green at 95+.

## Why deterministic matters here

aislop's promise is "same code in, same score out" — no API calls, no flake. That
is exactly what the simplest-model directive needs: the quality bar is enforced by
pure static analysis, not by asking a model "is this good?". The model only writes
and fixes; the gate's verdict is mechanical and reproducible.

## Interaction with the golden suite and determinism

- The slop score is **not** the judge metric (that measures task performance); it
  is a separate code-health gate. Both must pass.
- A self-revision in the improvement loop (Phase 4.5) that lowers the slop score
  below baseline is rejected even if the judge metric improved — clean code is a
  floor, not a tradeable.
