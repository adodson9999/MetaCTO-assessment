---
name: forge-agents
description: "Build four parallel implementations of the same task-agent (LangGraph, CrewAI, Claude Code subagent, Claude Agent SDK), plus a judge agent that invents a concrete numeric metric and ranks them on a leaderboard. Every line of every agent's instructions passes a four-member adversarial debate gate (literal / adversarial / intent / Ultron) before it is written, looping until exactly one interpretation survives. Wires the agents into a shared local EverOS memory pool and a SkillOpt + SkillClaw self-evolution loop. Use this skill whenever the user wants to forge agents, build a multi-framework agent comparison, create an agent arena, build the same agent in several frameworks and score them, set up a judged agent benchmark, or says 'forge agents', 'build me the four agents', 'compare frameworks on this task', or anything about building agents that must be measured against a hard metric. Trigger even when the user only describes the task and expects the four-agent + judge build implicitly."
---

# Forge Agents

You are an agent foundry. Given one task, you build **four implementations of that same task** — in LangGraph, CrewAI, a Claude Code subagent, and the Claude Agent SDK — plus a **judge agent** that invents a concrete numeric metric and ranks the four on a leaderboard. Every instruction line that defines any agent must survive a four-member debate gate before it is committed. Everything runs locally and air-gapped.

This SKILL.md is the control flow. Detailed specs live in `references/` — read the named file at each phase rather than guessing.

## Non-negotiable invariants

These hold in every phase. If any instruction you are about to write would violate one, stop.

1. **Four agents, one task.** Always exactly four implementations of the *same* task: LangGraph, CrewAI, Claude Code subagent, Claude Agent SDK. Four-of-the-same is intended.
2. **The judge invents a hard metric, not a rubric.** The judge defines a single numeric metric measurable on all four, measures it, and emits a leaderboard. No fuzzy scoring. See `references/judge.md`.
3. **Every agent line passes the debate gate.** No instruction line reaches an agent file until the four-member panel reaches consensus that it has exactly one interpretation. See `references/debate-gate.md`. This is the most important gate in the skill — never skip or batch it.
4. **Agents are built to be measured.** Each agent must emit its metric in an obvious, machine-readable way (structured JSON to `results/`). If you cannot see how a built agent would emit its number, the build is wrong.
5. **Local and air-gapped.** Memory is EverOS only (Markdown + SQLite + LanceDB on Ollama). Backend is swappable between Ollama and Claude Haiku via one central config. Nothing calls a non-local service unless the user explicitly opts into a cloud backend.
6. **Sandbox.** All agent read/write/exec is confined to the workspace folder. Never let a generated agent act outside it.

## Phases

Move through these in order. Phase 0 and Phase 1 set up the environment; Phases 2–6 run per task.

### Phase 0 — Integrate dependencies (call the existing `/scan-and-integrate` skill)

Before the first build, the three upstream repos must be present and verified. `/scan-and-integrate` is the user's **own separate skill** — this skill does not implement it. Invoke `/scan-and-integrate`, passing each repo URL and its stated purpose, and let that skill do the security scan, purpose verification, and vendored install into `vendor/`. The three repos and the purpose to pass for each:

- **EverMind-AI/EverOS** — local self-evolving agent memory (the shared memory pool).
- **microsoft/SkillOpt** — per-agent, validation-gated skill optimization (`best_skill.md`).
- **AMAP-ML/SkillClaw** — collective cross-agent skill evolution and sharing.

If `/scan-and-integrate` reports that a repo fails its security scan or purpose check, STOP and report to the user. Do not proceed to build against an unintegrated repo. After it finishes, record each pinned commit in `config.toml` `[vendor]`.

### Phase 1 — Scaffold the workspace

Run `scripts/init_workspace.py` to create the one self-contained workspace folder. Layout and rationale are in `references/architecture.md`. The folder contains `agents/`, `memory/`, `evolvers/`, `results/`, the shared EverOS store, the central `config.toml`, and the installer. Then run the installer (`scripts/install.sh` on macOS/Linux, `scripts/install.ps1` on Windows) for one-command setup.

**Location convention.** Scaffold the workspace **inside the host repository** — run `init_workspace.py` from the repo root so the foundry lands at `<repo>/agent-foundry/` (e.g. `assessment/MetaCTO-Assessment/agent-foundry/`). Everything the foundry needs is self-contained under that folder (its own `.venv`, `vendor/`, `scripts/`, `memory/.everos`), so it travels with the repo. Keep all foundry-internal paths **relative to `FORGE_WORKSPACE`** — never hardcode an absolute path — so the foundry can be relocated by a plain move. The one place an absolute path is unavoidable is the EverOS store root (`vendor/EverOS/.env` → `EVEROS_MEMORY__ROOT`); point it at `<workspace>/memory/.everos` and re-point it if the workspace moves. The Claude Code subagent built in Phase 3 must be registered at the host repo's `.claude/agents/` (see `references/agent-frameworks.md`).

### Phase 2 — Define the task (interactive interview)

Interview the user to pin down the task. Ask only what you cannot infer, one focused question at a time. You need: the task itself, its inputs, what a correct/good output looks like, and any constraints. Capture the result as `workspace/task_spec.md`. This interview is **separate** from the debate gate — here you gather the task; the gate governs the agent instruction lines you write afterward.

### Phase 2.5 — API Test Agent Quality Standards (apply only when task is API testing)

**Detection:** The task is API testing when the task spec describes generating test payloads for an HTTP endpoint's request body. If the task is not API testing, skip this entire phase. If it is, every standard in this section is mandatory — no line of any agent's instructions is finalized until it satisfies the debate gate AND every applicable standard below.

#### Scope delineation — three non-overlapping pipeline positions

The three API testing positions have strictly separate scopes. Never conflate them. Building one agent to do all three is a defect.

- **Structural payload agent (n299-class):** Generates 6 labeled output types — valid, inv_missing_required, inv_wrong_type, inv_extra_field, inv_all_null, inv_maxlength. Does NOT test boundary values or null/empty states.
- **Boundary value agent (n310-class):** Generates boundary point payloads only — numeric 9-point, boolean 2-point, string length 6-point, array size 4-point, plus all-minimum and all-maximum combination bodies. Does NOT test structural invalidity or null/empty states.
- **Null/empty state agent (n311-class):** Generates null and empty state payloads only — 7 states per required field, pairwise-null combinations, string-literal-null distinction, and optional-nullable checks. Does NOT test boundary values or structural invalidity.

#### Standard 1 — Coverage is ALL required fields, not a sample

Every agent that generates payloads targeting schema fields must iterate every required field in the schema. Generating one representative payload for one field and calling the scope covered is a defect. The agent instructions must say "For EACH field in REQUIRED_FIELDS" — not "for a required field" or "for one field at a time." Output arrays must have one entry per field (or per field × type combination where applicable). If the schema has 8 required fields, the output must reflect 8 required fields — not fewer.

#### Standard 2 — Output is labeled arrays, not flat single bodies

No agent in the API testing pipeline may emit a bare single payload body as its entire output for any invalid category. Every invalid category output must be an array of labeled objects. Each labeled object must carry at minimum: the field name it targets, the category label, and the body. The run.py wrapper iterates these arrays to execute each payload; a bare body cannot be iterated and will fail execution.

#### Standard 3 — The 9 WRONG_TYPE_VALUES with exact values (structural agents only)

When an agent generates wrong-type payloads, it must use exactly these 9 values and exactly these constant names. No substitutions, approximations, or reductions:

```
INT_VAL     = 42
FLOAT_VAL   = 3.14
BOOL_TRUE   = true
BOOL_FALSE  = false
STRING_VAL  = "wrong_type_string"
CHAR_VAL    = "x"
LIST_VAL    = [1, "a", true]
OBJECT_VAL  = {"key": "value"}
NULL_NONE   = null
```

**Type-match exclusion rule** — for a field with schema type T, skip any WRONG_TYPE_VALUE whose JSON type matches T exactly. The exclusions by schema type are:
- string field  → skip STRING_VAL and CHAR_VAL (both are strings)
- integer field → skip INT_VAL
- number field  → skip FLOAT_VAL and INT_VAL (integers are valid numbers)
- boolean field → skip BOOL_TRUE and BOOL_FALSE
- array field   → skip LIST_VAL
- object field  → skip OBJECT_VAL

Apply this exclusion per field, independently. An integer field gets 7 wrong-type payloads (9 minus INT_VAL=1). A string field gets 7 wrong-type payloads (9 minus STRING_VAL+CHAR_VAL=2). The agent instructions must enumerate the exact exclusion rules for each schema type — not summarize them as "skip matching types."

#### Standard 4 — inv_missing_required: exactly TWO variants per field (structural agents only)

For each required field, produce exactly two payloads:
1. `key_absent` — the field's key is completely removed from the JSON object
2. `key_present_null` — the field's key is present, value is JSON null

These are two distinct HTTP conditions that APIs validate differently at the parsing layer. The agent must not collapse them into one. Total array length for inv_missing_required = (count of REQUIRED_FIELDS) × 2.

#### Standard 5 — inv_extra_field: exactly 9 payloads, one per WRONG_TYPE_VALUE category (structural agents only)

The inv_extra_field array must contain exactly 9 objects — one per WRONG_TYPE_VALUE category in this fixed order: INT_VAL, FLOAT_VAL, BOOL_TRUE, BOOL_FALSE, STRING_VAL, CHAR_VAL, LIST_VAL, OBJECT_VAL, NULL_NONE. In every body, all documented fields are present and unchanged; the extra field added uses the key name "extra_field" with the category's value. No type-match exclusion applies to inv_extra_field — all 9 categories are always present.

#### Standard 6 — inv_maxlength: ALL constrained string fields, always an array (structural agents only)

The agent must identify every string field in the schema that has a maxLength constraint — not just the first one, not just a named field passed in as a parameter. The output is always an array even when only one string field has a maxLength constraint. If no string field has a maxLength constraint, the value is JSON null. Each array element: `{ "field": "<name>", "max_length": N, "value_length": N+1, "body": { ... } }` where the value in body is the ASCII letter "a" repeated exactly N+1 times.

#### Standard 7 — 7 null/empty states applied to ALL required fields (null/empty state agents only)

For each required field, produce payloads for all 7 states. All 7 states are applied to every required field regardless of the field's schema type. All 7 are expected to return HTTP 400:

```
1. KEY_ABSENT      — field key is completely removed from the JSON object
2. JSON_NULL       — field key is present, value is JSON null
3. EMPTY_STRING    — field key is present, value is "" (empty string, two double-quote characters)
4. INTEGER_ZERO    — field key is present, value is 0 (the integer zero)
5. BOOLEAN_FALSE   — field key is present, value is false (JSON boolean false)
6. EMPTY_ARRAY     — field key is present, value is [] (empty JSON array)
7. EMPTY_OBJECT    — field key is present, value is {} (empty JSON object)
```

Total inner state objects = N × 7. The agent instructions must list all 7 by name and exact value. "Null and empty variants" is not a valid substitute — all 7 must be named explicitly.

#### Standard 8 — Boundary point formulas with exact computations (boundary value agents only)

For numeric fields with both minimum M and maximum N (M < N), the agent must produce exactly these 9 labeled points using exactly these formulas:

```
MIN_MINUS_1        = M − 1                                → expected 400
MIN                = M                                    → expected 2xx
MIN_PLUS_1         = M + 1                                → expected 2xx
TEN_PCT_ABOVE_MIN  = floor(M + (N − M) × 0.10)           → expected 2xx
MIDPOINT           = floor((M + N) / 2)                   → expected 2xx
TEN_PCT_BELOW_MAX  = floor(N − (N − M) × 0.10)           → expected 2xx
MAX_MINUS_1        = N − 1                                → expected 2xx
MAX                = N                                    → expected 2xx
MAX_PLUS_1         = N + 1                                → expected 400
```

For fields with only minimum M (no maximum): produce MIN_MINUS_1, MIN, MIN_PLUS_1 only. For fields with only maximum N (no minimum): produce MAX_MINUS_1, MAX, MAX_PLUS_1 only. String boundary labels: UNDER_MIN_LENGTH, EMPTY, MIN_LENGTH, MID_LENGTH, MAX_LENGTH, OVER_MAX_LENGTH — omit any that are inapplicable given the constraints present. Array boundary labels: UNDER_MIN_ITEMS, MIN_ITEMS, MAX_ITEMS, OVER_MAX_ITEMS — omit inapplicable labels. The agent instructions must state the formula for each point by name, not say "test at boundaries."

#### Standard 9 — Explicit pass and fail thresholds per output category

Every agent in the API testing pipeline must have explicit pass and fail thresholds stated for each output category. The required metric form is: rate formula (numerator ÷ denominator × 100), exact pass threshold as a percentage, and exact fail condition stated as a specific event. "High accuracy" and "most payloads correct" are not acceptable. A metric that states pass but not fail (or fail but not pass) is incomplete and must be corrected before the agent line is finalized.

#### Standard 10 — Agents produce payloads only; run.py executes them

No API testing agent may send HTTP requests. The agent's sole job is to produce the labeled JSON payload structure. The paired run.py wrapper reads the agent's output, iterates over each labeled array, sends each body to the target endpoint, compares the actual HTTP response class to the "expected" field in each labeled object, and records results to `results/runs/<run-id>/<agent-name>.json`. Any agent instruction that says "send a request" or "call the endpoint" violates this separation and must fail the debate gate.

### Phase 3 — Author the four agents through the debate gate

For each of the four agents, draft its instruction set **one line at a time**, and pass every line through the debate gate before writing it. The full procedure — the four panel members, the consensus rule, the halt-and-ask behavior, and the uncapped loop — is in `references/debate-gate.md`. Read it now; do not improvise the gate.

As each agent's lines are finalized:
- Write the agent's system prompt into its `subagent/<agent-name>.md` file (YAML frontmatter + gated body). This is the canonical prompt artifact — there is no separate staging directory.
- Write a **thin dispatcher** `run.py` for each framework that delegates all framework boilerplate to the centralized runners in `agents/common/runners/`. See `references/agent-frameworks.md` for the thin dispatcher pattern.

All four agents share the same EverOS memory pool — see `references/memory-everos.md` for the shared-scope wiring (common `project_id`/`app_id`, per-agent `agent_id`).

### Phase 4 — Build the judge and run the four agents

Build the judge per `references/judge.md`: it invents one concrete numeric metric for this task, runs the four agents **in parallel** (`scripts/run_agents.py`), reads their emitted numbers, and writes a leaderboard (`results/leaderboard.md` + `results/leaderboard.json`). The judge tracks results over time so repeated runs show which framework is best at this task.

### Phase 5 — Wire self-evolution

Wire the agents into the evolution loop per `references/evolution.md`: SkillOpt sharpens each agent's own skill document behind a validation gate that uses the judge's metric; SkillClaw shares and collectively evolves skills across all agents in the folder. Evolution runs on a **nightly sleep cycle plus a manual trigger** (`/evolve`), staged for the user's review before adoption — never auto-adopted.

### Phase 6 — Self-questioning pass

As the final step, critique your own build. Read `references/self-review.md` and write `workspace/SELF_REVIEW.md`: gaps, weak spots, ambiguities that slipped through, fragile wiring, and concrete improvements. Report findings; do not auto-apply them. The user decides what to act on.

## Folder search

Whenever you search the workspace folder, use the hybrid pipeline in `scripts/hybrid_search.py`: a keyword leg (BM25/SQLite) and a meaning leg (EverOS embeddings/LanceDB) run in parallel, their results are fused with reciprocal-rank fusion, and a local reranker produces the final order. Never do a single-mode lookup.

## Backend switching

All components read one central backend config (`scripts/backend_config.py` + `config.toml`). The provider switch toggles between `ollama` and `claude-haiku` (`claude-haiku-4-5`), with a LiteLLM proxy as the universal OpenAI-compatible shim so even SkillClaw and EverOS's OpenAI path accept Claude. Swapping models is a one-line change; every agent, the judge, the debaters, and the evolvers inherit it.
