# Task Spec — API CI/CD Pipeline Runner

> Position **general**, workflow **run-cicd-pipeline** ("CI/CD Pipeline Runner").
> Captured in Phase 2 of forge-agents. This is the single task all four agents
> (LangGraph, CrewAI, Claude Code subagent, Claude Agent SDK) implement, and the basis
> for the judge's numeric metric. Coexists with the other foundry builds.
> **Backend = Ollama** (`ollama`, local / air-gapped) per the build request — the
> foundry's global default. **The Ollama server is NEVER started by this build** (the
> agent is forbidden from starting it; the phase-4 script only probes it read-only and
> exits if it is down). **DummyJSON is never touched** — this task has no DummyJSON
> surface.

## The task

A CI/CD pipeline runner reads a build manifest, installs Ollama in the CI runner,
pulls the configured model, starts the Ollama server, spawns every enabled agent as a
subprocess pointed at the Ollama backend in parallel batches of 4, captures each
agent's stdout/stderr to separate files, and **exits the pipeline with code 1 if any
agent exits non-zero or emits stdout that does not parse as valid JSON** — blocking
deployment in every such case.

That task splits into two halves:

- **The deterministic half** — install Ollama (`curl … | sh`), `ollama --version`,
  `ollama pull`, `ollama list`, `ollama serve`, the `/api/tags` health check, spawning
  `agents/run_agent.py` subprocesses in batches of 4, the 300 s per-agent timeout +
  SIGTERM, PID management, `kill`, the pipeline exit code, and blocking deployment — is
  the **CI harness / runner's** job, **not the agent's**. The agent is debate-gated
  against performing any of it (gated line L12).
- **The analytical half — the agent's role** — given one pipeline run's captured
  artifacts (the `[backend]` config block, the `manifest.json` agent array, and each
  listed agent's `exit_code` / `timed_out` / captured `stdout`), classify every
  **enabled** agent and emit the exact **ten-field `pipeline-summary.json`**.

One pipeline run in → one structured pipeline-summary out → one scored field set. A
separate deterministic program reads the agent's summary and sets the pipeline exit
code (`agents_failed > 0` ⇒ exit 1, block deployment; `0` ⇒ exit 0, allow).

### The classification contract (the exact algorithm the agent reproduces)

```
ENABLED        = manifest objects whose `enabled` is literally true
                 (enabled=false or missing-enabled objects are excluded entirely)
agents_total   = count of ENABLED
per enabled agent, FIRST MATCH WINS:
  1. TIMED_OUT  if timed_out is true OR exit_code == 124
  2. MALFORMED  else if json.loads(full stdout) raises  (empty/whitespace == malformed)
  3. FAILED     else if exit_code != 0
  4. PASSED     else (exit_code == 0 AND stdout parses as JSON)
agents_passed  = |PASSED|
agents_failed  = |FAILED| + |MALFORMED| + |TIMED_OUT|   (the three buckets PARTITION
                 the non-passing enabled agents — no agent in two buckets)
```

The ten emitted fields (task-mandated names): `run_id`, `model`, `model_digest`,
`agents_total`, `agents_passed`, `agents_failed`, `failed_agents` (list of names),
`malformed_agents` (list of names), `timed_out_agents` (list of names), `timestamp`.

### Phase-2 disambiguation (recorded in the debate gate)

The task's prose (step 7) parses stdout **first** and only then looks at the exit code,
while step 6 records TIMED_OUT separately — leaving the **timed-out-AND-unparseable**
agent classifiable into two buckets, which would double-charge `agents_failed`. The
debate gate (lines L5–L6) pins an explicit **first-match precedence
`TIMED_OUT > MALFORMED > FAILED > PASSED`** with **mutually-exclusive** failure buckets,
so every enabled agent lands in exactly one category and `agents_failed` is a clean sum.

## Target / inputs — Phase-2 fork (fixtures)

The task's real inputs (a manifest + captured agent stdout/stderr from a live CI run)
are **local, air-gapped fixtures** under `data/run-cicd-pipeline/scenarios/<scenario>/`
(a `manifest.json` + per-agent `stdout/<name>.stdout.txt` + an `exec.json` carrying exit
codes / timed-out flags / backend block / digest / run id / timestamp), one scenario per
classification shape. `build_gold.py` materialises these and derives the gold summary.

| scenario                    | enabled | shape                                                                   | pass rate | block? |
|-----------------------------|--------:|-------------------------------------------------------------------------|-----------|--------|
| clean_all_pass              | 4 (+1 disabled) | all pass; a disabled agent present and excluded                 | 100%      | no     |
| mixed_batch                 | 6       | 1 FAILED(exit 1), 1 FAILED(exit 2), 1 MALFORMED, 1 TIMED_OUT, 2 pass     | 33.33%    | yes    |
| disabled_and_empty_stdout   | 3 (+2 disabled)  | 1 MALFORMED (exit 0, empty stdout), 2 pass                      | 66.67%    | yes    |
| timeout_precedence          | 4       | 1 TIMED_OUT (exit 124 + empty stdout → TIMED_OUT, not MALFORMED), 1 FAILED, 2 pass | 50% | yes    |

The **"start Ollama + GET /api/tags == 200"** step (How step 4) is honored by the
harness probing the **live local Ollama `/api/tags`** read-only before scoring — and
**only probing**: this build never starts the server.

## Tooling mapping

The task names the Ollama CLI (`ollama pull/serve/list/--version`), curl (the
`/api/tags` health check), Python `subprocess` / `json` / `pathlib`,
`agents/manifest.json`, `config.toml`, and a GitHub Actions / GitLab CI / Jenkins
runner. The agent is **reporter-agnostic over captured artifacts**: it parses the
manifest + per-agent execution records; the harness plays every CI-orchestration role
(install, serve, spawn, timeout, exit code, leaderboard as the "dashboard", EverOS note
as history). No external SaaS is contacted — air-gapped.

## Metric

- **Task gate metric — Pipeline Agent Pass Rate** = (enabled agents that exit 0 **and**
  whose stdout parses as valid JSON ÷ total enabled agents) × 100. **Pass = exactly
  100%**; **Fail = any value < 100%** (a single failed / malformed / timed-out agent
  sets `FAIL_COUNT > 0`, exits the pipeline with code 1, and blocks deployment, no
  tolerance). TIMED_OUT agents count as failures. This is a property of the scenario
  fixtures (100% / 33.33% / 66.67% / 50%), so the genuine finding is **which pipeline
  runs must be blocked**: mixed_batch, disabled_and_empty_stdout, timeout_precedence
  (clean_all_pass may deploy).

- **Forge ranking metric — Pipeline-Summary Fidelity** = % of (scenario × field) cells
  where the agent's emitted summary matches the deterministic gold summary
  (denominator = 4 × 10 = 40). Because the task is deterministic and the prompt is
  tightly debate-gated, correctness saturates; the leaderboard breaks ties with
  **report_conformance** (raw structural exactness — exactly ten keys, native-int
  counts, ordered string arrays, partitioned failure buckets) → **tokens** →
  **elapsed**. See `judge/run-cicd-pipeline/metric.json`.

## Outputs

- Agents: `results/runs/<run-id>/<agent>.json` (+ `.cases.json` with per-scenario detail).
- Judge: `results/leaderboard-run-cicd-pipeline.{json,md}`.
- Gold: `data/run-cicd-pipeline/gold.json` (+ `gold/<scenario>.json`).

## Constraints

- **Backend = Ollama** (local / air-gapped), via `FORGE_PROVIDER=ollama` (the global
  default). The four agents reach Ollama through its native OpenAI-compatible `/v1`
  endpoint.
- **The Ollama server is never started** by this build — the agent is forbidden from
  starting/installing/serving anything, and the phase-4 script only probes `/api/tags`
  read-only and exits if Ollama is down.
- **DummyJSON untouched** — this task has no DummyJSON surface.
- **Sandboxed** — all agent I/O inside `FORGE_WORKSPACE`.
- **Air-gapped** — no non-local service is contacted.
