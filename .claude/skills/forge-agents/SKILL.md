---
name: forge-agents
description: "Build four parallel implementations of the same task-agent (LangGraph, CrewAI, Claude Code subagent, Claude Agent SDK), plus a judge agent that invents a concrete numeric metric and ranks them on a leaderboard. Runs a spec-driven pipeline (constitution -> specify -> clarify -> optional data-input -> plan -> tasks -> analyze -> checklist -> implement) where every agent instruction line passes a four-member adversarial debate gate, every AI-produced artifact passes a determinism review, each agent self-improves across a 10-round keep-if-improved tournament against the judge, and the whole build must satisfy a verified output contract plus an auto-derived golden regression suite before it can report done. Wires the agents into a shared local EverOS memory pool and a SkillOpt + SkillClaw self-evolution loop. Use this skill whenever the user wants to forge agents, build a multi-framework agent comparison, create an agent arena, build the same agent in several frameworks and score them, set up a judged agent benchmark, or says 'forge agents', 'build me the four agents', 'compare frameworks on this task', or anything about building agents that must be measured against a hard metric. Trigger even when the user only describes the task and expects the four-agent + judge build implicitly."
---

# Forge Agents

You are an agent foundry. Given one task, you build **four implementations of that
same task** — in LangGraph, CrewAI, a Claude Code subagent, and the Claude Agent
SDK — plus a **judge agent** that invents a concrete numeric metric and ranks the
four on a leaderboard. Every instruction line survives a four-member debate gate,
every AI-produced artifact survives a determinism review, each agent self-improves
across a 10-round tournament against the judge, and nothing ships until a verified
output contract and a golden regression suite both pass. Everything runs locally.

This SKILL.md is the **control flow**. Detailed specs live in `references/` — read
the named file at each phase rather than guessing. The governing document is
`references/constitution.md`; read it first and obey it everywhere.

## How this maps to spec-kit (and goes past it)

Forge runs the full spec-kit phase vocabulary, with forge's rigor layered on and
one extra phase (**data-input**) for pattern-finding over user data:

| spec-kit            | forge phase                                  | forge adds |
|---------------------|----------------------------------------------|------------|
| constitution        | Phase 0–1 (read constitution, scaffold)      | 7 hard invariants inside the constitution |
| specify             | Phase 2 (task interview)                      | task_spec captured per agent |
| clarify             | Phase 2 + debate gate                         | per-line adversarial clarification, uncapped |
| _(none)_            | **Phase 2.2 — data-input (optional)**         | ingest user data, identify patterns, feed the spec |
| plan                | Phase 2.5 + Phase 3 authoring                 | API-testing quality standards |
| tasks               | Phase 3 (per-agent line drafting)             | debate gate + determinism review per line |
| analyze             | **Phase 3.5 — /analyze cross-artifact gate**  | constitution + spec + metric consistency |
| checklist           | Phase 6 self-review + golden suite            | "unit tests for English" plus real regression tests |
| checklist           | **Phase 6.5 — code-review gate**             | every reviewer in agents/code-review/ ≥85 over all created/produced code |
| implement           | Phase 4 (judge + run) + Phase 4.5 (improve)   | hard metric, 10-round keep-if-improved loop |

Customization (presets / extensions / overrides) is in `references/presets.md`.
The thin `forge` CLI surface is in `references/cli.md`.

## Operating principle — built for the simplest model

Deterministic scripts do the heavy lifting; the model orchestrates. For routine,
reversible, in-workspace actions the CLI and scripts **just run** — no permission
prompts, obvious defaults taken and recorded. **Only two things halt and ask the
user:** (1) a debate-gate ambiguity, (2) an output-contract/guardrail failure.
See constitution Article V.

Every deterministic file the foundry writes also passes an **aislop-style
code-quality gate** (`references/code-quality-gate.md`): a no-LLM, regex+AST static
scan that scores the code 0–100, auto-fixes mechanical slop, and rejects anything
below the baseline. "Same code in, same score out" — the quality bar is mechanical,
not a model judgement, which is exactly what the simplest-model directive needs.

## Non-negotiable invariants

The 7 original invariants are now **Article I of the constitution**
(`references/constitution.md`) — read them there. They are unchanged in force; if
any instruction you are about to write would violate one, stop. Two invariants
were added (constitution Article I.8–I.9): **every AI artifact passes a
determinism review**, and **no build reports done until the output contract
verifies**.

## Phases

Move through these in order. Phase 0–1 set up the environment; Phases 2–6 run per
task. Each phase that produces an AI artifact ends by running the determinism
review (`references/determinism.md`).

### Phase 0 — Read the constitution, integrate dependencies

Read `references/constitution.md` in full. Then integrate the three upstream repos
via the user's **own** `/scan-and-integrate` skill — this skill does not implement
it. Pass each repo URL and purpose; let that skill do the security scan, purpose
verification, and vendored install into `vendor/`:

- **EverMind-AI/EverOS** — local self-evolving agent memory (the shared pool).
- **microsoft/SkillOpt** — per-agent, validation-gated skill optimization.
- **AMAP-ML/SkillClaw** — collective cross-agent skill evolution and sharing.

If `/scan-and-integrate` reports a failure, STOP and report. Record each pinned
commit in `config.toml [vendor]`.

### Phase 1 — Scaffold the workspace

Run `scripts/init_workspace.py` to create the one self-contained workspace folder.
Layout is in `references/architecture.md`. It contains `agents/`, `judge/`,
`memory/`, `evolvers/`, `results/`, `tests/golden/`, the guardrail/determinism
scripts, the central `config.toml`, and the installer. Then run the installer
(`scripts/install.sh` / `install.ps1`).

**Location convention.** Scaffold **inside the host repository** so the foundry
lands at `<repo>/agent-foundry/`. Keep all foundry-internal paths relative to
`FORGE_WORKSPACE`. The Claude Code subagent is registered at the host repo's
`.claude/agents/` (see `references/agent-frameworks.md`).

**Backend default.** `config.toml [backend].provider = "auto"`, resolving
**current Claude Code session → Ollama → explicit cloud** (constitution
Article VI, `references/backends.md`). Never hardcode a provider.

### Phase 2 — Specify the task (interactive interview)

Interview the user to pin down the task: the task itself, its inputs, what a
correct/good output looks like, and constraints. Ask only what you cannot infer,
one focused question at a time. Capture `workspace/task_spec.md`. Record any
project-specific principles into the constitution's "Project principles" section.
This interview is **separate** from the debate gate.

Also ask the **schema-strictness question** here (per build): should the judge's
emitted artifacts be validated against formal JSON Schemas, or by lighter
presence/shape checks? Record the answer in `config.toml [guardrails].schema_mode`
(`strict` | `light`); `verify_build.py` reads it. See `references/guardrails.md`.

### Phase 2.2 — Data input (optional)

If the user supplies data for the agent to learn from, run this phase; otherwise
skip it. Ingest the data, identify the patterns relevant to the task, and fold the
findings into `task_spec.md` (and the judge's metric design). Full procedure,
sandbox rules, and pattern-report format are in `references/data-input.md`. The
pattern report itself is an AI artifact and gets a determinism review.

### Phase 2.5 — API Test Agent Quality Standards (apply only when task is API testing)

**Detection:** the task is API testing when the spec describes generating test
payloads for an HTTP endpoint's request body. If not, skip this phase. If it is,
every standard in `references/api-testing-standards.md` is mandatory and each
agent line must satisfy the debate gate AND every applicable standard. (The ten
standards — scope delineation, all-required-fields coverage, labeled arrays, the
9 WRONG_TYPE_VALUES, the two missing-required variants, inv_extra_field,
inv_maxlength, the 7 null/empty states, boundary formulas, explicit thresholds,
payloads-only — are unchanged from the prior version and now live in that
reference.)

### Phase 3 — Author the four agents through the debate gate

For each of the four agents, draft its instruction set **one line at a time** and
pass every line through the debate gate before writing it. Read
`references/debate-gate.md` now; do not improvise the gate. As each agent's lines
are finalized:

- Write the gated system prompt into `agents/<agent-name>/subagent/<agent-name>.md`
  (YAML frontmatter + gated body). This is the canonical prompt artifact.
- Write a **thin dispatcher** `run.py` per framework that delegates to the
  centralized runners in `agents/common/runners/`. See `references/agent-frameworks.md`.
- After each agent's prompt is complete, run the **determinism review**
  (`references/determinism.md`) on it — re-generate the gated lines N times and
  confirm they converge. A non-deterministic prompt cannot be adopted.
- Immediately after writing any deterministic file (`run.py`, runners, `score.py`,
  scripts), run the **code-quality gate** (`scripts/slop_scan.py`,
  `references/code-quality-gate.md`): auto-fix mechanical slop in place, hand the
  rest back, and re-scan until the file clears the baseline score.
- **Code-review gate (Article I.10) on every code file, all four frameworks.** Each
  `run.py` you author — LangGraph, CrewAI, Claude Code subagent, and Claude Agent SDK —
  and any other code it produces, must pass `scripts/code_review_gate.py`: every
  reviewer discovered in `agents/code-review/` (however many, no fixed count) scores
  ≥85. This holds at **every point** code is created; no framework is exempt. On any
  sub-85: hard-halt, show the reviewer notes, rewrite (never waive, never lower), and
  re-run the full reviewer set until all four frameworks' code is ≥85 on every lens.
  See `references/code-review-gate.md`.

All four agents share the same EverOS memory pool — see `references/memory-everos.md`.

Every agent's system prompt (all four frameworks) must state, in its own words, that
**all code it creates will be reviewed by every agent in `agents/code-review/` and
must score ≥85 on each, no exception, looping until it does** — pointing at
`agents/code-review/` and the shared memory so the agent knows the standard before it
writes a line. See `references/agent-frameworks.md` (self-awareness clause).

### Phase 3.5 — Analyze (cross-artifact consistency gate)

Before building the judge, run `/analyze` (`scripts/analyze.py`,
`references/analyze.md`). It checks that `task_spec.md`, the four agent prompts,
the judge metric design, and the constitution all agree — no contradictions, no
orphaned requirements, no metric that can't be computed from what the agents emit.
On a contradiction it **hard-halts and asks the user** (constitution Article V
exception 2). This is additive to, not a replacement for, the Phase 6 self-review.

### Phase 4 — Build the judge and run the four agents

Build the judge per `references/judge.md`: invent one concrete numeric metric,
create the judge subfolder (`judge/<group>/<agent-short-name>/metric.json` +
`score.py`) **before** running, then run the four agents **in parallel**
(`scripts/run_agents.py`) and write a timestamped leaderboard.

**Phase-4 precondition (guardrail).** `verify_build.py --phase 4` must pass first:
all four agents exist and each emits a machine-readable metric. No leaderboard is
ever produced from a partial field of four.

**Code-review gate on the judge.** The judge's `score.py` and any code it generates
are code targets too: they must pass `scripts/code_review_gate.py` at ≥85 on every
reviewer discovered in `agents/code-review/` before the judge is used. Same hard-halt
-and-loop rule as the four frameworks — the judge is not exempt (Article I.10).

### Phase 4.5 — Improvement tournament (10 rounds)

Run the keep-if-improved tournament in `references/improvement-loop.md`. For each
agent, repeat 10 rounds: the agent runs against the judge, proposes a bounded
self-revision, the revision passes the **same full pipeline** (debate gate +
determinism review + 95 quality gate + the **code-review gate at ≥85 on every
reviewer in `agents/code-review/`**), and is **kept only if the judge score
improves** (else discarded and the round retried), in the style of autoresearch.
A self-revision that drops any reviewed file below 85 on any lens is rejected exactly
like a metric regression — this holds for **every** revision, in all four frameworks
and the judge (Article I.10). Track the score trajectory. The post-loop best score
per agent becomes the **golden baseline**.

**Per-framework mode (fight-camp).** When the user wants each framework to improve
**independently** — evolving its own divergent prompt because a prompt that wins for
one framework may lose for another — run the separate **`fight-camp`** skill. It
runs four sealed experiments (LangGraph, CrewAI, Claude Agent SDK, Claude Code
subagent), each keep-if-improved against the same judge/metric/budget, and writes
each framework's best prompt back into its agent. Same task and metric across all
four (fair comparison); only the prompt diverges. Trigger: `/fight-camp`.

### Phase 5 — Wire self-evolution

Wire the agents into the evolution loop per `references/evolution.md`: SkillOpt
sharpens each agent's skill behind the judge-metric validation gate; SkillClaw
shares and collectively evolves skills across all agents. Evolution runs nightly
plus a manual trigger (`/evolve`), staged for review — never auto-adopted. Any
SkillOpt edit also re-runs the **golden suite** and is rejected if it regresses
the baseline.

### Phase 6 — Verify, self-review, and golden suite (build completion)

The build is not "done" until all three pass, in order:

1. **Output contract** — `scripts/verify_build.py` validates the full deliverable
   set (`references/guardrails.md`), including **file completeness**
   (`scripts/verify_files.py`, `references/file-verification.md`): every created
   file exists with correct content, and the `.claude/agents/<name>.md`
   registration is confirmed explicitly so you never have to ask whether the agent
   was registered. On any failure: **hard-halt and ask the user**.
2. **Golden regression suite** — `scripts/golden_run.py` runs the per-agent
   auto-derived golden cases (`references/golden-tests.md`). Pass =
   judge metric ≥ baseline (minus tolerance) AND deterministic structure matches.
   On regression: hard-halt and report which case/agent regressed.
3. **Self-questioning pass** — read `references/self-review.md`, write
   `workspace/SELF_REVIEW.md` (gaps, residual ambiguities, fragile wiring,
   determinism findings, concrete improvements). Report; do not auto-apply.
4. **Code-review gate (Phase 6.5).** `scripts/code_review_gate.py --agent <group>/<name>`
   discovers and runs every reviewer in `agents/code-review/` over every code file
   the build created (and the agent's produced code when code-producing). Pass =
   every target ≥85 on every discovered reviewer. On any sub-85: hard-halt, show the
   reviewer notes, rewrite, loop until all ≥85. See `references/code-review-gate.md`.

Only after 1–4 pass may the build report success.

## Folder search

Whenever you search the workspace folder, use `scripts/hybrid_search.py`: a keyword
leg (BM25/SQLite) and a meaning leg (EverOS embeddings/LanceDB) run in parallel,
fused with reciprocal-rank fusion, then locally reranked. Never single-mode.

## Backend switching

All components read one central backend config (`scripts/backend_config.py` +
`config.toml`) resolved by `scripts/llm_config.py`. Default order: **current
Claude Code session → Ollama → explicit cloud** (e.g. `claude-haiku-4-5` on
opt-in), with a LiteLLM proxy as the universal OpenAI-compatible shim. Swapping
the model is a one-line change inherited by every agent, the judge, the debaters,
the determinism checker, and the evolvers. See `references/backends.md`.
