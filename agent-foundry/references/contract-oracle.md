# Contract-conformance oracle — the manual tester's checklist, encoded

A fixed, **universal** table keyed by operation type — target-independent, so it can't be biased by
the target's own documentation or observed behaviour. Every api-tester agent maps its cases onto the
relevant rows and emits `expected_by_contract` **from this table** — never from the brief, the
target's docs, or observed behaviour.

The oracle is **bug-blind**: it encodes the *standard* and the *intended contract*, never the
*target's bugs*. It finds nothing on a correct API and surfaces the defect on a buggy one. The same
oracle applies to any API.

## 1. The contract oracle (target-independent)

| Operation | `expected_by_contract` (assert + report deviation) |
|-----------|----------------------------------------------------|
| Create (POST) | `201 Created` + `Location`/id returned + **read-back**: a follow-up GET returns the created resource |
| Read (GET) | `200`; body matches documented schema; `404` for a non-existent id |
| Update (PUT/PATCH) | `200`; **read-back reflects the change**; PATCH changes only the named fields |
| Delete (DELETE) | `2xx`; **read-back -> `404`** (resource is gone). *Record still retrievable -> deviation "not deleted".* |
| Idempotent replay | Replays produce the **same effect and response**; no duplicate side effect |
| List + sort | Output is **monotonic on the sort key** (asc/desc), **including nested keys**; invalid sort -> `400` |
| List + filter | **Every returned record matches** the predicate; count consistent; unknown filter per policy |
| Pagination | Pages **partition** the set (no overlap, no gap); correct `total`/limit/offset metadata |
| Validation | Malformed/invalid body -> `4xx` (usually `400/422`) with a machine-readable error; **never `5xx` on a well-formed request** |
| AuthN | Missing/expired/revoked credential -> `401` |
| AuthZ | Insufficient permission -> `403`; no cross-tenant data leak |
| Status semantics | Documented code returned exactly; success != error; `2xx` bodies aren't error envelopes |
| Headers | Standard headers present & correct (Content-Type, caching, Retry-After, etc.) |
| Documented capability | Every documented resource x method / field / filter is **implemented**; documented-but-`404`/ignored -> `missing_capability` deviation |

## 2. The `deviations[]` output (the findings channel)

Every case carries, and the run aggregates, findings. A **finding** is raised when
`observed != expected_by_contract` (a likely product bug) **or** when
`expected_by_docs != expected_by_contract` (the spec itself violates convention — also a
manual-tester finding). Findings are surfaced **even when the response is "acceptable" by the
target's own docs.**

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

The run emits `deviations[] = [every case with verdict=deviation]`. A deviation is **always
surfaced, never absorbed** by a lenient oracle.

## 3. Full-surface enumeration, incl. negatives-of-omission

Derive **every documented resource x every documented method** and **every documented field/param
including nested paths and date/range**. Attempt each. A documented capability that is
missing/ignored (`404`, unchanged result) is itself a `missing_capability` deviation.

## 4. Black-box read-back oracles

Every contract invariant must be checkable from the **response + a follow-up request** — never from
a DB row, server log, or injected instrumentation the target may not expose. Verify a delete by
GET-`404`, not a DB check; verify an update by GET reflecting the change. Where an old assertion
needed instrumentation the target lacks, it degrades to the observable black-box signal instead of
silently not running.

## 5. Repetition / soak for intermittent bugs

Run each case **N times** (the configured **soak** count) and flag **non-determinism**: a case whose
result varies across repeats is a `flaky`/`intermittent` deviation.

## 6. De-bias (remove behaviour-as-contract)

Every clause that encodes the target's quirk as the contract, and every `also_accept` that swallows
a standard code, is removed. The expectation is the contract-oracle value above, not the target's
observed behaviour.
