# Task Spec — API Idempotency-of-Endpoints Tester

> Position **api-tester**, workflow **test-idempotency-of-endpoints**. Captured in Phase 2
> of forge-agents. This is the single task all four agents (LangGraph, CrewAI, Claude Code
> subagent, Claude Agent SDK) implement, and the basis for the judge's numeric metric.
> Coexists with the other api-tester builds in this foundry.
>
> **Backend = Ollama (local, air-gapped)** — the committed `config.toml`
> `[backend].provider` default; the run/evolve scripts set `FORGE_PROVIDER=ollama` explicitly.
> Ollama must already be running — the scripts do **not** start the server; they health-check
> `:11434` and fail with instructions if it is down. Model comes from
> `[backend].ollama_model` (e.g. `qwen2.5:14b-instruct`).
> _(History: the first build ran on Claude per the owner's "just the claude option"; the
> backend was later switched to Ollama. To go back to Claude, set
> `FORGE_PROVIDER=claude-haiku` with `ANTHROPIC_API_KEY` in the env.)_

## The task

Given a **running API** and a per-collection **idempotency contract**, the agent produces
an **idempotency test plan** for one collection. A deterministic harness executes the plan:
it sends each idempotent request (PUT, DELETE) **three times with one reused
Idempotency-Key**, and the create request (POST add) three times with a primary key plus
once with a **fresh** key, capturing every response **byte-for-byte**. It then confirms,
per endpoint:

- the second and third response **codes** exactly match the first,
- the second and third response **bodies** are **byte-for-byte identical** to the first
  (string comparison, **not** semantic JSON equality),
- the target holds **exactly one record** after all three requests (not three), and
- a **fresh** Idempotency-Key creates a **distinct** record.

One collection contract in → one structured idempotency test plan out → one scored
scenario table.

## Target — DummyJSON, tested AS-IS (writes are non-persistent → target never modified)

DummyJSON's in-memory dataset is **deepFrozen**; its write controllers (`src/controllers/*.js`)
**return computed objects without persisting** anything. Verified live: after a full run,
`GET /products/1` still returns the original title and `total` is still 194. So issuing
real PUT/DELETE/POST does **not** modify the target — this is the one task that writes, and
it is safe precisely because of that non-persistence.

Its real idempotency behavior (the QA findings):

- **PUT `/<col>/<id>`** → `200`; a deterministic merge of the body over the frozen record.
  Replaying with one Idempotency-Key → **byte-identical** bodies. **Idempotent.** ✓
- **DELETE `/<col>/<id>`** → `200`; the body carries `deletedOn: new Date().toISOString()`,
  a **fresh timestamp each call**, so replays **DIFFER byte-for-byte**. **Not byte-for-byte
  idempotent.** ✗ (status is consistent; only the timestamped body diverges.)
- **POST `/<col>/add`** → `201`; `id = frozenData.<col>.length + 1` (constant), so a replay
  **and a fresh-key request** return the **same id**. The **Idempotency-Key header is
  ignored**; a new key does **not** create a distinct record. ✗

The idealized idempotency contract (consistent status + byte-identical body on replay,
exactly one record, a fresh key creating a distinct record) is encoded per-scenario as the
`ideal` token; the gold records the API's **real** token. Where they differ is a genuine QA
finding about DummyJSON, **not** an agent failure (mirrors the pagination / request-payloads
philosophy in this foundry).

### Literal-request mappings (and why)

- **"Generate a UUID v4 Idempotency-Key"** → the gated plan uses **fixed literal** UUID-shaped
  keys (one reused across the three replays, a distinct one for the fresh-key check). The
  target ignores the header, so the value never perturbs a token; pinning it keeps the plan
  byte-stable and reproducible across all four agents and the gold. Per-request UUID
  *generation* is the executor's concern, not the plan's.
- **"Query the DB with psql/mysql: SELECT COUNT(*) = 1"** → there is **no SQL database** and
  writes do not persist, so the count assertion is mapped onto a **read-only state-effect
  probe**: `GET` the target record (present exactly once → count 1; by-id addressing makes
  triplication structurally impossible) and, for the fresh-key check, compare the
  fresh-key response to the primary-key response. The mapping (and the fact that
  "exactly one record" holds for **structural** reasons — by-id addressing + non-persistence
  — not because of an Idempotency-Key dedup layer) is itself a documented finding.
- **"POST endpoints with documented Idempotency-Key support"** → DummyJSON documents **none**,
  so per the task's own selection rule POST is **not** an idempotent endpoint. It is exercised
  as **informational** scenarios (to surface the ignored-header finding) but is **excluded
  from the headline Compliance Rate denominator**.

## Inputs

- **Contract:** `data/test-idempotency-of-endpoints/idempotency_spec.json` — the collection
  catalogue + `id_field` + `target_id`. This is what the agents are briefed from.
- **Collections (6):** `/products`, `/posts`, `/comments`, `/todos`, `/users`, `/recipes`
  (each has a record at id 1, a PUT/DELETE-by-id endpoint, and an `/add` create endpoint).
- **Target API:** local DummyJSON on `:8899`, booted air-gapped (no Mongo):
  `JWT_SECRET=forge_test_secret MONGODB_URI= NODE_ENV=development PORT=8899 LOG_ENABLED=false node index.js`.

## What a correct / good agent output looks like

Each agent emits, per collection, a single five-key plan object (the debate-gated "ask"):
`collection, id_field, target_id, idempotent_requests, create_request`, where:

- `idempotent_requests` = exactly two objects — `put {PUT, /<col>/<id>, body
  {"title":"idempotency-probe"}, idempotency_key A, replays 3}` and `delete {DELETE,
  /<col>/<id>, body null, idempotency_key B, replays 3}`.
- `create_request` = one object — `post {POST, /<col>/add, body {"title":"idempotency-probe"},
  idempotency_key C, second_key D, replays 3}`.

The harness then writes `results/runs/<run>/<agent>.{json,cases.json}` with the per-(collection,
scenario) **observed token** from the real replayed requests.

## The metric

Two layers, both numeric and machine-read from `results/`:

1. **Headline (each agent emits): Idempotency Compliance Rate** =
   (idempotent endpoint cases — PUT, DELETE across all collections — where all three replays
   return identical code AND byte-for-byte identical body AND the target holds exactly one
   record ÷ total idempotent endpoint cases) × 100. A property of the *target API*; a faithful
   agent reproduces the gold value (empirically **50%** — PUT compliant, DELETE not
   byte-idempotent). A **secondary Idempotency Correctness Rate** (empirically **77.78%**)
   also credits the POST fresh-key finding.

2. **Judge's rank key — Idempotency-Test Fidelity (0–100):** the fraction of gold
   `(collection, scenario)` cases where the agent's harness-observed token equals the gold
   token. **Uncovered scenarios score 0.** This rewards the framework that builds the correct
   PUT/DELETE replay probes (right method, right `/<col>/<target_id>` path, the **same** key
   reused across all three replays, `replays = 3`) and the POST probe with a primary + distinct
   fresh key. Pass = 100%; fail = any scenario uncovered or mis-constructed.

> **Why fidelity, not raw compliance, ranks the agents:** all four drive the same API, so a
> correct run yields the same compliance rate. What differs between frameworks is test
> fidelity — plan coverage and request-construction quality.

## Scenario set (9 per collection — the fidelity denominator = 54)

`put_status_consistent / put_body_byte_identical / put_single_record`,
`delete_status_consistent / delete_body_byte_identical / delete_single_record`,
`post_status_consistent / post_body_byte_identical / post_new_key_distinct`.
Defined once in `agents/common/idempotency_spec.py` (shared by gold + harness).

## Ground truth (already built)

`data/test-idempotency-of-endpoints/gold.json` + `gold/<collection>.json` — produced by
`build_gold.py`, the deterministic **reference** (not one of the four agents). It authors the
contract, derives the canonical correct plan, executes every request against the live API
(real replayed writes), and records the **real** observed token per scenario. Rebuild any
time with `BASE_URL=http://localhost:8899 python3 data/test-idempotency-of-endpoints/build_gold.py`.

**Empirical result:** 6 collections · 9 scenarios each · 54 total · 42 API-ideal →
Correctness 77.78%; idempotent-endpoint cases 6/12 pass → **Compliance Rate = 50%**. The
failures are real DummyJSON characteristics and legitimate QA findings:
- `delete_body_byte_identical` → false: each DELETE response embeds a fresh `deletedOn`
  timestamp, so replays diverge byte-for-byte.
- `post_new_key_distinct` → false: the Idempotency-Key header is ignored, so a fresh key
  returns the same `id` and creates no distinct record.

> **Determinism note.** `deletedOn` has millisecond precision; three sub-millisecond replays
> can share a timestamp and a non-idempotent DELETE can masquerade as idempotent. The harness
> spaces replays of one request by 6 ms (`INTER_REPLAY_DELAY_S`) so the ms tick advances and
> the latent non-idempotency surfaces deterministically. PUT/POST carry no time field and stay
> byte-identical regardless — confirmed stable across repeated gold builds.

## Constraints / invariants

- **Backend = Ollama (local, air-gapped)** — the foundry's committed `config.toml` default;
  the run/evolve scripts set `FORGE_PROVIDER=ollama` and do **not** start the server (they
  health-check `:11434` and fail with instructions if it is down).
- **Target is never modified.** DummyJSON's writes are non-persistent (deepFrozen data);
  verified by a post-run GET showing the record + `total` unchanged.
- **Plan generation is LLM-driven** (each framework's LLM builds the plan from the brief) —
  this is where the frameworks differ. **Execution + scoring are deterministic code** (the
  harness replays the requests, captures bodies byte-for-byte, runs the read-only state probes).
- **Sandbox:** all agent read/write/exec confined to `agent-foundry/` (plus local HTTP to the
  local target). Shared EverOS memory pool (common `project_id`/`app_id`, per-agent `agent_id`).
- **Implementable in all four frameworks** — plain orchestration (brief → plan), portable.

## Running the COMPLETE literal test

This build is a **faithful test of DummyJSON as-is** (Compliance = 50%). To run the *full*
literal task — where the `SELECT COUNT(*)` check is a real DB query and a compliant target
scores 100% — see **[`FULL_TEST_REQUIREMENTS.md`](FULL_TEST_REQUIREMENTS.md)**: it maps each
of the four literal assertions to the infrastructure it needs (idempotency-key middleware,
persistence, a SQL DB + `psql`/`mysql` client), gives a concrete setup checklist, and shows
the single env-gated `_record_count()` change that swaps the GET state-probe for a true
`COUNT(*)`. DummyJSON is left untouched; a full run means pointing `FORGE_TARGET_BASE_URL` at
an idempotency-capable, DB-backed target.

## Open defaults flagged for sign-off

1. Target = DummyJSON as-is, gold = real behavior. Headline Compliance is **50%** by the API's
   real contract, not 100% (PUT idempotent; DELETE not byte-idempotent).
2. "SELECT COUNT(*) = 1" realized via read-only GET state-effect probes (no SQL DB; writes
   non-persistent). POST excluded from the Compliance denominator (no documented key support).
3. Replay spacing = 6 ms so the `deletedOn` timestamp varies deterministically.
4. Idempotency keys are fixed literals in the plan; the executor sends them verbatim.
5. Rank key = Idempotency-Test Fidelity; headline = Idempotency Compliance Rate.
