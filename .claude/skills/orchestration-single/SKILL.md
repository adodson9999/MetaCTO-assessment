---
name: orchestration-single
description: >
  Run exactly one named API tester agent plus the 3 general agents (bug-reporter,
  run-cicd-pipeline, test-case-creator) against every DummyJSON endpoint sequentially.
  The user provides the agent name at invocation. Use when you want to isolate and
  run a single API tester against the full endpoint surface. Trigger with
  "orchestration-single [agent-name]", "run single agent [agent-name]",
  "test [agent-name] against all endpoints", or "run just [agent-name]".
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

# orchestration-single

Single-agent run. Exactly one API tester agent (user-specified by name) + the 3 general
agents run against every DummyJSON endpoint sequentially. One endpoint completes fully
before the next starts.

All agents live in `agent-foundry/agents/`. All results go into
`agent-foundry/results/runs/[RUN_ID]/`. Paths are relative to the MetaCTO-Assessment
project root.

---

## Non-negotiable invariants

All 10 invariants from orchestration-full apply identically here, including invariant 1
(test-case-creator is the sole writer to test-case-registry.json; the single api-tester
agent writes findings to staging only). Additionally:

11. **Exactly one API tester agent runs.** Not two, not zero. If the provided agent name
    does not match any of the 40 known API tester agent folder names exactly, stop
    immediately and surface an error with the valid agent list. Do not attempt fuzzy matching.

12. **The 3 general agents always run.** Even when only one API tester agent is specified,
    test-case-creator, run-cicd-pipeline, and bug-reporter always execute after it on
    every endpoint. The 3 generals are not optional.

13. **Agent name is provided at invocation — never prompted mid-run.** If no agent name
    is provided at skill invocation, display the valid agent list and exit. Do not ask
    mid-run.

---

## Phase 0 — Parse and validate agent name

### 0a. Extract agent name from invocation

The user invokes this skill with a single agent name argument. Extract it from the
invocation message. The agent name must be an exact folder name from
`agent-foundry/agents/api-tester/`. Examples:

- "orchestration-single test-authentication-flows" → AGENT_NAME = "test-authentication-flows"
- "run single agent validate-request-payloads" → AGENT_NAME = "validate-request-payloads"
- "run just create-postman-collection" → AGENT_NAME = "create-postman-collection"

If the user provides an old n### name like "n301-test-authentication-flows", strip the
prefix: AGENT_NAME = "test-authentication-flows". Do not accept the prefixed form.

### 0b. Validate against the known agent list

```python
VALID_AGENTS = [
    "validate-request-payloads",
    "verify-response-status-codes",
    "test-authentication-flows",
    "check-authorization-rules",
    "validate-json-schema-responses",
    "test-pagination-behavior",
    "verify-error-message-clarity",
    "test-rate-limit-enforcement",
    "validate-query-parameter-handling",
    "test-idempotency-of-endpoints",
    "verify-content-type-negotiation",
    "validate-null-empty-fields",
    "test-timeout-handling",
    "verify-crud-operation-integrity",
    "test-concurrent-request-handling",
    "validate-header-propagation",
    "test-webhook-delivery",
    "run-regression-suite",
    "track-defect-density",
    "validate-api-versioning-behavior",
    "test-ssl-tls-enforcement",
    "verify-caching-headers",
    "validate-correlation-id-propagation",
    "test-bulk-operation-endpoints",
    "verify-audit-log-generation",
    "validate-search-and-filter-queries",
    "test-file-upload-and-download",
    "verify-sorting-behavior",
    "test-event-driven-api-triggers",
    "test-ip-allowlist-enforcement",
    "test-api-gateway-routing",
    "verify-third-party-oauth-integration",
    "test-multipart-form-data-handling",
    "validate-retry-after-header-compliance",
    "test-soft-delete-behavior",
    "validate-graphql-depth-limits",
    "test-long-polling-support",
    "verify-enum-value-restrictions",
    "measure-api-consumer-satisfaction",
    "create-postman-collection",
]

if AGENT_NAME not in VALID_AGENTS:
    print(f"ERROR: '{AGENT_NAME}' is not a valid API tester agent folder name.")
    print("Valid agents (exact folder names under agent-foundry/agents/api-tester/):")
    for a in VALID_AGENTS:
        print(f"  {a}")
    exit(1)
```

Also assert the spec file exists:
```bash
SPEC="agent-foundry/agents/api-tester/${AGENT_NAME}/subagent/api-tester-${AGENT_NAME}.md"
if [ ! -f "$SPEC" ]; then
  echo "ERROR: Spec file not found: $SPEC"
  echo "The agent folder exists but the spec file is missing."
  exit 1
fi
```

### 0c. Bootstrap (environment detection, prerequisites, RUN_ID)

Read backend from `agent-foundry/config.toml`:

```bash
PROVIDER=$(grep '^provider' agent-foundry/config.toml | head -1 | awk -F'"' '{print $2}')

if [ "$PROVIDER" = "ollama" ]; then
  ENV_MODE="ollama"
  OLLAMA_MODEL=$(grep 'ollama_model' agent-foundry/config.toml | head -1 | awk -F'"' '{print $2}')
  OLLAMA_BASE_URL=$(grep 'ollama_base_url' agent-foundry/config.toml | head -1 | awk -F'"' '{print $2}')
else
  if [ -n "$CLAUDE_CODE_SESSION" ] || command -v claude >/dev/null 2>&1; then
    ENV_MODE="claude-code"
  else
    ENV_MODE="ollama"
  fi
fi

FORGE_WORKSPACE="$(pwd)/agent-foundry"
```

Prerequisite checks (identical to orchestration-full Phase 0b):
- `agent-foundry/agents/` must exist
- `ffmpeg` must be on PATH
- `.understand-anything/knowledge-graph.json` must exist
- `agent-foundry/config.toml` must exist
- If ENV_MODE=ollama: Ollama must respond at `${OLLAMA_BASE_URL}/models`
- Create directory structure: `agent-foundry/results/runs/` and sub-dirs

Generate RUN_ID: `RUN-[YYYYMMDD-HHMMSS]` with `run_type: "single:[AGENT_NAME]"`.
Initialize `agent-foundry/results/runs/${RUN_ID}/orchestration-state.json`.

### 0c-i. Merge .understandignore

The `.understandignore` file lives at `.understand-anything/.understandignore` (already
exists in this project). Merge required entries into it — never overwrite:

```bash
IGNORE_FILE=".understand-anything/.understandignore"

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
  fi
done
```

Apply this as a post-processing filter: any node whose file path starts with an ignored
prefix is removed from scope before scope calculation.

### 0d. Build full endpoint list

Identical to orchestration-full Phase 0d. All endpoints are tested — no scoping.

```bash
CLI/dummyjson-pp-cli --list-endpoints --output json \
  > agent-foundry/results/runs/${RUN_ID}/endpoints.json 2>/dev/null
```

Parse into ENDPOINT objects. Update state file with full endpoint list.

---

## Phase 1 — Agent execution order for this run

The run uses exactly 4 agents per endpoint, in this fixed order:

```
1. [AGENT_NAME]       ← the single API tester agent the user specified
2. test-case-creator  ← general: final test case sweep
3. run-cicd-pipeline  ← general: pipeline integrity check
4. bug-reporter       ← general: bug sweep
```

Spec file paths:
- API tester: `agent-foundry/agents/api-tester/${AGENT_NAME}/subagent/api-tester-${AGENT_NAME}.md`
- run.py (Ollama): `agent-foundry/agents/api-tester/${AGENT_NAME}/subagent/run.py`
- General agents: `agent-foundry/agents/general/${GEN_NAME}/subagent/general-${GEN_NAME}.md`
- General run.py (Ollama): `agent-foundry/agents/general/${GEN_NAME}/subagent/run.py`

This list is fixed for the entire run. It does not change between endpoints.

---

## Phase 2 — Per-endpoint loop

For EACH endpoint E in the endpoint list, execute the following in full:

### 2a. Mark endpoint in-progress

```python
state["current_endpoint_id"] = E["endpoint_id"]
state["current_agent"] = None
write_state()
```

Create per-agent output directories:
```bash
mkdir -p agent-foundry/results/runs/${RUN_ID}/agents/${AGENT_NAME}
mkdir -p agent-foundry/results/runs/${RUN_ID}/agents/test-case-creator
mkdir -p agent-foundry/results/runs/${RUN_ID}/agents/run-cicd-pipeline
mkdir -p agent-foundry/results/runs/${RUN_ID}/agents/bug-reporter
```

### 2b. Run the 4 agents in order

For EACH of the 4 agents in order:

**Step B1 — Skip if already completed** (resumption support)

Read state. If this agent is in `agents_completed` for endpoint E, skip.

**Step B2 — Mark agent in-progress**

Update state: `current_agent = A.name`.

**Step B3 — Invoke the agent**

Pass endpoint context. Do NOT pass a tc_id. The api-tester agent writes raw findings
to staging — it does not write to the registry.

Create the staging directory before invocation:
```bash
mkdir -p "agent-foundry/results/runs/${RUN_ID}/staging/${AGENT_NAME}"
```

**If ENV_MODE = "claude-code":**

```python
spec_path = "agent-foundry/agents/api-tester/{}/subagent/api-tester-{}.md".format(AGENT_NAME, AGENT_NAME)
spec_content = open(spec_path).read()
# Invoke via Agent tool: spec_content = system prompt
# endpoint_context + staging_path = user message
staging_path = f"agent-foundry/results/runs/{RUN_ID}/staging/{AGENT_NAME}/{E_ID}-findings.json"
```

**If ENV_MODE = "ollama":**

```bash
# API tester agent:
FORGE_WORKSPACE="$(pwd)/agent-foundry" \
  python3 "agent-foundry/agents/api-tester/${AGENT_NAME}/subagent/run.py" \
  > agent-foundry/results/runs/${RUN_ID}/agents/${AGENT_NAME}/${E_ID}-stdout.txt \
  2> agent-foundry/results/runs/${RUN_ID}/agents/${AGENT_NAME}/${E_ID}-stderr.txt

# General agents (same pattern):
FORGE_WORKSPACE="$(pwd)/agent-foundry" \
  python3 "agent-foundry/agents/general/${GEN_NAME}/subagent/run.py" \
  > agent-foundry/results/runs/${RUN_ID}/agents/${GEN_NAME}/${E_ID}-stdout.txt \
  2> agent-foundry/results/runs/${RUN_ID}/agents/${GEN_NAME}/${E_ID}-stderr.txt
```

Timeout: 300 seconds. On exit non-zero or timeout: write a synthetic ERROR entry to staging
(not the registry), log the timeout, and continue to G1b so test-case-creator still runs.

**Step B4 — Per-step guardrail loop**

IDENTICAL to orchestration-full Step B4. All four guardrails apply:

**G1 — Findings staging (mandatory for every step of the api-tester agent)**

The api-tester agent writes each step's raw result to staging (not the registry).
Per-step staging entry format:
```json
{
  "step_number": S.step_number,
  "step_text": S.step_text,
  "http_method": "GET" | "POST" | ...,
  "http_path": "/...",
  "http_status": 200,
  "response_body_excerpt": "...",
  "assertion_result": "PASS" | "FAIL" | "Code Update",
  "assertion_detail": "..."
}
```
Assert the staging file is updated for step S before advancing to S+1.
If not updated: log ERROR, write a synthetic staging entry with `"assertion_result": "ERROR"`,
continue. Do NOT write to test-case-registry.json.

**G1b — test-case-creator invocation (mandatory after the api-tester agent completes all steps)**

Identical to orchestration-full G1b. Fires once after AGENT_NAME completes all steps for
endpoint E. Uses staged findings as input. Enforces 3-attempt retry with escalating format
instructions. test-case-creator is the ONLY writer to test-case-registry.json.

```
STAGING_FILE = agent-foundry/results/runs/${RUN_ID}/staging/${AGENT_NAME}/${E_ID}-findings.json
```

Success: valid non-empty JSON array → append all tc objects to registry.
All 3 attempts fail: write one ERROR sentinel to registry, log CRITICAL, continue.

**G2 — Postman collection (handled by create-postman-collection agent)**

The `create-postman-collection` agent (when it IS the AGENT_NAME for this run)
runs per-endpoint and updates the Postman collection for that endpoint. When the
AGENT_NAME is NOT `create-postman-collection`, G2 is not applicable for this run —
log INFO: "G2 not applicable: create-postman-collection not the selected agent."
Do not fail the run or call the agent separately. The single-agent run tests exactly
the one specified agent.

**G3 — Bug detection and live capture (mandatory if step outcome = FAIL)**

Identical to orchestration-full G3:
1. Call bug-reporter with mode "live-start"
2. Start ffmpeg: `ffmpeg -f avfoundation -i "1:0" -r 30 -vcodec libx264 agent-foundry/results/bug-reports/recordings/${BUG_ID}.mp4 &`
3. Original agent pauses
4. Reproduce steps 1 through S in exact order
5. Stop ffmpeg
6. Call bug-reporter with mode "finalize" — all 10 artifacts required
7. Assert `agent-foundry/results/bug-reports/${BUG_ID}.json` exists
8. Agent resumes from S+1

The bug report includes:
```json
{
  "found_by_agent": "[AGENT_NAME or bug-reporter]",
  "test_case_id": "[tc_id]",
  "run_id": "[RUN_ID]",
  "run_type": "single"
}
```

**G4 — "Code Update" label for non-applicable steps**

Status: `"Code Update"`. No bug report. No blocking. Advance to S+1 immediately.

**Step B5 — Agent completion**

After all steps complete:
1. Move agent from `agents_pending` to `agents_completed` in state file.
2. Set `current_agent = null`.
3. **B5-CHECK**: Assert `agent-foundry/results/test-case-registry.json` has ≥ 1 entry
   (real OR ERROR sentinel) where `agent == AGENT_NAME` AND `endpoint_id == E.endpoint_id`.
   If zero: G1b failed silently — log CRITICAL, force-write one ERROR sentinel, continue.
   Also assert staging file exists. If missing: log ERROR (agent did not write findings).

### 2c. Mark endpoint complete

After all 4 agents complete:
1. Set endpoint `status: "completed"`, record `completed_at`.
2. Set `current_endpoint_id = null`.
3. Append endpoint summary to `agent-foundry/results/runs/${RUN_ID}/pipeline-summary.json`.

---

## Phase 3 — Finalize run

Write pipeline summary to `agent-foundry/results/runs/${RUN_ID}/pipeline-summary.json`:

```json
{
  "run_id": "[RUN_ID]",
  "run_type": "single",
  "agent_under_test": "[AGENT_NAME]",
  "general_agents": ["test-case-creator", "run-cicd-pipeline", "bug-reporter"],
  "agents_per_endpoint": 4,
  "env_mode": "[ENV_MODE]",
  "forge_workspace": "[FORGE_WORKSPACE]",
  "started_at": "[ISO8601]",
  "completed_at": "[ISO8601]",
  "total_endpoints": N,
  "total_test_cases": N,
  "total_bugs": N,
  "total_code_updates": N,
  "endpoints": [...]
}
```

Update `agent-foundry/results/test-case-registry.json` with all tc_ids.
Regenerate `agent-foundry/results/bug-reports/index.json`.
Set `completed: true` in `orchestration-state.json`.

Exit code: any CRITICAL/HIGH bugs → exit 1, else exit 0.

---

## Output attribution

Every test case in `agent-foundry/results/test-case-registry.json` produced by this run includes:
```json
{
  "agent": "[AGENT_NAME or general agent name]",
  "run_id": "[RUN_ID]",
  "run_type": "single"
}
```

Every bug report in `agent-foundry/results/bug-reports/` includes:
```json
{
  "found_by_agent": "[agent name]",
  "test_case_id": "[tc_id]",
  "run_id": "[RUN_ID]",
  "run_type": "single"
}
```

---

## Resumption

If invoked and `agent-foundry/results/runs/` contains an incomplete single run for the
same AGENT_NAME (`orchestration-state.json` with `"completed": false` and matching agent),
offer:
1. **Resume** from the last completed agent.
2. **Start Fresh** with a new RUN_ID.

Default to Resume if no input within 10 seconds.
