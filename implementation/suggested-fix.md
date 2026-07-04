# Suggested fix — make the agents test like a manual API tester

## The one idea

A manual API tester finds bugs by comparing **actual behaviour** against the **contract they carry in
their head** (REST/HTTP conventions + the intended spec), across the **whole surface**, and flagging
**every discrepancy** — regardless of what the vendor's docs happen to say. Reproduce exactly that:

> **Give every agent a universal contract oracle (independent of the target's own docs), have the
> harness compare observed-vs-contract for every case across the full surface, and emit a
> `deviations[]` findings report. Repeat each case to catch intermittent behaviour.**

This is bug-blind: the agent knows the *standard* and the *intended contract*, never the *target's
bugs*. It would find nothing on a correct API and surface the defect on a buggy one.

## The crux: decouple the oracle from the target's self-description

Today each agent's expectation is read from the **brief**, which encodes the target's own docs — so a
non-standard target (200-on-create, soft-delete) produces a non-standard expectation, and the
deviation matches the expectation and passes.

Fix: the **surface** (which endpoints/fields/params exist) still comes from the brief, but the
**expected behaviour comes from the operation's universal semantics**, not the brief. Two baselines
are compared:

- `expected_by_contract` — from the universal table below (REST/HTTP/RFC semantics of the operation).
- `expected_by_docs` — what the target's own spec claims (only if it differs).
- `observed` — filled by the harness.

A **finding** is raised when `observed ≠ expected_by_contract` (a likely product bug) **or** when
`expected_by_docs ≠ expected_by_contract` (the spec itself violates convention — also a manual-tester
finding). Findings are reported **even when the response is "acceptable" by the target's own docs.**

## 1. The contract oracle (the manual tester's checklist, encoded)

A fixed, universal table keyed by operation type — target-independent, so it can't be biased:

| Operation | `expected_by_contract` (assert + report deviation) |
|-----------|----------------------------------------------------|
| Create (POST) | `201 Created` + `Location`/id returned + **read-back**: a follow-up GET returns the created resource |
| Read (GET) | `200`; body matches documented schema; `404` for a non-existent id |
| Update (PUT/PATCH) | `200`; **read-back reflects the change**; PATCH changes only the named fields |
| Delete (DELETE) | `2xx`; **read-back → `404`** (resource is gone). *Record still retrievable → deviation "not deleted".* |
| Idempotent replay | Replays produce the **same effect and response**; no duplicate side effect |
| List + sort | Output is **monotonic on the sort key** (asc/desc), **including nested keys**; invalid sort → `400` |
| List + filter | **Every returned record matches** the predicate; count consistent; unknown filter per policy |
| Pagination | Pages **partition** the set (no overlap, no gap); correct `total`/limit/offset metadata |
| Validation | Malformed/invalid body → `4xx` (usually `400/422`) with a machine-readable error; **never `5xx` on a well-formed request** |
| AuthN | Missing/expired/revoked credential → `401` |
| AuthZ | Insufficient permission → `403`; no cross-tenant data leak |
| Status semantics | Documented code returned exactly; success ≠ error; `2xx` bodies aren't error envelopes |
| Headers | Standard headers present & correct (Content-Type, caching, Retry-After, etc.) |
| Documented capability | Every documented resource×method / field / filter is **implemented**; documented-but-`404`/ignored → deviation |

Each agent maps its cases onto the relevant rows and emits `expected_by_contract` from the table — not
from the brief.

## 2. The `deviations[]` output (the missing flow piece)

Extend the shared emit/execute contract so every case carries, and the run aggregates, findings:

```json
{
  "case": "<label>",
  "operation": "create|read|update|delete|list_sort|list_filter|pagination|validation|authn|authz|headers|capability",
  "request": { "method": "...", "path_role": "the create endpoint", "...": "..." },
  "expected_by_contract": { "status": 201, "invariants": ["location_present", "readback_reflects_create"] },
  "expected_by_docs": { "status": 200 },
  "observed": { "status": 200, "readback": "present", "...": "..." },
  "verdict": "deviation",
  "deviation_kind": "status_code | persistence | ordering | filter | schema | missing_capability | leak | header",
  "severity": "minor | major | critical",
  "note": "REST: resource creation returns 201 Created; observed 200."
}
```

The run emits `deviations[] = [every case with verdict=deviation]` — the manual-tester findings report.
This is separate from the agent's own pass/fail: **a deviation is always surfaced, never absorbed by a
lenient oracle.**

## 3. Full-surface enumeration (G8), incl. negatives-of-omission

Derive **every documented resource × every documented method** and **every documented field/param
including nested paths and date/range**. Attempt each. A documented capability that is missing/ignored
(`404`, unchanged result) is itself a `missing_capability` deviation. Catches per-resource CRUD gaps,
nested-field sort, and the missing date filter.

## 4. Black-box read-back oracles

Every contract invariant must be checkable from the **response + a follow-up request** — never from a
DB row, server log, or injected delay the target may not expose. (Verify a delete by GET-`404`, not a
DB check; verify an update by GET reflecting the change.) Where an old assertion needed instrumentation
the target lacks, it degrades to the black-box signal instead of silently not running.

## 5. Repetition / soak for intermittent bugs

Run each case **N times** and flag **non-determinism**: a case whose result varies across repeats is a
`flaky`/`intermittent` deviation. This is how the "`sortBy` **sometimes** doesn't work" class gets
caught — a single deterministic shot can miss it.

## 6. De-bias (remove behaviour-as-contract)

Delete every clause that encodes the target's quirk as the contract and every `also_accept` that
swallows a standard code — e.g. "assert the documented soft-delete markers," "write-persistence
persisted-or-simulated as the contract specifies," "follow-up read reflects the original," "create
`201` (also_accept `[200]`)." These are the source of the misses.

## How this catches the four (and the honest limits)

- **200-instead-of-201** → contract row Create expects `201`; observed `200` → `status_code` deviation.
- **No hard delete** → contract row Delete expects read-back `404`; record still retrievable →
  `persistence`/"not deleted" deviation.
- **Sorting / nested** → contract row List+sort expects monotonic incl. nested; unsorted → `ordering`
  deviation; **soak** catches the "sometimes."
- **Missing features (per-resource CRUD, date filter)** → surface enumeration attempts each; missing →
  `missing_capability` deviation.
- **Persistence across restart** → *out of scope* (needs a server restart, not observable in one run) —
  the one you agreed can be skipped. Optionally noted as an environment caveat, not asserted.

Honest limits: cross-restart/global state (needs restart), truly undocumented *intended* behaviour (no
contract to compare against), and very rare intermittents (bounded by the soak count).

## Where it lands (durable, not a 39-file hand-patch)

1. **Standard:** add one article — **G12: contract-conformance oracle + deviation findings** (with the
   contract table + `deviations[]` schema), tighten **G8** to full-surface incl. negatives-of-omission,
   and add the **soak** requirement. This makes every future build/update inherit it.
2. **Shared reference:** a `references/contract-oracle.md` (the table) the harness and agents cite.
3. **Emit/execute contract:** add `expected_by_contract` + `deviations[]` to the shared plan/result
   shape.
4. **Re-author the agents** through update-agent so they adopt it, and **de-bias** the CRUD /
   soft-delete / status-code / sort specs in the same pass.

I can implement all four — write the G12 article + the contract-oracle reference, extend the emit
contract, and sweep the 39 prompts (de-bias + add the contract oracle, `deviations[]`, surface rule,
and soak) — keeping every agent feature-agnostic and bug-blind, then re-verify. Say go and I'll start.
