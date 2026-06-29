# Output Guardrails — the "done" contract

Guardrails guarantee the **output ask**: every successful build produces a
complete, valid, schema-conforming foundry. The enforcer is the deterministic
`scripts/verify_build.py` (constitution Article I.9, Article V). A build may not
report success until it passes. **On any guardrail failure: hard-halt and ask the
user** — this is one of the only two halts in the skill.

These scripts are scaffolded **into the generated foundry workspace** (alongside
`agents/`, `judge/`, `results/`), so the contract travels with each build.

## The deliverable contract

`verify_build.py` checks every item. All are mandatory unless the task spec marks
an agent group absent.

### 1. Four agents + judge + leaderboard
- `agents/<group>/<short-name>/{langgraph,crewai,claude_sdk,subagent}/run.py` — all four present.
- `agents/<group>/<short-name>/subagent/<short-name>.md` — gated system prompt, valid YAML frontmatter.
- `judge/<group>/<short-name>/metric.json` + `score.py` — present and parseable.
- At least one `results/<group>/<short-name>/leaderboard-<TS>.{json,md}` — timestamped, never bare `leaderboard.json`.
- Each `results/runs/<run-id>/<framework>.json` carries `agent`, `run_id`, `metric_name`, `metric_value` (number), `raw_output_path`, `ts`.

### 2. Memory + evolution wiring
- EverOS store present at `memory/.everos/`; all four agents share one
  `project_id`/`app_id` and each has a distinct `agent_id`.
- `evolvers/skillopt/<agent>/` and `evolvers/skillclaw/` exist; SkillOpt's
  validation gate references the judge metric (not a second metric).

### 3. Self-review + analyze report
- `workspace/SELF_REVIEW.md` exists and is non-empty.
- `results/_global/analyze-<TS>.json` exists with `status: pass` (Phase 3.5).

### 4. Golden suite pass
- `tests/golden/<group>/<short-name>/golden.json` exists (the recorded baseline).
- `scripts/golden_run.py` exits 0 for every agent.

### 5. File completeness (every created file)
- `scripts/verify_files.py` exits 0: every file in the derived expected-set AND
  every entry in `workspace/BUILD_MANIFEST.json` exists with correct content
  (`references/file-verification.md`).
- The **`.claude/agents/<name>.md` registration** is checked explicitly — it must
  exist and resolve to the canonical subagent prompt. No more manually asking
  "was the agent registered?".
- **Exactly one registry.** The build fails if `agent-foundry/.claude/agents/`
  exists — that stray foundry-local registry must not be present; the only
  registry is the host repo root `.claude/agents/`.
- `results/_global/files-<TS>.json` exists with `status: pass`. Any missing or
  empty or malformed file hard-halts the build.

### 6. Determinism receipts
- For each AI artifact class (agent prompt, judge score, any self-revision) a
  determinism receipt exists under `results/_global/determinism/` with
  `verdict: deterministic` (or an accepted, recorded tolerance). See
  `references/determinism.md`.

### 7. Code-quality score ≥ 95
- `results/_global/quality-<TS>.json` exists with an overall score **≥ 95**
  (`references/code-quality-gate.md`). Every deterministic file scanned;
  per-file score also ≥ 95.
- A score below 95 is a hard failure: the offending files are **rewritten** (not
  patched) and re-scanned. The build cannot report "done" until the workspace
  scores 95+.

### 8. Config + sandbox integrity
- `config.toml [backend].provider == "auto"`; `python scripts/verify_llm_config.py` exits 0.
- No generated script writes or execs outside `FORGE_WORKSPACE` (static check:
  no absolute paths above the workspace, no bare `export FORGE_PROVIDER`).

## Schema mode (asked per build)

Phase 2 records `config.toml [guardrails].schema_mode`:

- `strict` — `verify_build.py` validates `metric.json`, `leaderboard.json`,
  `results/runs/*.json`, and `golden.json` against the JSON Schemas in
  `schemas/` (scaffolded into the workspace). Recommended; best for small models.
- `light` — presence + type/shape assertions only, no formal schema files.

If the user does not answer, default to `strict`.

## Failure behavior

```
run verify_build.py --phase <n>
if exit != 0:
    HARD-HALT
    show the user: which contract item failed, the file path, the expected vs actual
    ask: fix automatically (regenerate just that artifact) or hand-edit?
    re-run verify_build.py from the same phase
    # never advance, never report "done", never fabricate a passing result
```

`verify_build.py` runs at two points: as a **Phase-4 precondition**
(`--phase 4`, the four agents must exist and emit metrics before any leaderboard)
and at **build completion** (`--phase 6`, the full contract). It is also safe to
run standalone at any time (`forge verify`).

## What guardrails do NOT do

They do not judge quality (that is the judge's metric), do not pick a winner, and
do not auto-adopt fixes. They prove the build is **complete and well-formed**, then
hand control back to the user on any gap.
