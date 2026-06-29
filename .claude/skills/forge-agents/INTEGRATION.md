# Forge-Agents v2 — Integration & Roadmap

This update folds five external references into forge-agents and adds the two asks
(output guardrails, golden regression suite). Everything you selected across the
20-question interview is included.

## Source repos and what each contributed

| Source | What forge borrowed | Where it lives |
|--------|---------------------|----------------|
| **github/spec-kit** | Phase vocabulary (constitution → specify → clarify → plan → tasks → analyze → checklist → implement), a constitution file, the `/analyze` gate, presets/extensions/overrides layering, a thin CLI | `SKILL.md`, `references/constitution.md`, `references/analyze.md`, `references/presets.md`, `references/cli.md` |
| **hknio/qan-nondeterministic-ai-agent** | Multi-run non-determinism detection (generate → run N times → compare → review) as a universal wrapper on every AI action | `references/determinism.md`, `scripts/determinism_check.py` |
| **karpathy/autoresearch** | Keep-if-improved hill-climb: propose → run fixed budget → keep only if metric improves → repeat (the 10-round tournament) | `references/improvement-loop.md`, `scripts/improve_loop.py` |
| **scanaislop/aislop** | Deterministic (regex + AST, no LLM) code-quality gate scoring 0–100; **95 floor**, rewrite below | `references/code-quality-gate.md`, `scripts/slop_scan.py` |
| **(the two asks)** | Output-contract guardrails + golden regression suite | `references/guardrails.md`, `references/golden-tests.md`, `scripts/verify_build.py`, `scripts/golden_run.py` |

## New phase model (SKILL.md)

```
0  read constitution + integrate deps (/scan-and-integrate)
1  scaffold workspace (default session->ollama backend)
2  specify (task interview) + ask schema-strictness
2.2 data-input (optional): ingest data, find patterns -> spec     [NEW]
2.5 API-testing standards (when applicable)
3  author 4 agents — debate gate + determinism review + 95 quality gate per line/file
3.5 /analyze cross-artifact consistency gate                       [NEW]
4  build judge + run 4 in parallel  (verify_build --phase 4 precondition)
4.5 10-round keep-if-improved tournament -> golden baseline        [NEW]
5  wire SkillOpt/SkillClaw (golden-gated adoption)
6  verify_build (contract) + golden suite + self-review  = "done"  [NEW gates]
```

## The four gates (every build passes all four)

1. **Debate gate** (existing) — every instruction line has exactly one interpretation.
2. **Determinism review** (new) — every AI artifact is stable across N samples.
3. **Code-quality gate** (new) — every deterministic file scores ≥ 95 or is rewritten.
4. **Output-contract guardrail** (new) — the full deliverable set verifies before "done".

Plus the **golden suite** (regression) and **/analyze** (consistency) as build-completion / pre-judge gates.

## Design principles locked in from the interview

- **Built for the simplest model.** Deterministic stdlib scripts do the work; the
  model orchestrates. CLI/scripts run without permission prompts for routine,
  reversible, in-workspace actions.
- **Only two halts.** A debate-gate ambiguity, or an output-contract/guardrail
  failure (which now includes a sub-95 quality score). Everything else: just do it.
- **Backend default:** current Claude Code session → Ollama fallback → explicit
  cloud opt-in. Never hardcoded.
- **95 is the floor.** Code below 95 on the aislop-style gate is rewritten, not patched.

## Known cleanup (flagged, not yet done)

- **Double-nesting.** The installed skill currently nests as
  `.claude/skills/forge-agents/forge-agents/` with a second stray `SKILL.md` at the
  outer level whose relative `references/` links are broken. Canonical content
  should sit directly under `.claude/skills/forge-agents/`. This package is laid
  out flat (correct) — install it at the skill root (see INSTALL.md).
- Schemas (`schemas/*.json`) referenced by `verify_build.py --strict` are scaffolded
  by `init_workspace.py`; add formal JSON Schemas there when `schema_mode = strict`.

## Files in this package

```
SKILL.md
INTEGRATION.md  (this file)
INSTALL.md
references/
  constitution.md          api-testing-standards.md   guardrails.md
  determinism.md           analyze.md                 golden-tests.md
  improvement-loop.md      data-input.md              presets.md
  backends.md              cli.md                     code-quality-gate.md
  (existing: debate-gate.md, judge.md, evolution.md, architecture.md,
             agent-frameworks.md, memory-everos.md, self-review.md)
scripts/
  slop_scan.py  verify_build.py  determinism_check.py  golden_run.py
  analyze.py    improve_loop.py  forge.py
  (existing: init_workspace.py, run_agents.py, judge_score.py, debate_gate.py,
             self_review.py, backend_config.py, hybrid_search.py, llm_config.py,
             verify_llm_config.py, install.sh, install.ps1, requirements.txt)
```
