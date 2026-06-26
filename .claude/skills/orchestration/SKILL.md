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

---

## Non-negotiable invariants

All 10 invariants from orchestration-full apply identically here. Additionally:

11. **Change detection always runs first.** No agent is invoked against any endpoint
    until all change detection steps (0c through 0g) are complete and the RETEST_ENDPOINTS
    list is finalized. Testing on stale scope is a broken run.

12. **The knowledge graph backup is always made before /understand runs.** Never overwrite
    the existing `knowledge-graph.json` without first renaming it to
    `knowledge-graph.[TIMESTAMP].json`. Loss of the prior graph breaks diff capability.

13. **The diff determines scope — nothing else.** The RETEST_ENDPOINTS list comes
    exclusively from the /understand-diff output and the cli-factory diff output.
    Manual endpoint additions or removals are not permitted during a smart run.
    Use orchestration-full for an override.

14. **On first run (no prior graph), behave as orchestration-full.** If
    `.understand-anything/knowledge-graph.json` does not exist, skip change detection
    and run all endpoints. Log: "First run detected — running full scope."

---

## Phase 0 — Bootstrap

Identical to orchestration-full Phase 0a and 0b (environment detection + prerequisite
verification). Generate RUN_ID. Initialize state with `run_type: "smart"`.

---

## Phase 0c — Check for first run

```bash
if [ ! -f ".understand-anything/knowledge-graph.json" ]; then
  echo "First run — no prior knowledge graph found. Running full scope."
  FIRST_RUN=true
fi
```

If FIRST_RUN=true: skip to Phase 0h (build full endpoint list), then continue
to Phase 1 as orchestration-full.

---

## Phase 0d — Re-run cli-factory on DummyJSON docs

Re-run the CLI factory to generate a fresh CLI from the live DummyJSON docs:

```bash
# Snapshot the current CLI binary for comparison
cp CLI/dummyjson-pp-cli CLI/dummyjson-pp-cli.prev 2>/dev/null || true

# Re-run cli-factory on the live docs
# This invokes the cli-factory skill targeting https://dummyjson.com/docs
# The skill will regenerate the CLI and output to ~/printing-press/library/dummyjson/
```

Invoke the `cli-factory` skill with:
- Target: `https://dummyjson.com/docs`
- Mode: reprint (use `references/printing-press-reprint/SKILL.md` mode)
- Output: `CLI/dummyjson-pp-cli` (overwrite in place after build)

After cli-factory completes:

```bash
# Diff the old CLI against the new CLI to detect API changes
CLIFFDIFF=$(diff \
  <(CLI/dummyjson-pp-cli.prev --list-endpoints --output json 2>/dev/null || echo "{}") \
  <(CLI/dummyjson-pp-cli --list-endpoints --output json 2>/dev/null || echo "{}") \
)

if [ -z "$CLIFFDIFF" ]; then
  CLI_CHANGED=false
  echo "DummyJSON API: no changes detected in CLI diff."
else
  CLI_CHANGED=true
  echo "DummyJSON API: changes detected. Diff:"
  echo "$CLIFFDIFF"
  # Save diff for later scope calculation
  echo "$CLIFFDIFF" > results/runs/${RUN_ID}/cli-diff.txt
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
Save to `results/runs/${RUN_ID}/cli-changes.json`.

---

## Phase 0e — Backup existing knowledge graph

```bash
TIMESTAMP=$(date -u +"%Y%m%dT%H%M%SZ")
KG_BACKUP=".understand-anything/knowledge-graph.${TIMESTAMP}.json"

cp .understand-anything/knowledge-graph.json "${KG_BACKUP}"
echo "Backed up knowledge graph to: ${KG_BACKUP}"
```

Record `KG_BACKUP` path in state file.

---

## Phase 0f — Run /understand-diff to map impact

Run `/understand-diff` to get the exact impact map of what has changed in the
codebase since the last `/understand` run. This must run BEFORE `/understand`
so it captures the delta between the backed-up graph and current source files.

### 0f-i. Write .understandignore before running diff

Before invoking `/understand-diff`, write (or overwrite) `.understandignore` at the
project root to exclude all AI agent directories and run outputs from the analysis.
These paths change on every run and must never influence the diff scope:

```bash
cat > .understandignore << 'EOF'
# AI agent implementations — excluded from understand-diff scope
agents/
agents/api-tester/
agents/general/

# Orchestration run outputs — change every run, not meaningful to diff
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

If `.understandignore` already exists, merge these entries rather than overwriting:
read the existing file, append any missing entries, write back. Never remove entries
that were already present.

### 0f-ii. Run /understand-diff

**If ENV_MODE = "claude-code":**
```
/understand-diff
```
Capture the output and save to `results/runs/${RUN_ID}/understand-diff-output.txt`.

**If ENV_MODE = "ollama":**
```bash
node ~/.understand-anything/repo/src/commands/understand-diff.js \
  > results/runs/${RUN_ID}/understand-diff-output.txt 2>&1
```

### 0f-iii. Filter and parse diff output

Parse the raw diff output. Before saving, apply a post-processing filter to strip any
node whose file path starts with any of the ignored prefixes — this acts as a second
safety net in case the ignore file was not honored:

```python
IGNORED_PREFIXES = [
    "agents/",
    "results/",
    "CLI/",
    ".understand-anything/intermediate/",
    ".understand-anything/knowledge-graph.",
]

def is_ignored(file_path: str) -> bool:
    return any(file_path.startswith(p) for p in IGNORED_PREFIXES)

# Parse diff output into changed_files, changed_functions, affected_paths
# Filter out any entry where the file_path is ignored
changed_files   = [f for f in raw_changed_files   if not is_ignored(f)]
changed_functions = [fn for fn in raw_changed_functions
                     if not is_ignored(fn.get("file", ""))]
```

Save the filtered result to `results/runs/${RUN_ID}/understand-diff-nodes.json`:
```json
{
  "changed_files": ["src/products/handler.ts", "src/auth/middleware.ts"],
  "changed_functions": ["getProducts", "validateToken"],
  "affected_paths": ["/products", "/auth"],
  "ignored_paths_filtered_out": ["agents/api-tester/n299-validate-request-payloads/agent.md"]
}
```

The `ignored_paths_filtered_out` field lists every path that was present in the raw diff
but removed by the filter — for auditability. If this list is non-empty, log INFO:
"[N] agent/result paths removed from diff scope — these are expected and correct."

---

## Phase 0g — Run fresh /understand

Now regenerate the knowledge graph with a fresh analysis:

**If ENV_MODE = "claude-code":**
```
/understand
```

**If ENV_MODE = "ollama":**
```bash
node ~/.understand-anything/repo/src/commands/understand.js \
  > results/runs/${RUN_ID}/understand-output.txt 2>&1
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
" > results/runs/${RUN_ID}/kg-diff-nodes.json
```

---

## Phase 0h — Build RETEST_ENDPOINTS list

Combine the scope from three sources:

1. **CLI diff changed endpoints** — from `cli-changes.json` (added + modified).
   For each changed endpoint, add its full URL family (all methods on that path).

2. **Understand-diff affected paths** — from `understand-diff-nodes.json`.
   For each `affected_path`, add all endpoints whose path starts with that prefix.

3. **KG diff changed nodes** — from `kg-diff-nodes.json`.
   For each changed node, look up which endpoints reference it in the knowledge graph
   and add those endpoints' full URL families.

Deduplicate and sort. Save to `results/runs/${RUN_ID}/retest-endpoints.json`.

**If RETEST_ENDPOINTS is empty and CLI_CHANGED = false:**
Log: "No changes detected — nothing to retest. Run orchestration-full to force a full run."
Write final state as completed with 0 endpoints tested. Exit 0.

**If RETEST_ENDPOINTS is empty but CLI_CHANGED = true:**
Log WARNING: "CLI changed but could not map to specific endpoints — running all endpoints."
Set RETEST_ENDPOINTS = all endpoints (full scope fallback).

Update `orchestration-state.json` with the RETEST_ENDPOINTS list, each with
`status: "pending"`.

---

## Phase 1 — Agent list

Identical to orchestration-full Phase 1. All 40 API tester agents + 3 generals, same order.

---

## Phase 2 — Per-endpoint loop

Identical to orchestration-full Phase 2 in every detail, but applied only to endpoints
in RETEST_ENDPOINTS rather than all endpoints.

The per-step guardrails (G1 through G4) are identical and non-negotiable.

The bug flow (live capture → pause → ffmpeg → reproduce → finalize → resume) is identical.

---

## Phase 3 — Finalize run

Identical to orchestration-full Phase 3, with these additions:

### 3e. Write change detection summary
```json
{
  "cli_changed": true/false,
  "cli_diff_path": "results/runs/[RUN_ID]/cli-diff.txt",
  "understand_diff_path": "results/runs/[RUN_ID]/understand-diff-output.txt",
  "kg_backup_path": "[KG_BACKUP]",
  "retest_endpoint_count": N,
  "total_endpoint_count": M,
  "skipped_endpoint_count": M - N
}
```
Write to `results/runs/${RUN_ID}/change-detection-summary.json`.

---

## Resumption

Same behavior as orchestration-full. If a prior incomplete smart run exists, offer
Resume or Start Fresh.
