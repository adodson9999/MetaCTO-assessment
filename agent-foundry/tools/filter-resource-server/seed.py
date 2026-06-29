#!/usr/bin/env python3
"""Deterministic seed data + filter contract for the local /resources SUT.

ONE source of truth for the seeded records and the documented filter contract,
shared by the server (tools/filter-resource-server/server.py), the gold builder,
and the harness's expected-count brief. Pure data + pure functions — no I/O, no
network, no LLM.

Why a purpose-built local server (and NOT DummyJSON)?
  The task mandates seeding the test database with EXACTLY 20 records of known
  field values and asserting the response count equals the known DB count. DummyJSON
  cannot be seeded (its writes are non-persistent / deep-frozen) and the build
  constraint is to never modify DummyJSON. A tiny air-gapped stdlib server seeded
  with the exact 20 records is therefore the only faithful system-under-test. It is
  read-only (GET), binds 127.0.0.1, and never touches DummyJSON.

Documented filter contract (the idealized, strict search/filter API):
  GET /<collection>?status=<v>&category=<v>
    - status   : ENUM filter, allowed values {"active", "inactive"}. An out-of-enum
                 value -> 400 with a message that references the "status" parameter.
    - category : free-form exact-match string filter (NOT enum-validated). Any value
                 is syntactically accepted; a value that matches no record yields a
                 200 response with an empty result list (e.g. category="C").
    - Filtering is AND across all applied recognized filters; a record is returned
      only if it matches every applied filter exactly.
    - Unknown / unrecognized query parameters -> 400 (STRICT policy) with a message
      that references the offending parameter name. This is the documented behavior
      for this endpoint, so it is NOT a documentation gap.
  The response body is {"<list_field>": [...records...], "total": <int>}.
"""
from __future__ import annotations

# Allowed enum values for the status filter (out-of-enum -> 400).
STATUS_ENUM = ("active", "inactive")

# The recognized filter parameters. Anything else is "unknown" -> 400 (strict).
RECOGNIZED_PARAMS = ("status", "category")


def _resources_seed() -> tuple[dict, ...]:
    """The EXACTLY-20-record primary collection from the task spec:
      15 active (active-001..active-015): 8 category A (001-008), 7 category B (009-015)
       5 inactive (inactive-001..inactive-005): no category.
    Returned as an immutable tuple of dicts; the server never mutates it."""
    records: list[dict] = []
    for n in range(1, 16):
        rid = f"active-{n:03d}"
        category = "A" if n <= 8 else "B"
        records.append({"id": rid, "status": "active", "category": category})
    for n in range(1, 6):
        rid = f"inactive-{n:03d}"
        records.append({"id": rid, "status": "inactive", "category": None})
    return tuple(records)


def _widgets_seed() -> tuple[dict, ...]:
    """A second, smaller collection with the IDENTICAL contract but a different known
    distribution, used ONLY as the held-out set for the staged evolution gate:
      10 active (active-001..active-010): 6 category A (001-006), 4 category B (007-010)
       4 inactive (inactive-001..inactive-004): no category."""
    records: list[dict] = []
    for n in range(1, 11):
        rid = f"active-{n:03d}"
        category = "A" if n <= 6 else "B"
        records.append({"id": rid, "status": "active", "category": category})
    for n in range(1, 5):
        rid = f"inactive-{n:03d}"
        records.append({"id": rid, "status": "inactive", "category": None})
    return tuple(records)


# collection_path -> (list_field, records). Immutable; seeded once at import.
COLLECTIONS: dict[str, tuple[str, tuple[dict, ...]]] = {
    "/resources": ("resources", _resources_seed()),
    "/widgets": ("widgets", _widgets_seed()),
}


def known_count(collection: str, params: dict) -> int:
    """The ground-truth count of records matching all applied recognized filters,
    computed directly from the seed (the 'known count in the database'). Assumes
    params are recognized + status (if present) is in-enum; callers guard those."""
    _, records = COLLECTIONS[collection]
    out = records
    if "status" in params:
        out = [r for r in out if r.get("status") == params["status"]]
    if "category" in params:
        out = [r for r in out if r.get("category") == params["category"]]
    return len(out)


def expected_counts(collection: str) -> dict:
    """The three documented expected counts for the count scenarios of one collection,
    derived deterministically from its seed."""
    return {
        "single_filter": known_count(collection, {"status": "active"}),
        "multi_filter": known_count(collection, {"status": "active", "category": "A"}),
        "empty_result": known_count(collection, {"status": "active", "category": "C"}),
    }


def category_b_ids(collection: str) -> list[str]:
    """IDs of the category-B active records (must NOT appear in a category=A result)."""
    _, records = COLLECTIONS[collection]
    return [r["id"] for r in records if r.get("status") == "active" and r.get("category") == "B"]


def inactive_ids(collection: str) -> list[str]:
    """IDs of the inactive records (must NOT appear in a status=active result)."""
    _, records = COLLECTIONS[collection]
    return [r["id"] for r in records if r.get("status") == "inactive"]
