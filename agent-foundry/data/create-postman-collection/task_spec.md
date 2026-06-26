# Task spec — api-tester / create-postman-collection ("n601")

## The task
The Postman Collection Creator. Read the test-case registry produced by the sibling n600
agent (`results/test-case-registry.json`) plus its summary, assert the registry has zero
gaps, filter to test cases where `involves_http_call = true`, build exactly one Postman
Collection v2.1 request item per HTTP test case, group items into per-agent folders,
assemble a single collection at `results/postman-collection.json`, read it back and
recursively count the request items, assert that count equals the registry's HTTP
test-case count, write a gaps file for any unrepresented `tc_id`, write a summary, and run
a Newman validation. n601 makes **no HTTP calls of its own** — it is a pure JSON→JSON
transform.

## Owner constraints (honored)
- **Backend = Ollama** (`config.toml [backend].provider = "ollama"`), and **the Ollama
  server is NOT started by this build.** `scripts/phase4_postman_run.sh` probes the
  configured endpoint and FATALs with instructions if it is down; it never launches
  `ollama serve`. The deterministic core (gold, oracle, CLI, Newman) needs no LLM and is
  fully verified; the live four-agent leaderboard is staged until Ollama is up.
- **DummyJSON is never used or modified.** n601 does not touch it (the task is a registry
  transform, not an HTTP test). Verified: the repo-root DummyJSON `package.json` was left
  pristine; Newman is installed in an isolated `tools/newman/` with its own `package.json`,
  not in the DummyJSON project's `node_modules`.
- **"Just create the agent."** The full four-framework forge + judge + evolution layer was
  built; no external/cloud service is contacted.

## Inputs
- `results/test-case-registry.json` — the n600 deliverable: a JSON array of test cases,
  each with `tc_id`, `agent`, `step_text`, `involves_http_call` (production CLI path).
- `results/test-case-registry-summary.json` — the n600 summary (gap pre-check).
- For the **forge measurement**, the four agents and the gold read the bundled FIXTURE
  (`data/create-postman-collection/registry_fixture.json` + `registry_summary_fixture.json`)
  directly, NOT the shared `results/` file — this keeps the measurement deterministic and
  isolated from the concurrently-running n600 build. The fixture is a 16-case registry
  (14 HTTP across 5 agents + 2 non-HTTP) hand-built to exercise every extraction branch:
  all six HTTP methods, the default method/path, all four body triggers, all five header
  triggers, the primary status regex, the arrow fallback regex, and the no-status (status
  0) case.

## What a correct output looks like
`results/postman-collection.json` is a valid Postman Collection v2.1 whose `item` array
holds one folder per distinct agent (first-appearance order), each folder holding one
request item per HTTP test case. Every item `name` is exactly a `tc_id`; its
`request.method`/`url`/`header`/`body` and its `event[0].script.exec` test lines are
derived from `step_text` by the spec's regexes/triggers; the collection has the five
`{{base_url}}` … `{{idempotency_key}}` variables. The recursive request-item count equals
the registry HTTP count (gap_count = 0 → 100% Postman Coverage Rate), and the collection
loads cleanly through Newman's own `postman-collection` SDK.

## Forge design — what each framework agent emits
Because the n601 algorithm is fully deterministic, the part that varies per framework is
the **Postman Generation Contract** the agent's LLM emits: the thirteen knobs of steps
3–8 (`filter_field`, the method/path/status regexes + their defaults, the four
`body_triggers`, the ordered five-entry `header_triggers`, `group_by`, `base_url`, the
five `variables`, `collection_name_prefix`). The shared deterministic harness
(`agents/common/postman.py`) applies that contract to the registry, builds + reads back +
recursively counts the collection, writes gaps/summary, and runs Newman — identical for
all four agents — so leaderboard differences are attributable to contract quality alone.
A spec-correct contract reproduces the gold collection (100% coverage, full fidelity); a
contract that swaps the status regexes, drops a header trigger, "corrects" a backslash,
or uses a wrong `filter_field`/`group_by` diverges and scores lower.

## Metric
- **Headline (QA finding):** Postman Coverage Rate = recursive request-item count ÷
  registry HTTP test-case count × 100. Pass = 100% (gap_count = 0) **and** the Newman
  validation passes. Against the fixture a correct contract → 100%, gap_count 0.
- **Judge ranking:** Postman Contract Fidelity = % of the 14 gold scenario tokens the
  agent's built collection reproduces (`judge/create-postman-collection/metric.json`).
  Newman validity is a non-aborting WARNING and is excluded from fidelity.

## Production artifact
`scripts/postman_collection_cli.py` is the faithful standalone n601 program: it runs all
twelve spec steps against the real `results/` registry with the spec's exit codes and
stderr/stdout messages (`--seed-from-fixture` to use the bundled fixture when n600 has not
yet run). The four forge agents emit the contract this CLI consumes.

## Newman note
Newman 6.x has no `--dry-run` flag (and `newman run` alone would fire every request at
base_url). The faithful, request-free "validate the collection schema" check loads the
collection through `postman-collection` — the exact SDK Newman uses on load
(`tools/newman/validate_collection.js`). Verified: it returns valid for the gold
collection and rejects a malformed one.
