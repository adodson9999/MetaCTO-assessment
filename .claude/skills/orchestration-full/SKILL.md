---
name: orchestration-full
description: >
  Run all 40 API tester agents plus the 3 general agents (bug-reporter, run-cicd-pipeline,
  test-case-creator) against every DummyJSON endpoint unconditionally — no change detection,
  no scoping. Every endpoint is tested from scratch regardless of prior run history.
  Use when you want a complete ground-truth test run. Trigger with "orchestration-full",
  "run full orchestration", "test everything", or "run all agents on all endpoints".
allowed-tools:
  - Bash
  - Read
  - Write
  - Edit
  - Glob
  - Grep
  - WebFetch
  - Agent
---

# orchestration-full

Complete unconditional test run. Every endpoint × every agent × every step. No skipping,
no scoping, no change detection. This is the ground-truth run.

---

## Non-negotiable invariants

These hold in every phase without exception. If any instruction you are about to execute
would violate one, stop and surface the violation before proceeding.

1. **Every step produces a test case.** The test-case-creator is called after every single
   step an agent executes — not after the agent completes, but after each individual step.
   A run that produces zero test cases for a step is a broken run.

2. **Every API call produces a Postman item.** The moment any agent makes an HTTP call,
   the postman-collection agent is called immediately with that call's details and the
   tc_id of the step that triggered it. The Postman item name must exactly match the tc_id.

3. **Every bug triggers live capture + reproduction.** When any agent reports a bug, the
   bug reporter begins capturing immediately. The original agent pauses, reproduces the
   failing steps in the same order, ffmpeg records the terminal during reproduction, then
   the bug reporter finalizes the report. Only after the report is written does the original
   agent continue its remaining steps.

4. **"Code Update" means exactly that — nothing else.** A test case for a step that requires
   a code change is labeled "Code Update". No bug report. No pass/fail. No blocking.
   The agent continues to the next step immediately.

5. **Agents run sequentially within an endpoint.** Agent n+1 does not start until agent n
   has completed all its steps and all per-step side effects (test-case-creator, postman
   agent, bug reporter if triggered).

6. **Endpoints run sequentially.** Endpoint n+1 does not start until endpoint n is fully
   complete — all 40 API tester agents + 3 general agents finished, all outputs written,
   state file updated.

7. **All 40 API tester agents run on every endpoint.** No agent is skipped based on
   perceived relevance. An agent whose behavior doesn't apply to an endpoint produces
   "Code Update" labeled test cases — it still runs.

8. **The 3 general agents always run after the 40 API tester agents, per endpoint.**
   Order: test-case-creator final sweep → run-cicd-pipeline → bug-reporter sweep.

9. **State is written after every agent completes.** `results/runs/[RUN_ID]/orchestration-state.json`
   is updated immediately after each agent finishes so an interrupted run can resume from
   the last completed agent without re-running completed work.

10. **No output is discarded.** Every agent's stdout and stderr are written to
    `results/runs/[RUN_ID]/agents/[AGENT_NAME]/[ENDPOINT_ID]-stdout.txt` and
    `results/runs/[RUN_ID]/agents/[AGENT_NAME]/[ENDPOINT_ID]-stderr.txt`.

---

## Phase 0 — Bootstrap

### 0a. Detect environment

```bash
if [ -n "$CLAUDE_CODE_SESSION" ] || command -v claude >/dev/null 2>&1; then
  ENV_MODE="claude-code"
else
  ENV_MODE="ollama"
fi
echo "ENV_MODE=$ENV_MODE"
```

Record ENV_MODE. All subsequent agent invocations use this mode:
- `claude-code` → invoke agents as Claude Code subagents via the Agent tool
- `ollama` → invoke agents via `ollama run [model] < [agent-spec-path]` using the model
  configured in `config.toml [backend].model`

### 0b. Verify prerequisites

```bash
# results/ structure
mkdir -p results/runs results/bug-reports/screenshots results/bug-reports/recordings \
         results/bug-reports/logs results/bug-reports/db-dumps

# ffmpeg required for screen recording
if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "ERROR: ffmpeg not found. Install with: brew install ffmpeg"
  exit 1
fi

# knowledge graph must exist
if [ ! -f ".understand-anything/knowledge-graph.json" ]; then
  echo "ERROR: .understand-anything/knowledge-graph.json not found."
  echo "Run /understand first to generate the knowledge graph."
  exit 1
fi

# config.toml must exist
if [ ! -f "config.toml" ]; then
  echo "ERROR: config.toml not found."
  exit 1
fi
```

### 0b-i. Write .understandignore

Before any `/understand` or `/understand-diff` call can occur — in this run or any
subsequent run — the AI agent directories and run outputs must be excluded. Write
(or merge into) `.understandignore` at the project root now, during bootstrap, so
the ignore rules are always in place regardless of how `/understand` is invoked:

```bash
cat > .understandignore << 'EOF'
# AI agent implementations — excluded from understand analysis
agents/
agents/api-tester/
agents/general/

# Orchestration run outputs — change every run, not meaningful to analyze
results/
results/runs/
results/bug-reports/
results/postman-collection.json
results/test-case-registry.json
results/test-case-registry-summary.json

# Understand Anything own intermediate files
.understand-anything/intermediate/
.understand-anything/diff-overlay.json
.understand-anything/knowledge-graph.*.json

# CLI binary — compiled artifact, not source
CLI/
EOF
```

If `.understandignore` already exists, merge: read the existing file, append any
missing entries, write back. Never remove entries that were already present.

Additionally, apply this same filter as a post-processing step to any diff output
produced during this run. Any node whose file path starts with an ignored prefix
is silently removed from scope before scope calculation. Log removed paths to
`results/runs/${RUN_ID}/ignored-paths.json` for auditability.

### 0c. Generate RUN_ID and initialize state

```python
import datetime, json, uuid, pathlib

RUN_ID = "RUN-" + datetime.datetime.utcnow().strftime("%Y%m%d-%H%M%S")
run_dir = pathlib.Path(f"results/runs/{RUN_ID}")
run_dir.mkdir(parents=True, exist_ok=True)
(run_dir / "agents").mkdir(exist_ok=True)

state = {
    "run_id": RUN_ID,
    "run_type": "full",
    "env_mode": ENV_MODE,
    "started_at": datetime.datetime.utcnow().isoformat() + "Z",
    "endpoints": [],          # populated in Phase 1
    "current_endpoint_id": None,
    "current_agent": None,
    "completed": False
}
(run_dir / "orchestration-state.json").write_text(json.dumps(state, indent=2))
```

### 0d. Build endpoint list from DummyJSON CLI

Read the DummyJSON CLI output to extract every endpoint. The CLI lives at
`CLI/dummyjson-pp-cli`. Run its `list-endpoints` command (or equivalent help output)
to enumerate all METHOD + PATH combinations:

```bash
CLI/dummyjson-pp-cli --list-endpoints --output json > results/runs/${RUN_ID}/endpoints.json 2>/dev/null \
  || CLI/dummyjson-pp-cli help 2>&1 | grep -E '(GET|POST|PUT|PATCH|DELETE)' \
  > results/runs/${RUN_ID}/endpoints.txt
```

Parse the output into an array of ENDPOINT objects:
```json
{ "endpoint_id": "GET-products", "method": "GET", "path": "/products", "url_family": "/products" }
```

`url_family` = the path with all path parameters stripped to their prefix (e.g.,
`/products/{id}` → `/products`). Endpoints sharing a `url_family` are treated as connected.

Update `orchestration-state.json` with the full endpoint list, each with
`status: "pending"`, `agents_completed: []`, `agents_pending: [all 40 agent names + 3 generals]`.

---

## Phase 1 — API tester agents list

The 40 API tester agents in sequential execution order:

```
n299-validate-request-payloads
n300-verify-response-status-codes
n301-test-authentication-flows
n302-check-authorization-rules
n303-validate-json-schema-responses
n304-test-pagination-behavior
n305-verify-error-message-clarity
n306-test-rate-limit-enforcement
n307-validate-query-parameter-handling
n308-test-idempotency-of-endpoints
n309-verify-content-type-negotiation
n310-test-boundary-value-inputs
n311-validate-null-and-empty-fields
n312-test-timeout-handling
n313-verify-crud-operation-integrity
n314-test-concurrent-request-handling
n315-validate-header-propagation
n316-test-webhook-delivery
n317-run-regression-suite
n318-track-defect-density
n319-validate-api-versioning-behavior
n320-test-ssl-tls-enforcement
n321-verify-caching-headers
n322-validate-correlation-id-propagation
n323-test-bulk-operation-endpoints
n324-verify-audit-log-generation
n325-validate-search-and-filter-queries
n326-test-file-upload-and-download
n327-verify-sorting-behavior
n328-test-event-driven-api-triggers
n329-validate-ip-allowlist-enforcement
n330-test-api-gateway-routing
n331-verify-third-party-oauth-integration
n332-test-multipart-form-data-handling
n333-validate-retry-after-header-compliance
n334-test-soft-delete-behavior
n335-validate-graphql-depth-limits
n336-test-long-polling-support
n337-verify-enum-value-restrictions
n338-measure-api-consumer-satisfaction
```

General agents (always run after the 40, in this order):
```
test-case-creator   ← final sweep to catch any missed test cases
run-cicd-pipeline   ← validate pipeline integrity for this endpoint
bug-reporter        ← final sweep to catch any unreported failures
```

---

## Phase 2 — Per-endpoint loop

For EACH endpoint E in the endpoint list, execute the following in full before moving
to the next endpoint. Update `orchestration-state.json` at each checkpoint.

### 2a. Mark endpoint in-progress

```python
state["current_endpoint_id"] = E["endpoint_id"]
state_file.write_text(json.dumps(state, indent=2))
```

Create endpoint output directory:
```bash
mkdir -p results/runs/${RUN_ID}/agents
```

### 2b. Per-agent loop (40 API testers, then 3 generals)

For EACH agent A in the agent list (40 + 3 in order):

**Step B1 — Skip if already completed (resumption support)**

Read `orchestration-state.json`. If A is in `agents_completed` for endpoint E, skip to
next agent.

**Step B2 — Mark agent in-progress**

Update state: `current_agent = A.name`.

**Step B3 — Invoke the agent**

Resolve the agent spec file:
```bash
AGENT_SPEC="agents/api-tester/${A.name}/agent.md"
# general agents:
AGENT_SPEC="agents/general/${A.name}/agent.md"
```

Pass to the agent:
- The endpoint under test: `{ "method": E.method, "path": E.path, "base_url": "https://dummyjson.com" }`
- The RUN_ID
- The current tc_id counter (read from `results/test-case-registry.json` to get next available tc_id)

**If ENV_MODE = "claude-code":** invoke via Agent tool with the agent spec as the prompt,
passing endpoint context as user message.

**If ENV_MODE = "ollama":** run:
```bash
echo "[ENDPOINT CONTEXT JSON]" | \
  ollama run [model] "$(cat ${AGENT_SPEC})" \
  > results/runs/${RUN_ID}/agents/${A.name}/${E.endpoint_id}-stdout.txt \
  2> results/runs/${RUN_ID}/agents/${A.name}/${E.endpoint_id}-stderr.txt
```
Timeout: 300 seconds. If exit non-zero or timeout: treat as failed agent, write one
"Code Update" test case labeled "[AGENT_NAME] did not complete on [ENDPOINT_ID]", continue.

**Step B4 — Per-step guardrail loop**

As each step S of agent A executes, enforce the following IN ORDER before proceeding
to S+1. This is the core guardrail — no step advances until all side effects are settled:

**Guardrail G1 — Test case creation (mandatory for every step)**

Assert that a test case was created for step S. If the agent did not produce a test case
for this step, the orchestrator calls test-case-creator directly with S's details:
- Agent name: A.name
- Step text: S.step_text
- Step number: S.step_number
- Endpoint: E
- Outcome: one of "PASS" | "FAIL" | "Code Update"
- tc_id: next available (auto-increment from test-case-registry.json)

Write the new tc_id back to `results/test-case-registry.json`.

**Guardrail G2 — Postman collection update (mandatory if step made an HTTP call)**

If step S involved any HTTP call:
- If a tc_id already exists for this step: read it.
- Call the postman-collection agent with:
  - `tc_id`: the tc_id assigned in G1
  - `method`: extracted from S
  - `url`: E.base_url + E.path
  - `headers`, `body`, `expected_status`: extracted from S
  - `item_name`: MUST equal tc_id exactly
- Assert that the postman-collection agent wrote the item to `results/postman-collection.json`
  with `"name": tc_id`. If assertion fails, log ERROR and retry once. If retry fails, log
  WARNING and continue — do not abort the run.

**Guardrail G3 — Bug detection and live capture (mandatory if step outcome = FAIL)**

If step S outcome is FAIL:

1. **Bug reporter starts live capture immediately.** Call bug-reporter with mode "live-start",
   passing: A.name, E.endpoint_id, S.step_number, S.step_text, tc_id.
   Bug reporter writes a partial BUG_ID record to `results/bug-reports/[BUG_ID]-partial.json`.

2. **Start ffmpeg screen recording.**
   ```bash
   BUG_ID="[the BUG_ID from step 1]"
   RECORDING_PATH="results/bug-reports/recordings/${BUG_ID}.mp4"
   # macOS:
   ffmpeg -f avfoundation -i "1:0" -r 30 -vcodec libx264 -preset fast \
     "${RECORDING_PATH}" \
     > /tmp/ffmpeg-${BUG_ID}.log 2>&1 &
   FFMPEG_PID=$!
   echo $FFMPEG_PID > /tmp/ffmpeg-${BUG_ID}.pid
   # Linux (X11):
   # ffmpeg -f x11grab -r 30 -s 1920x1080 -i :0.0 -vcodec libx264 "${RECORDING_PATH}" &
   ```

3. **Original agent pauses.** The agent stops advancing to step S+1.

4. **Original agent reproduces the failing steps.** The agent re-executes steps 1 through S
   in exact order. No shortcuts, no parameter changes, no skipping. Every reproduction step
   is recorded as-is. The ffmpeg recording captures the terminal during this reproduction.

5. **Stop ffmpeg recording.**
   ```bash
   FFMPEG_PID=$(cat /tmp/ffmpeg-${BUG_ID}.pid)
   kill -SIGINT $FFMPEG_PID
   wait $FFMPEG_PID 2>/dev/null
   rm /tmp/ffmpeg-${BUG_ID}.pid
   ```

6. **Bug reporter finalizes the report.** Call bug-reporter with mode "finalize", passing:
   - BUG_ID
   - RECORDING_PATH
   - All 10 artifact paths (testing steps, Postman ref, screenshot, recording, logs, db-dump,
     created_at, title, severity, priority)
   - Reporting agent: A.name
   - tc_id: the test case number that found this bug

7. **Assert bug report exists** at `results/bug-reports/[BUG_ID].json`. If missing, log ERROR.

8. **Original agent resumes from step S+1.** It continues all remaining steps of its run
   on this endpoint. It does NOT re-run S. Remaining steps use fresh tc_ids.

**Guardrail G4 — "Code Update" label (mandatory if step is not applicable)**

If step S outcome is "Code Update" (agent determined this endpoint does not have the
behavior being tested):
- Label the test case: `"status": "Code Update"`, `"pass": null`, `"fail": null`
- Do NOT call bug-reporter
- Do NOT block progression
- Continue to S+1 immediately

**Step B5 — Agent completion**

After all steps of agent A are complete for endpoint E:
1. Move A from `agents_pending` to `agents_completed` in the state file.
2. Update `current_agent = null` in state file.
3. Write final stdout/stderr files if not already written.

**Guardrail B5-CHECK — Assert completion is real:**
- Assert `results/test-case-registry.json` has at least one entry for A.name + E.endpoint_id.
- If zero entries: log ERROR "Agent [A.name] produced no test cases for [E.endpoint_id]".
  Write one synthetic "Code Update" test case and continue. Do not abort.

### 2c. Mark endpoint complete

After all 43 agents complete for endpoint E:
1. Set endpoint status to "completed", record `completed_at`.
2. Update `current_endpoint_id = null` in state file.
3. Append endpoint summary to `results/runs/[RUN_ID]/pipeline-summary.json`.

---

## Phase 3 — Finalize run

After all endpoints complete:

### 3a. Write pipeline summary
```json
{
  "run_id": "[RUN_ID]",
  "run_type": "full",
  "started_at": "[ISO8601]",
  "completed_at": "[ISO8601]",
  "total_endpoints": N,
  "total_agents_per_endpoint": 43,
  "total_test_cases": N,
  "total_bugs": N,
  "total_code_updates": N,
  "endpoints": [...]
}
```

### 3b. Update test-case-registry.json
Ensure all tc_ids for this run are persisted with final status, agent name, endpoint id,
and (if passed) the `updated_at` timestamp.

### 3c. Update bug-reports/index.json
Regenerate the index from all `[BUG_ID].json` files in `results/bug-reports/`.

### 3d. Mark run complete
Set `completed: true` in `orchestration-state.json`.

### 3e. Exit code
- Any CRITICAL or HIGH bugs found → exit 1
- All bugs MEDIUM or LOW, or no bugs → exit 0

---

## Resumption

If orchestration-full is invoked and `orchestration-state.json` already exists for a
prior incomplete run, read it and offer the user two choices:
1. **Resume** the incomplete run from the last completed agent.
2. **Start fresh** with a new RUN_ID.

Default to Resume if no user input is provided within 10 seconds.
