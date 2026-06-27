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

All agents live in `agent-foundry/agents/`. All results go into `agent-foundry/results/runs/[RUN_ID]/`.
The working root for all relative paths in this skill is the MetaCTO-Assessment project root.

---

## Non-negotiable invariants

These hold in every phase without exception. If any instruction you are about to execute
would violate one, stop and surface the violation before proceeding.

1. **test-case-creator is the sole writer to test-case-registry.json. No exceptions.**
   Individual api-tester agents do NOT write to `agent-foundry/results/test-case-registry.json`.
   They write their raw findings to a per-agent staging file. After each api-tester agent
   completes all its steps for an endpoint, test-case-creator is invoked with those staged
   findings and must emit a valid, non-empty JSON array of test case objects. Only
   test-case-creator appends to the registry. Any direct write from an api-tester agent
   to test-case-registry.json is a broken run and must be blocked.
   A run where test-case-creator produces 0 valid cases AND no ERROR sentinel entry exists
   in the registry for that agent+endpoint combination is a broken run.

2. **Every API tester agent runs on every endpoint.** The `create-postman-collection` agent
   is one of the 40 and runs per-endpoint like all others. It handles Postman collection
   updates for that endpoint as part of its sequential execution. No agent is skipped.

3. **Every bug triggers live capture + reproduction.** When any agent reports a bug, the
   bug reporter begins capturing immediately. The original agent pauses, reproduces the
   failing steps in the same order, ffmpeg records the terminal during reproduction, then
   the bug reporter finalizes the report. Only after the report is written does the original
   agent continue its remaining steps.

4. **"Code Update" means exactly that — nothing else.** A test case for a step that requires
   a code change is labeled "Code Update". No bug report. No pass/fail. No blocking.
   The agent continues to the next step immediately.

5. **Agents run sequentially within an endpoint.** Agent n+1 does not start until agent n
   has completed all its steps and all per-step side effects (test-case-creator, bug reporter
   if triggered).

6. **Endpoints run sequentially.** Endpoint n+1 does not start until endpoint n is fully
   complete — all 40 API tester agents + 3 general agents finished, all outputs written,
   state file updated.

7. **All 40 API tester agents run on every endpoint.** No agent is skipped based on
   perceived relevance. An agent whose behavior doesn't apply to an endpoint produces
   "Code Update" labeled test cases — it still runs.

8. **The 3 general agents always run after the 40 API tester agents, per endpoint.**
   Order: test-case-creator final sweep → run-cicd-pipeline → bug-reporter sweep.

9. **State is written after every agent completes.** `agent-foundry/results/runs/[RUN_ID]/orchestration-state.json`
   is updated immediately after each agent finishes so an interrupted run can resume from
   the last completed agent without re-running completed work.

10. **No output is discarded.** Every agent's stdout and stderr are written to
    `agent-foundry/results/runs/[RUN_ID]/agents/[AGENT_NAME]/[ENDPOINT_ID]-stdout.txt` and
    `agent-foundry/results/runs/[RUN_ID]/agents/[AGENT_NAME]/[ENDPOINT_ID]-stderr.txt`.

---

## Phase 0 — Bootstrap

### 0a. Detect backend

Read the provider from `agent-foundry/config.toml`:

```bash
PROVIDER=$(grep '^provider' agent-foundry/config.toml | head -1 | awk -F'"' '{print $2}')
# PROVIDER = "ollama" | "claude-haiku"

if [ "$PROVIDER" = "ollama" ]; then
  ENV_MODE="ollama"
  OLLAMA_MODEL=$(grep 'ollama_model' agent-foundry/config.toml | head -1 | awk -F'"' '{print $2}')
  OLLAMA_BASE_URL=$(grep 'ollama_base_url' agent-foundry/config.toml | head -1 | awk -F'"' '{print $2}')
  echo "ENV_MODE=ollama model=$OLLAMA_MODEL"
else
  # claude-haiku or in a Claude Code session
  if [ -n "$CLAUDE_CODE_SESSION" ] || command -v claude >/dev/null 2>&1; then
    ENV_MODE="claude-code"
  else
    ENV_MODE="ollama"
    OLLAMA_MODEL=$(grep 'ollama_model' agent-foundry/config.toml | head -1 | awk -F'"' '{print $2}')
  fi
  echo "ENV_MODE=$ENV_MODE"
fi

FORGE_WORKSPACE="$(pwd)/agent-foundry"
```

All subsequent agent invocations use ENV_MODE:
- `claude-code` → invoke agents via the Agent tool, passing the agent spec .md as system prompt
- `ollama` → invoke agents via `FORGE_WORKSPACE=[path] python3 [run.py path]`

### 0b. Verify prerequisites

```bash
# agent-foundry must exist
if [ ! -d "agent-foundry/agents" ]; then
  echo "ERROR: agent-foundry/agents/ not found. Run from MetaCTO-Assessment project root."
  exit 1
fi

# results/ structure inside agent-foundry
mkdir -p agent-foundry/results/runs \
         agent-foundry/results/bug-reports/screenshots \
         agent-foundry/results/bug-reports/recordings \
         agent-foundry/results/bug-reports/logs \
         agent-foundry/results/bug-reports/db-dumps

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

# config.toml must exist in agent-foundry
if [ ! -f "agent-foundry/config.toml" ]; then
  echo "ERROR: agent-foundry/config.toml not found."
  exit 1
fi

# Ollama must be running if ENV_MODE=ollama
if [ "$ENV_MODE" = "ollama" ]; then
  if ! curl -s "${OLLAMA_BASE_URL}/models" >/dev/null 2>&1; then
    echo "ERROR: Ollama not running at ${OLLAMA_BASE_URL}. Start with: ollama serve"
    exit 1
  fi
fi
```

### 0b-i. Merge .understandignore

The `.understandignore` file lives at `.understand-anything/.understandignore` (already exists).
Merge agent and result directories into it — never overwrite existing entries:

```bash
IGNORE_FILE=".understand-anything/.understandignore"

# Entries to ensure are present
REQUIRED_ENTRIES=(
  "agent-foundry/agents/"
  "agent-foundry/results/"
  "agent-foundry/memory/"
  "agent-foundry/tools/"
  "agent-foundry/evolvers/"
  "agent-foundry/.venv/"
  ".understand-anything/intermediate/"
  ".understand-anything/knowledge-graph.*.json"
  "CLI/"
  "node_modules/"
)

for entry in "${REQUIRED_ENTRIES[@]}"; do
  if ! grep -qF "$entry" "$IGNORE_FILE" 2>/dev/null; then
    echo "$entry" >> "$IGNORE_FILE"
    echo "Added to .understandignore: $entry"
  fi
done
```

Additionally, apply this as a post-processing filter to any diff output during this run.
Any node whose file path starts with an ignored prefix is removed from scope before
scope calculation. Log removed paths to `agent-foundry/results/runs/${RUN_ID}/ignored-paths.json`.

### 0c. Generate RUN_ID and initialize state

```python
import datetime, json, pathlib

RUN_ID = "RUN-" + datetime.datetime.utcnow().strftime("%Y%m%d-%H%M%S")
run_dir = pathlib.Path(f"agent-foundry/results/runs/{RUN_ID}")
run_dir.mkdir(parents=True, exist_ok=True)
(run_dir / "agents").mkdir(exist_ok=True)

state = {
    "run_id": RUN_ID,
    "run_type": "full",
    "env_mode": ENV_MODE,
    "forge_workspace": str(pathlib.Path("agent-foundry").resolve()),
    "started_at": datetime.datetime.utcnow().isoformat() + "Z",
    "endpoints": [],
    "current_endpoint_id": None,
    "current_agent": None,
    "completed": False
}
(run_dir / "orchestration-state.json").write_text(json.dumps(state, indent=2))
```

### 0d. Build endpoint list from DummyJSON CLI

The CLI lives at `CLI/dummyjson-pp-cli` (symlink to the printing-press library build).

```bash
CLI/dummyjson-pp-cli --list-endpoints --output json \
  > agent-foundry/results/runs/${RUN_ID}/endpoints.json 2>/dev/null \
  || CLI/dummyjson-pp-cli help 2>&1 \
  | grep -E '(GET|POST|PUT|PATCH|DELETE)' \
  > agent-foundry/results/runs/${RUN_ID}/endpoints.txt
```

Parse the output into an array of ENDPOINT objects:
```json
{ "endpoint_id": "GET-products", "method": "GET", "path": "/products", "url_family": "/products" }
```

`url_family` = path with all path parameters stripped to their prefix
(e.g. `/products/{id}` → `/products`). Endpoints sharing a `url_family` are connected.

Update `orchestration-state.json` with the full endpoint list, each with
`status: "pending"`, `agents_completed: []`, `agents_pending: [all 40 agent names + 3 generals]`.

---

## Phase 1 — Agent lists

### API tester agents (40) — sequential execution order

These are the exact folder names under `agent-foundry/agents/api-tester/`:

```
validate-request-payloads
verify-response-status-codes
test-authentication-flows
check-authorization-rules
validate-json-schema-responses
test-pagination-behavior
verify-error-message-clarity
test-rate-limit-enforcement
validate-query-parameter-handling
test-idempotency-of-endpoints
verify-content-type-negotiation
validate-null-empty-fields
test-timeout-handling
verify-crud-operation-integrity
test-concurrent-request-handling
validate-header-propagation
test-webhook-delivery
run-regression-suite
track-defect-density
validate-api-versioning-behavior
test-ssl-tls-enforcement
verify-caching-headers
validate-correlation-id-propagation
test-bulk-operation-endpoints
verify-audit-log-generation
validate-search-and-filter-queries
test-file-upload-and-download
verify-sorting-behavior
test-event-driven-api-triggers
test-ip-allowlist-enforcement
test-api-gateway-routing
verify-third-party-oauth-integration
test-multipart-form-data-handling
validate-retry-after-header-compliance
test-soft-delete-behavior
validate-graphql-depth-limits
test-long-polling-support
verify-enum-value-restrictions
measure-api-consumer-satisfaction
create-postman-collection
```

### General agents (3) — always run after the 40, in this order

These are the exact folder names under `agent-foundry/agents/general/`:

```
test-case-creator
run-cicd-pipeline
bug-reporter
```

### Agent spec file resolution

For each agent A, resolve its spec file:

```bash
# API tester agents:
SPEC="agent-foundry/agents/api-tester/${A_NAME}/subagent/api-tester-${A_NAME}.md"

# General agents:
SPEC="agent-foundry/agents/general/${A_NAME}/subagent/general-${A_NAME}.md"

# run.py for Ollama invocation:
RUNPY_API="agent-foundry/agents/api-tester/${A_NAME}/subagent/run.py"
RUNPY_GEN="agent-foundry/agents/general/${A_NAME}/subagent/run.py"
```

Assert the spec file exists before invoking. If missing, log ERROR, write one
"Code Update" test case labeled "[AGENT_NAME] spec not found", continue.

---

## Phase 2 — Per-endpoint loop

For EACH endpoint E in the endpoint list, execute the following in full before moving
to the next endpoint. Update `orchestration-state.json` at each checkpoint.

### 2a. Mark endpoint in-progress

```python
state["current_endpoint_id"] = E["endpoint_id"]
state_file.write_text(json.dumps(state, indent=2))
```

Create per-agent output directory:
```bash
mkdir -p agent-foundry/results/runs/${RUN_ID}/agents
```

### 2b. Per-agent loop (40 API testers, then 3 generals)

For EACH agent A in the agent list (40 + 3 in order):

**Step B1 — Skip if already completed (resumption support)**

Read `orchestration-state.json`. If A is in `agents_completed` for endpoint E, skip.

**Step B2 — Mark agent in-progress**

Update state: `current_agent = A.name`.

**Step B3 — Invoke the agent**

Pass to the agent:
- Endpoint context: `{ "method": E.method, "path": E.path, "base_url": "https://dummyjson.com" }`
- `RUN_ID`
- Staging output path: `agent-foundry/results/runs/${RUN_ID}/staging/${A_NAME}/${E_ID}-findings.json`
  The agent writes its raw findings (HTTP results, assertion outcomes, step results) here.
  The agent does NOT receive a `tc_id` and does NOT write to `test-case-registry.json`.

Create the staging directory before invocation:
```bash
mkdir -p "agent-foundry/results/runs/${RUN_ID}/staging/${A_NAME}"
```

**If ENV_MODE = "claude-code":**

Read the agent spec .md file and invoke via the Agent tool, passing endpoint context
as the user message. The agent spec .md content becomes the system prompt.

```python
spec_content = open(SPEC).read()
# Invoke via Agent tool with spec_content as system prompt and endpoint_context as message
```

**If ENV_MODE = "ollama":**

```bash
FORGE_WORKSPACE="$(pwd)/agent-foundry" \
  python3 "${RUNPY}" \
  > agent-foundry/results/runs/${RUN_ID}/agents/${A_NAME}/${E_ID}-stdout.txt \
  2> agent-foundry/results/runs/${RUN_ID}/agents/${A_NAME}/${E_ID}-stderr.txt
```

Timeout: 300 seconds. On exit non-zero or timeout: write one "Code Update" test case
labeled "[AGENT_NAME] did not complete on [ENDPOINT_ID]" and continue.

**Step B4 — Per-step guardrail loop**

As each step S of agent A executes, enforce IN ORDER before advancing to S+1:

**Guardrail G1 — Findings staging (mandatory for every step of every api-tester agent)**

The api-tester agent writes each step's raw result to the staging file — NOT to the registry.
The staging file format for each step entry:
```json
{
  "step_number": S.step_number,
  "step_text": S.step_text,
  "http_method": "GET" | "POST" | ...,
  "http_path": "/products/1",
  "http_status": 200,
  "response_body_excerpt": "...",
  "assertion_result": "PASS" | "FAIL" | "Code Update",
  "assertion_detail": "..."
}
```

Assert that the staging file was updated for step S before advancing to S+1.
If the staging file was not updated: log ERROR for step S, write a synthetic staging entry
with `"assertion_result": "ERROR"`, continue to S+1. Do NOT write to test-case-registry.json.

**Guardrail G1b — test-case-creator invocation (mandatory after each api-tester agent completes all steps)**

This fires once per api-tester agent, AFTER all its steps are done, BEFORE the next agent starts.
It is the ONLY mechanism that writes to `agent-foundry/results/test-case-registry.json`.

```
STAGING_FILE = agent-foundry/results/runs/${RUN_ID}/staging/${A_NAME}/${E_ID}-findings.json
```

**Sub-step 1 — Assert staging file exists and is non-empty**
```bash
if [ ! -s "$STAGING_FILE" ]; then
  echo "ERROR: Staging file missing or empty: $STAGING_FILE"
  # Write one ERROR sentinel to registry and continue
  append_to_registry({
    "tc_id": "TC-ERR-${A_NAME}-${E_ID}-nostaging",
    "agent": A_NAME, "endpoint_id": E_ID, "run_id": RUN_ID,
    "outcome": "ERROR", "error": "staging file missing",
    "pass": false, "fail": false
  })
  # Continue to next agent — do NOT abort
fi
```

**Sub-step 2 — Invoke test-case-creator with staged findings**

```python
# Read the staged findings
findings = json.load(open(STAGING_FILE))

# Build the test-case-creator prompt
system_prompt = open("agent-foundry/agents/general/test-case-creator/subagent/general-test-case-creator.md").read()

user_message = f"""
You are test-case-creator. Given the following API test findings from agent '{A_NAME}'
running against endpoint {E.method} {E.path}, emit a JSON array of test case objects.

FINDINGS:
{json.dumps(findings, indent=2)}

OUTPUT RULES — YOU MUST FOLLOW THESE EXACTLY:
- Your response must be ONLY a valid JSON array.
- Start your response with [ and end with ].
- No prose, no markdown, no code fences, no explanation.
- Each element must include: tc_id, agent, endpoint_id, step_number, step_text, outcome, pass, fail.
- tc_id values start at TC-{next_tc_id} and increment by 1 for each case.
- outcome must be exactly "PASS", "FAIL", or "Code Update".
- pass is true only when outcome is "PASS". fail is true only when outcome is "FAIL".
"""

output = invoke_agent(system_prompt, user_message)
```

**If ENV_MODE = "claude-code":** invoke via Agent tool.
**If ENV_MODE = "ollama":** `FORGE_WORKSPACE=$(pwd)/agent-foundry python3 agent-foundry/agents/general/test-case-creator/subagent/run.py`

**Sub-step 3 — Parse and validate output (with retry)**

```python
MAX_ATTEMPTS = 3
parsed = []

for attempt in range(1, MAX_ATTEMPTS + 1):
    parsed = extract_json_array(output)  # same as testcase.extract_json_array in contract.py

    if parsed:
        break  # valid non-empty array — proceed

    # Retry with escalating format enforcement
    if attempt == 1:
        retry_prefix = "CRITICAL: Your previous response was not a valid JSON array. "
        retry_prefix += "Output ONLY a JSON array. Start with [ and end with ]. No other text."
    elif attempt == 2:
        retry_prefix = "MANDATORY FORMAT: Output exactly this structure (filled in with real data):\n"
        retry_prefix += '[{"tc_id":"TC-N","agent":"' + A_NAME + '","endpoint_id":"' + E_ID + '",'
        retry_prefix += '"step_number":1,"step_text":"...","outcome":"PASS","pass":true,"fail":false}]'
    # attempt == 3 is the final try — same prefix as attempt 2

    output = invoke_agent(system_prompt, retry_prefix + "\n\n" + user_message)
    log(f"test-case-creator retry attempt {attempt} for {A_NAME}/{E_ID}")

if not parsed:
    # All 3 attempts failed — write ERROR sentinel
    log(f"ERROR: test-case-creator produced 0 valid cases for {A_NAME}/{E_ID} after {MAX_ATTEMPTS} attempts")
    append_to_registry({
        "tc_id": f"TC-ERR-{A_NAME}-{E_ID}",
        "agent": A_NAME, "endpoint_id": E_ID, "run_id": RUN_ID,
        "outcome": "ERROR",
        "error": f"test-case-creator returned empty/unparseable output after {MAX_ATTEMPTS} attempts",
        "pass": false, "fail": false
    })
    # Continue — do NOT abort the run
```

**Sub-step 4 — Write to registry (on success only)**

```python
if parsed:
    for tc in parsed:
        # Enforce required fields
        tc["agent"]       = tc.get("agent", A_NAME)
        tc["endpoint_id"] = tc.get("endpoint_id", E_ID)
        tc["run_id"]      = RUN_ID
        append_to_registry(tc)
    log(f"test-case-creator wrote {len(parsed)} cases for {A_NAME}/{E_ID}")
```

`append_to_registry` reads `agent-foundry/results/test-case-registry.json`, appends the
new cases, and writes back atomically. It is the ONLY function that writes to that file.

**Guardrail G2 — Postman collection (handled by create-postman-collection agent)**

The `create-postman-collection` agent (agent #40 in the list) runs per-endpoint as part
of the sequential 40. When it runs, it creates/updates the Postman collection for that
endpoint and links each item to the tc_id for that endpoint's test cases.

The orchestrator's responsibility: after `create-postman-collection` completes, assert that
`agent-foundry/results/postman-collection.json` was updated with at least one item whose
`name` matches a tc_id from this endpoint's test case registry entries.
If assertion fails, log WARNING — do not abort the run.

**Guardrail G3 — Bug detection and live capture (mandatory if step outcome = FAIL)**

If step S outcome is FAIL:

1. **Bug reporter starts live capture immediately.** Call bug-reporter with mode "live-start",
   passing: A.name, E.endpoint_id, S.step_number, S.step_text, tc_id.
   Bug reporter writes a partial record to `agent-foundry/results/bug-reports/[BUG_ID]-partial.json`.

2. **Start ffmpeg screen recording.**
   ```bash
   BUG_ID="[the BUG_ID from step 1]"
   RECORDING_PATH="agent-foundry/results/bug-reports/recordings/${BUG_ID}.mp4"
   # macOS:
   ffmpeg -f avfoundation -i "1:0" -r 30 -vcodec libx264 -preset fast \
     "${RECORDING_PATH}" > /tmp/ffmpeg-${BUG_ID}.log 2>&1 &
   FFMPEG_PID=$!
   echo $FFMPEG_PID > /tmp/ffmpeg-${BUG_ID}.pid
   # Linux (X11):
   # ffmpeg -f x11grab -r 30 -s 1920x1080 -i :0.0 -vcodec libx264 "${RECORDING_PATH}" &
   ```

3. **Original agent pauses.** The agent stops advancing to step S+1.

4. **Original agent reproduces the failing steps.** Re-executes steps 1 through S in exact
   order. No shortcuts, no parameter changes, no skipping. The ffmpeg recording captures
   the terminal during reproduction.

5. **Stop ffmpeg recording.**
   ```bash
   kill -SIGINT $(cat /tmp/ffmpeg-${BUG_ID}.pid)
   wait $(cat /tmp/ffmpeg-${BUG_ID}.pid) 2>/dev/null
   rm /tmp/ffmpeg-${BUG_ID}.pid
   ```

6. **Bug reporter finalizes the report.** Call bug-reporter with mode "finalize", passing:
   - BUG_ID, RECORDING_PATH
   - All 10 artifacts: testing steps, Postman ref, screenshot, recording, logs, db-dump,
     created_at, title, severity, priority
   - Reporting agent: A.name
   - tc_id: the test case that found this bug

7. **Assert bug report exists** at `agent-foundry/results/bug-reports/[BUG_ID].json`.
   If missing, log ERROR.

8. **Original agent resumes from step S+1.** Does NOT re-run S. Remaining steps use fresh tc_ids.

**Guardrail G4 — "Code Update" label (mandatory if step is not applicable)**

If step S outcome is "Code Update":
- Label: `"status": "Code Update"`, `"pass": null`, `"fail": null`
- Do NOT call bug-reporter
- Do NOT block progression
- Continue to S+1 immediately

**Step B5 — Agent completion**

After all steps of agent A complete for endpoint E:
1. Move A from `agents_pending` to `agents_completed` in state file.
2. Set `current_agent = null`.
3. Write final stdout/stderr files.

**B5-CHECK — Assert test-case-creator ran and wrote to the registry:**
- Assert `agent-foundry/results/test-case-registry.json` has ≥ 1 entry (real OR ERROR sentinel)
  where `agent == A.name` AND `endpoint_id == E.endpoint_id`.
- If zero entries exist for this agent+endpoint: G1b failed silently. Log CRITICAL.
  Force-write one ERROR sentinel now. Do not abort.
- Assert staging file `agent-foundry/results/runs/${RUN_ID}/staging/${A_NAME}/${E_ID}-findings.json`
  exists. If missing: log ERROR (api-tester agent did not write findings).

### 2c. Mark endpoint complete

After all 43 agents complete for endpoint E:
1. Set endpoint `status: "completed"`, record `completed_at`.
2. Set `current_endpoint_id = null`.
3. Append endpoint summary to `agent-foundry/results/runs/[RUN_ID]/pipeline-summary.json`.

---

## Phase 3 — Finalize run

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
Write to `agent-foundry/results/runs/[RUN_ID]/pipeline-summary.json`.

### 3b. Update test-case-registry.json
Persist all tc_ids with final status, agent name, endpoint id, and `updated_at` timestamp.
Write to `agent-foundry/results/test-case-registry.json`.

### 3c. Update bug-reports/index.json
Regenerate index from all `[BUG_ID].json` files in `agent-foundry/results/bug-reports/`.

### 3d. Mark run complete
Set `completed: true` in `orchestration-state.json`.

### 3e. Exit code
- Any CRITICAL or HIGH bugs found → exit 1
- All bugs MEDIUM or LOW, or no bugs → exit 0

---

## Resumption

If invoked and `agent-foundry/results/runs/` contains an incomplete run
(`orchestration-state.json` with `"completed": false`), read it and offer:
1. **Resume** from the last completed agent.
2. **Start fresh** with a new RUN_ID.

Default to Resume if no input within 10 seconds.
