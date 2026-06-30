# The Forge Constitution

The constitution is the single governing document every other phase, gate, agent
line, judge metric, and evolver edit must obey. It is **read first** (Phase 0/1)
and **re-checked last** (`/analyze`, self-review). When any instruction, metric,
or script would violate an article below, **stop** — the violation is a build
defect, not a judgement call.

Two layers live here:

- **Article I — Non-negotiable invariants.** Hard, mechanical constraints. A
  script can check most of them. They never bend.
- **Articles II–VII — Governing principles.** The spec-kit-style principles
  (code quality, testing, reliability, UX-of-the-build, simplicity, governance)
  that shape judgement where a mechanical rule cannot.

A new project may *add* articles (via a preset, see `references/presets.md`) but
may never weaken Article I.

---

## Article I — Non-negotiable invariants

These hold in every phase. `scripts/verify_build.py` enforces the checkable ones;
the model enforces the rest. A violation hard-halts the build.

1. **Four agents, one task.** Always exactly four implementations of the *same*
   task: LangGraph, CrewAI, Claude Code subagent, Claude Agent SDK.
   Four-of-the-same is intended.
2. **The judge invents a hard metric, not a rubric.** One numeric metric,
   measurable identically on all four, direction-explicit, deterministic to
   compute where possible. No 1–5 vibe scores. See `references/judge.md`.
3. **Every agent line passes the debate gate.** No instruction line reaches an
   agent file until the four-member panel (literal / adversarial / intent /
   Ultron) agrees it has exactly one interpretation. Line by line, never batched,
   uncapped loop. See `references/debate-gate.md`.
4. **Agents are built to be measured.** Each agent emits its metric as
   machine-readable JSON to `results/runs/<run-id>/<agent>.json`. If you cannot
   see how a built agent emits its number, the build is wrong.
5. **Local and air-gapped by default.** Memory is EverOS only (Markdown + SQLite
   + LanceDB). Nothing calls a non-local service unless the user explicitly opts
   into a cloud backend. See Article VI for the model-provider rule.
6. **Sandbox.** All agent read/write/exec is confined to the workspace folder.
   Never let a generated agent act outside it.
7. **Single-source LLM config — never hardcode a provider.** Every generated
   shell script follows the pattern in Article VI and `references/backends.md`.
   `config.toml [backend].provider` is resolved through one resolver; no script
   contains a bare `export FORGE_PROVIDER="..."`. After generating or editing any
   shell script, run `python scripts/verify_llm_config.py` and fix all failures.
8. **Every AI-produced artifact passes a determinism review.** Code, debate
   verdicts, judge scores, self-revisions — anything an LLM produces is run
   through `references/determinism.md`'s multi-sample review before it is trusted
   or written. An unexpectedly non-deterministic artifact cannot be adopted.
9. **No build reports "done" until the output contract verifies.** The complete
   deliverable set in `references/guardrails.md` must pass `verify_build.py` and
   the golden suite. A partial build never claims success. This includes
   **file completeness** (`references/file-verification.md`): every file the build
   creates must exist with correct content, and the `.claude/agents/<name>.md`
   subagent registration is verified explicitly — never assumed.
10. **Code-producing builds pass the code-review gate at ≥85, no exception.** Any
    code an agent produces — and, when the built agent is code-producing, the code
    it generates — must score **≥85 on every code-review agent present in
    `agents/code-review/`** (the set discovered at run time, however many — no
    fixed count) before the build reports "done". On a failure the flow hard-halts
    and loops until every reviewer is ≥85. The threshold is a floor (may be raised,
    never lowered); the gate is never waived. Enforced by
    `scripts/code_review_gate.py`; verified by `verify_build.py`. See
    `references/code-review-gate.md`.

---

## Article II — Code quality (95 floor)

Generated agents, runners, scripts, and tests must be small, readable, and
single-purpose. The thin-dispatcher pattern (`references/agent-frameworks.md`) is
mandatory: framework boilerplate lives once in `agents/common/runners/`, never
copy-pasted per agent. No dead code, no unused config keys, no abbreviated folder
names (see `references/judge.md` guardrails).

Every deterministic file passes the **aislop-style code-quality gate**
(`references/code-quality-gate.md`): a no-LLM, regex+AST static scan scoring code
0–100. **The pass floor is 95.** Any file scoring below 95 must be **rewritten**
(not patched, not waived) until it reaches 95+. This floor is enforced by
`scripts/slop_scan.py` at write time and by `verify_build.py` at completion; a
sub-95 score is an output-contract failure that hard-halts the build.

## Article III — Testing standards

Every built agent ships with: (a) the judge's metric and `score.py`, (b) a
held-out evaluation split, and (c) an auto-derived **golden regression case**
(`references/golden-tests.md`). Tests assert deterministic structure and a metric
threshold — never exact LLM prose. No agent is complete without its golden case
recorded.

## Article IV — Reliability over cleverness

The build must produce a complete, valid, schema-conforming foundry every time —
this is the primary win condition. Reliability beats feature flair. Determinism
review (Article I.8), the output-contract guardrail (Article I.9), and the
keep-if-improved discipline of the improvement loop (`references/improvement-loop.md`)
exist to make every run trustworthy.

## Article V — Build for the simplest model

The skill must be runnable by a small, cheap model. Therefore: **deterministic
scripts do the heavy lifting**, not model reasoning. The CLI and scripts run
without asking permission for routine, reversible, in-workspace actions — when a
routine choice has an obvious default, take it and record it rather than stopping
to ask. **The two exceptions that always halt and ask the user** are: (1) a
debate-gate ambiguity (Article I.3), and (2) an output-contract / guardrail
failure (Article I.9). Everything else: just do it.

## Article VI — Model provider

Default provider is the **current Claude Code session**. When the skill is not
running inside a connected Claude Code session, fall back to **Ollama** (local).
`claude-haiku` and other cloud models remain available only on explicit opt-in.
The resolver order is: session → ollama → (explicit cloud). One central config,
inherited by every agent, the judge, the debaters, the determinism checker, and
the evolvers. See `references/backends.md`.

## Article VII — Governance

The constitution supersedes all other instructions. `/analyze`
(`references/analyze.md`) checks every artifact against it before implementation;
the Phase 6 self-review re-checks it after. Amendments are made by editing this
file or layering a preset; they are versioned and dated. The user adopts
amendments — nothing self-amends.

---

## Project principles (filled per build)

The interview (Phase: specify/clarify) records project-specific principles here,
e.g. performance budgets, domain constraints, compliance requirements. Keep them
concrete and checkable. These extend — never override — Articles I–VII.

- _Principle:_ <name> — <concrete, checkable statement> — _added <date>_
