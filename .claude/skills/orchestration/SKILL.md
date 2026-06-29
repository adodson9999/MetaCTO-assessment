---
name: orchestration
description: >
  Smart test run that detects changes in the DummyJSON API documentation and the
  Understand Anything knowledge graph before testing. Re-runs cli-factory on
  https://dummyjson.com/docs to detect API changes, runs /understand-diff to map
  impact, runs /understand fresh to rebuild the graph, then retests only the
  changed endpoints and all other methods sharing their URL family. On first run
  (no prior knowledge graph) behaves identically to orchestration-full.
  Trigger with "orchestration", "run smart orchestration", "run changed tests",
  or "test what changed".
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

# orchestration

Change-aware test run. Detects what changed in the API docs and codebase,
rebuilds the knowledge graph, then retests only the affected endpoints.
All invariants from orchestration-full apply here — the only difference is
Phase 0 which scopes the endpoint list before testing begins.

All agents live in `agent-foundry/agents/`. All results go into
`agent-foundry/results/runs/[RUN_ID]/`. Paths are relative to the MetaCTO-Assessment
project root.

---

## Non-negotiable invariants

All 10 invariants from orchestration-full apply identically here, including invariant 1
(test-case-creator is the sole writer to test-case-registry.json; api-tester agents write
findings to staging only; G1b enforces the 3-attempt retry before any ERROR sentinel is
written). Additionally:

11. **Change detection always runs first.** No agent is invoked against any endpoint
    until all change detection steps (0d through 0h) are complete and the RETEST_ENDPOINTS
    list is finalized. Testing on stale scope is a broken run.

12. **The knowledge graph backup is always made before /understand runs.** Never overwrite
    the existing `.understand-anything/knowledge-graph.json` without first renaming it to
    `.understand-anything/knowledge-graph.[TIMESTAMP].json`. Loss of the prior graph breaks
    diff capability.

13. **The diff determines scope — nothing else.** The RETEST_ENDPOINTS list comes
    exclusively from the /understand-diff output and the cli-factory diff output.
    Manual endpoint additions or removals are not permitted during a smart run.
    Use orchestration-full for an override.

14. **On first run (no prior graph), behave as orchestration-full.** If
    `.understand-anything/knowledge-graph.json` does not exist, skip change detection
    and run all endpoints. Log: "First run detected — running full scope."

---

## Phase 0 — Bootstrap

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
- `agent-foundry/agents/` exists
- `ffmpeg` on PATH
- `agent-foundry/config.toml` exists
- If ENV_MODE=ollama: Ollama responds at `${OLLAMA_BASE_URL}/models`
- Create `agent-foundry/results/runs/` and subdirectory structure

Generate RUN_ID: `RUN-[YYYYMMDD-HHMMSS]`. Initialize state with `run_type: "smart"`.

---

## Phase 0c — Check for first run

```bash
if [ ! -f ".understand-anything/knowledge-graph.json" ]; then
  echo "First run — no prior knowledge graph found. Running full scope."
  FIRST_RUN=true
fi
```

If FIRST_RUN=true: skip to Phase 0h (build full endpoint list), then proceed as
orchestration-full for all subsequent phases.

---

## Phase 0d — Re-run cli-factory on DummyJSON docs

Re-run the CLI factory to generate a fresh CLI from the live DummyJSON docs:

```bash
# Snapshot the current CLI for comparison
cp CLI/dummyjson-pp-cli CLI/dummyjson-pp-cli.prev 2>/dev/null || true

# Invoke cli-factory skill targeting https://dummyjson.com/docs
# Mode: reprint — regenerates the CLI from the live docs
# Output: CLI/dummyjson-pp-cli (overwrite after build completes)
```

After cli-factory completes, diff old vs new CLI:

```bash
CLIFFDIFF=$(diff \
  <(./CLI/dummyjson-pp-cli.prev --list-endpoints --output json 2>/dev/null || echo "{}") \
  <(./CLI/dummyjson-pp-cli --list-endpoints --output json 2>/dev/null || echo "{}") \
)

if [ -z "$CLIFFDIFF" ]; then
  CLI_CHANGED=false
  echo "DummyJSON API: no changes detected in CLI diff."
else
  CLI_CHANGED=true
  echo "DummyJSON API: changes detected."
  echo "$CLIFFDIFF" > agent-foundry/results/runs/${RUN_ID}/cli-diff.txt
fi
```

Extract added, removed, and modified endpoints from the diff into:
```json
{
  "added": [{"method": "GET", "path": "/new-resource"}],
  "removed": [{"method": "DELETE", "path": "/old-resource"}],
  "modified": [{"method": "POST", "path": "/products"}]
}
```
Save to `agent-foundry/results/runs/${RUN_ID}/cli-changes.json`.

---

## Phase 0e — Backup existing knowledge graph

```bash
TIMESTAMP=$(date -u +"%Y%m%dT%H%M%SZ")
KG_BACKUP=".understand-anything/knowledge-graph.${TIMESTAMP}.json"

cp .understand-anything/knowledge-graph.json "${KG_BACKUP}"
echo "Backed up knowledge graph to: ${KG_BACKUP}"
```

Record `KG_BACKUP` path in state file. This backup is the baseline for the diff.

---

## Phase 0f — Merge .understandignore and run /understand-diff

### 0f-i. Merge .understandignore before running diff

The `.understandignore` file lives at `.understand-anything/.understandignore` (already
exists in this project). Merge required entries — never overwrite:

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
    echo "Added to .understandignore: $entry"
  fi
done
```

Apply this as a post-processing filter to all diff output: any node whose file path
starts with an ignored prefix is removed from scope before RETEST_ENDPOINTS calculation.

### 0f-ii. Run /understand-diff

Run `/understand-diff` to get the exact impact map of what changed in the codebase since
the last `/understand` run. This must run BEFORE `/understand` so it captures the delta
between the backed-up graph and the current source.

**If ENV_MODE = "claude-code":**
```
/understand-diff
```
Capture output: `agent-foundry/results/runs/${RUN_ID}/understand-diff-output.txt`

**If ENV_MODE = "ollama":**
```bash
node ~/.understand-anything/repo/src/commands/understand-diff.js \
  > agent-foundry/results/runs/${RUN_ID}/understand-diff-output.txt 2>&1
```

### 0f-iii. Filter and parse diff output

Parse the raw diff output. Apply a post-processing filter to strip any node whose
file path starts with an ignored prefix:

```python
IGNORED_PREFIXES = [
    "agent-foundry/agents/",
    "agent-foundry/results/",
    "agent-foundry/memory/",
    "agent-foundry/tools/",
    "agent-foundry/evolvers/",
    "agent-foundry/.venv/",
    "CLI/",
    ".understand-anything/intermediate/",
    ".understand-anything/knowledge-graph.",
    "node_modules/",
]

def is_ignored(file_path: str) -> bool:
    return any(file_path.startswith(p) for p in IGNORED_PREFIXES)

# Filter all entries
changed_files = [f for f in raw_changed_files if not is_ignored(f)]
changed_functions = [fn for fn in raw_changed_functions
                     if not is_ignored(fn.get("file", ""))]

# Track what was filtered out for auditability
ignored_paths_filtered = [f for f in raw_changed_files if is_ignored(f)]
```

Save filtered result to `agent-foundry/results/runs/${RUN_ID}/understand-diff-nodes.json`:
```json
{
  "changed_files": ["src/products/handler.ts", "src/auth/middleware.ts"],
  "changed_functions": ["getProducts", "validateToken"],
  "affected_paths": ["/products", "/auth"],
  "ignored_paths_filtered_out": ["agent-foundry/agents/api-tester/validate-request-payloads/subagent/api-tester-validate-request-payloads.md"]
}
```

If `ignored_paths_filtered_out` is non-empty, log INFO:
"[N] agent/result paths removed from diff scope — expected and correct."

---

## Phase 0g — Run fresh /understand

Regenerate the knowledge graph:

**If ENV_MODE = "claude-code":**
```
/understand
```

**If ENV_MODE = "ollama":**
```bash
node ~/.understand-anything/repo/src/commands/understand.js \
  > agent-foundry/results/runs/${RUN_ID}/understand-output.txt 2>&1
```

Wait for completion. Assert `.understand-anything/knowledge-graph.json` exists and
its `mtime` is newer than the backup. If not: log ERROR and abort.

Diff the new graph against the backup to extract changed nodes:
```bash
python3 -c "
import json, sys
old = json.load(open('${KG_BACKUP}'))
new = json.load(open('.understand-anything/knowledge-graph.json'))
old_nodes = {n['id']: n for n in old.get('nodes', [])}
new_nodes = {n['id']: n for n in new.get('nodes', [])}
changed = [nid for nid in set(list(old_nodes) + list(new_nodes))
           if old_nodes.get(nid) != new_nodes.get(nid)]
print(json.dumps({'changed_node_ids': changed}))
" > agent-foundry/results/runs/${RUN_ID}/kg-diff-nodes.json
```

---

## Phase 0h — Build RETEST_ENDPOINTS list

Combine scope from three sources:

1. **CLI diff changed endpoints** — from `agent-foundry/results/runs/${RUN_ID}/cli-changes.json`
   (added + modified). For each changed endpoint, add all endpoints in its URL family
   (all methods on that path prefix).

2. **Understand-diff affected paths** — from `agent-foundry/results/runs/${RUN_ID}/understand-diff-nodes.json`.
   For each `affected_path`, add all endpoints whose path starts with that prefix.

3. **KG diff changed nodes** — from `agent-foundry/results/runs/${RUN_ID}/kg-diff-nodes.json`.
   For each changed node, look up which endpoints reference it in the knowledge graph
   and add those endpoints' full URL families.

Deduplicate and sort. Save to `agent-foundry/results/runs/${RUN_ID}/retest-endpoints.json`.

**If RETEST_ENDPOINTS is empty and CLI_CHANGED = false:**

```
No changes detected — nothing to retest.
Run orchestration-full to force a full run.
```
Write final state as completed with 0 endpoints tested. Exit 0.

**If RETEST_ENDPOINTS is empty but CLI_CHANGED = true:**

```
WARNING: CLI changed but could not map to specific endpoints — running all endpoints.
```
Set RETEST_ENDPOINTS = all endpoints (full scope fallback).

Update `orchestration-state.json` with RETEST_ENDPOINTS, each with `status: "pending"`.

---

## Phase 1 — Agent list

Identical to orchestration-full Phase 1. All 40 API tester agents + 3 generals, same order.

**40 API tester agents** (exact folder names under `agent-foundry/agents/api-tester/`):

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

**3 general agents** (exact folder names under `agent-foundry/agents/general/`):

```
test-case-creator
run-cicd-pipeline
bug-reporter
```

**Agent spec file resolution:**

```bash
# API tester:
SPEC="agent-foundry/agents/api-tester/${AGENT_NAME}/subagent/api-tester-${AGENT_NAME}.md"
RUNPY="agent-foundry/agents/api-tester/${AGENT_NAME}/subagent/run.py"

# General:
SPEC="agent-foundry/agents/general/${GEN_NAME}/subagent/general-${GEN_NAME}.md"
RUNPY="agent-foundry/agents/general/${GEN_NAME}/subagent/run.py"
```

---

## Phase 2 — Per-endpoint loop

Identical to orchestration-full Phase 2 in every detail, but applied only to endpoints
in RETEST_ENDPOINTS rather than all endpoints.

The per-step guardrails (G1, G1b, G2, G3, G4) are identical and non-negotiable.

G1 (Findings staging): api-tester agents write per-step raw results to
`agent-foundry/results/runs/${RUN_ID}/staging/${AGENT_NAME}/${E_ID}-findings.json`.
They do NOT write to test-case-registry.json.

G1b (test-case-creator invocation): fires once after each api-tester agent completes all
steps for the endpoint. Reads staging file, invokes test-case-creator, validates output
is a non-empty JSON array. Retries up to 3 times with escalating format enforcement.
test-case-creator is the ONLY writer to test-case-registry.json. On 3-attempt failure:
writes one ERROR sentinel, logs CRITICAL, continues.

G2 (Postman collection): `create-postman-collection` runs as one of the 40 agents
per-endpoint and handles Postman collection creation/update for that endpoint. The
orchestrator asserts after `create-postman-collection` completes that
`agent-foundry/results/postman-collection.json` was updated with at least one item
whose `name` matches a tc_id from this endpoint's test cases.

The bug flow (live capture → pause → ffmpeg → reproduce → finalize → resume) is
identical to orchestration-full.

Agent invocation (per ENV_MODE):

Create staging directory before each api-tester agent invocation:
```bash
mkdir -p "agent-foundry/results/runs/${RUN_ID}/staging/${AGENT_NAME}"
```

**claude-code:**
```python
spec_content = open(SPEC).read()
staging_path = f"agent-foundry/results/runs/{RUN_ID}/staging/{AGENT_NAME}/{E_ID}-findings.json"
# Invoke via Agent tool: spec_content = system prompt
# endpoint_context + staging_path = user message (agent writes findings here, not registry)
```

**ollama:**
```bash
FORGE_WORKSPACE="$(pwd)/agent-foundry" \
  python3 "${RUNPY}" \
  > agent-foundry/results/runs/${RUN_ID}/agents/${AGENT_NAME}/${E_ID}-stdout.txt \
  2> agent-foundry/results/runs/${RUN_ID}/agents/${AGENT_NAME}/${E_ID}-stderr.txt
```

Timeout: 300 seconds. On non-zero exit or timeout: write synthetic ERROR entry to staging
(not registry), then still invoke G1b so test-case-creator runs against that staging data.

---

## Phase 3 — Finalize run

Identical to orchestration-full Phase 3 with these additions:

### 3e. Write change detection summary

```json
{
  "cli_changed": true,
  "cli_diff_path": "agent-foundry/results/runs/[RUN_ID]/cli-diff.txt",
  "cli_changes_path": "agent-foundry/results/runs/[RUN_ID]/cli-changes.json",
  "understand_diff_path": "agent-foundry/results/runs/[RUN_ID]/understand-diff-output.txt",
  "understand_diff_nodes_path": "agent-foundry/results/runs/[RUN_ID]/understand-diff-nodes.json",
  "kg_backup_path": "[KG_BACKUP]",
  "retest_endpoints_path": "agent-foundry/results/runs/[RUN_ID]/retest-endpoints.json",
  "retest_endpoint_count": N,
  "total_endpoint_count": M,
  "skipped_endpoint_count": "M - N"
}
```

Write to `agent-foundry/results/runs/${RUN_ID}/change-detection-summary.json`.

Write full pipeline summary to `agent-foundry/results/runs/${RUN_ID}/pipeline-summary.json`
(same format as orchestration-full with `"run_type": "smart"`).

Update `agent-foundry/results/test-case-registry.json`.
Regenerate `agent-foundry/results/bug-reports/index.json`.
Set `completed: true` in `orchestration-state.json`.

Exit code: any CRITICAL/HIGH bugs → exit 1, else exit 0.

---

## Resumption

If invoked and `agent-foundry/results/runs/` contains an incomplete smart run
(`orchestration-state.json` with `"completed": false` and `"run_type": "smart"`), offer:
1. **Resume** from the last completed agent (skips change detection — uses existing RETEST_ENDPOINTS).
2. **Start Fresh** with a new RUN_ID (re-runs change detection).

Default to Resume if no input within 10 seconds.
