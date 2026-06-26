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

---

## Non-negotiable invariants

All 10 invariants from orchestration-full apply identically here. Additionally:

11. **Exactly one API tester agent runs.** Not two, not zero. If the provided agent name
    does not match any of the 40 known API tester agents exactly, stop immediately and
    surface an error with the valid agent list. Do not attempt fuzzy matching.

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
invocation message. Examples:
- "orchestration-single n301-test-authentication-flows" → AGENT_NAME = "n301-test-authentication-flows"
- "run single agent validate-request-payloads" → AGENT_NAME = "n299-validate-request-payloads"
- "run just n316" → AGENT_NAME = "n316-test-webhook-delivery"

Normalize: if the user provides only the number (e.g., "n316"), expand to the full name.

### 0b. Validate against known agent list

```python
VALID_AGENTS = [
    "n299-validate-request-payloads",
    "n300-verify-response-status-codes",
    "n301-test-authentication-flows",
    "n302-check-authorization-rules",
    "n303-validate-json-schema-responses",
    "n304-test-pagination-behavior",
    "n305-verify-error-message-clarity",
    "n306-test-rate-limit-enforcement",
    "n307-validate-query-parameter-handling",
    "n308-test-idempotency-of-endpoints",
    "n309-verify-content-type-negotiation",
    "n310-test-boundary-value-inputs",
    "n311-validate-null-and-empty-fields",
    "n312-test-timeout-handling",
    "n313-verify-crud-operation-integrity",
    "n314-test-concurrent-request-handling",
    "n315-validate-header-propagation",
    "n316-test-webhook-delivery",
    "n317-run-regression-suite",
    "n318-track-defect-density",
    "n319-validate-api-versioning-behavior",
    "n320-test-ssl-tls-enforcement",
    "n321-verify-caching-headers",
    "n322-validate-correlation-id-propagation",
    "n323-test-bulk-operation-endpoints",
    "n324-verify-audit-log-generation",
    "n325-validate-search-and-filter-queries",
    "n326-test-file-upload-and-download",
    "n327-verify-sorting-behavior",
    "n328-test-event-driven-api-triggers",
    "n329-validate-ip-allowlist-enforcement",
    "n330-test-api-gateway-routing",
    "n331-verify-third-party-oauth-integration",
    "n332-test-multipart-form-data-handling",
    "n333-validate-retry-after-header-compliance",
    "n334-test-soft-delete-behavior",
    "n335-validate-graphql-depth-limits",
    "n336-test-long-polling-support",
    "n337-verify-enum-value-restrictions",
    "n338-measure-api-consumer-satisfaction",
]

if AGENT_NAME not in VALID_AGENTS:
    print(f"ERROR: '{AGENT_NAME}' is not a valid API tester agent name.")
    print("Valid agents:")
    for a in VALID_AGENTS:
        print(f"  {a}")
    exit(1)
```

### 0c. Bootstrap (environment, prerequisites, RUN_ID)

Identical to orchestration-full Phase 0a, 0b, and 0b-i. Generate RUN_ID with run_type:
`"single:[AGENT_NAME]"`. Initialize state file.

This includes writing `.understandignore` during bootstrap to exclude all AI agent
directories and run outputs from any `/understand` or `/understand-diff` analysis,
with the same merge-not-overwrite rule and post-processing filter applied to any
diff output produced during the run.

### 0d. Build full endpoint list

Identical to orchestration-full Phase 0d. All endpoints are tested — no scoping.

---

## Phase 1 — Agent execution order for this run

The run uses exactly 4 agents per endpoint, in this fixed order:

```
1. [AGENT_NAME]           ← the single API tester agent the user specified
2. test-case-creator      ← general: final test case sweep
3. run-cicd-pipeline      ← general: pipeline integrity check
4. bug-reporter           ← general: bug sweep
```

This list is fixed for the entire run. It does not change between endpoints.

---

## Phase 2 — Per-endpoint loop

For EACH endpoint E in the endpoint list, execute the following in full:

### 2a. Mark endpoint in-progress (identical to orchestration-full 2a)

### 2b. Run the 4 agents in order

For EACH of the 4 agents:

**Step B1 — Skip if already completed** (resumption support — same as orchestration-full)

**Step B2 — Mark agent in-progress**

**Step B3 — Invoke the agent**

Agent spec path:
- For the API tester agent: `agents/api-tester/[AGENT_NAME]/agent.md`
- For general agents: `agents/general/[agent-name]/agent.md`

Invocation is identical to orchestration-full Step B3 (claude-code vs ollama, 300s timeout,
stdout/stderr written to `results/runs/[RUN_ID]/agents/[AGENT_NAME]/[E.endpoint_id]-*.txt`).

**Step B4 — Per-step guardrail loop**

IDENTICAL to orchestration-full Step B4. All four guardrails apply:

- **G1**: Test case creation mandatory for every step
- **G2**: Postman collection update mandatory for every HTTP call, tc_id must match
- **G3**: Bug flow mandatory for every FAIL — live capture → pause → ffmpeg → reproduce → finalize → resume
- **G4**: "Code Update" label for non-applicable steps — no bug report, no blocking

The bug reproduction flow (ffmpeg screen capture, step-by-step reproduction, bug reporter
finalization) is identical to orchestration-full. The bug report must record:
- `"found_by_agent": AGENT_NAME` for the API tester agent's bugs
- `"found_by_agent": "bug-reporter"` for bugs surfaced during the bug-reporter general sweep
- `"test_case_id": tc_id` — the test case number that identified the bug

**Step B5 — Agent completion**

Identical to orchestration-full Step B5 including the B5-CHECK guardrail.

### 2c. Mark endpoint complete

Identical to orchestration-full 2c.

---

## Phase 3 — Finalize run

Identical to orchestration-full Phase 3.

The pipeline summary includes:
```json
{
  "run_type": "single",
  "agent_under_test": "[AGENT_NAME]",
  "general_agents": ["test-case-creator", "run-cicd-pipeline", "bug-reporter"],
  "agents_per_endpoint": 4
}
```

---

## Output attribution

Every test case in `results/test-case-registry.json` produced by this run includes:
```json
{
  "agent": "[AGENT_NAME or general agent name]",
  "run_id": "[RUN_ID]",
  "run_type": "single"
}
```

Every bug report in `results/bug-reports/` includes:
```json
{
  "found_by_agent": "[agent name]",
  "test_case_id": "[tc_id]",
  "run_id": "[RUN_ID]"
}
```

---

## Resumption

Same behavior as orchestration-full. If a prior incomplete single run exists for the
same AGENT_NAME, offer Resume or Start Fresh.
