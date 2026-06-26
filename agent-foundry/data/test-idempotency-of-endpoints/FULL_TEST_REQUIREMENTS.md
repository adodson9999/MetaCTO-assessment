# What a FULL idempotency test requires

> DummyJSON is left **as-is** (read-only target, never modified). This note records
> exactly what would be needed to run the **complete literal task** end-to-end — where
> every assertion is genuinely meaningful and a compliant target scores 100% — and what
> the current build already provides vs. what is missing.
>
> The current build is a **faithful test of DummyJSON's real behavior** (headline
> Idempotency Compliance Rate = 50%). It is NOT a gap in the agents — it is a gap in the
> **target**: DummyJSON has no idempotency layer, no persistence, and no SQL database.

---

## 1. The four literal assertions and what each one needs

| # | Literal assertion (from the task) | Infra it requires | Current build | Status |
|---|---|---|---|---|
| 1 | 2nd & 3rd response **codes** == 1st | any reachable endpoint | replays 3× and compares codes | ✅ already full |
| 2 | 2nd & 3rd response **bodies** byte-for-byte == 1st | an **idempotency layer** that caches & **replays the first stored response** (so even time/UUID fields are frozen on replay) | replays + exact byte compare | ⚠️ test is full; DummyJSON **fails** it (DELETE re-stamps `deletedOn`) |
| 3 | DB holds **exactly one record** after 3 identical-key requests | **persistent storage** + **direct DB access** (`psql`/`mysql`) | mapped to read-only `GET` state-effect probe | ⚠️ proxied; needs real DB |
| 4 | **fresh key** → **new** record, COUNT(\*) == 2 | a real **Idempotency-Key dedup layer** keyed per (endpoint, key) | sends a 2nd key, compares responses | ⚠️ test is full; DummyJSON **fails** it (header ignored) |

**Takeaway:** assertions 1, 2, 4 are already exercised correctly by the harness — DummyJSON
simply does not satisfy 2 and 4. Only assertion 3 (the `SELECT COUNT(*)`) is currently a
*proxy* and would need real infrastructure to become a true count.

---

## 2. Target API requirements (the missing piece)

A full test needs a target that actually implements idempotency. It must:

1. **Persist writes** to a real datastore (so a created/updated/deleted row exists to count).
2. **Honor an `Idempotency-Key` header** with cache-first-response semantics:
   - first request with key K for an endpoint → execute, **store the response**, return it;
   - any later request with the **same** K → return the **byte-identical stored response**
     (do **not** re-execute, do **not** re-stamp timestamps) and create **no** new row;
   - a request with a **new** key → a distinct operation (new row for a create).
3. **Serialize responses deterministically** (stable key order) so byte comparison is fair.
4. (Optional but realistic) return **409 Conflict** if the same key is reused with a
   *different* body, and expire keys after a documented TTL.

DummyJSON provides **none** of these (no `Idempotency-Key` code path; `deepFrozen` data,
so writes never persist; `DELETE` injects a fresh `deletedOn` timestamp every call).

---

## 3. Database access (for assertion 3)

The literal step is: `SELECT COUNT(*) FROM [table] WHERE [unique_field] = [value]`.

To run it you need:

- **A SQL database** (PostgreSQL or MySQL) that the target API writes to.
- **A CLI client on PATH** — neither is installed here:
  - `psql` (PostgreSQL):   `brew install libpq && brew link --force libpq`  (or full `postgresql`)
  - `mysql` (MySQL):       `brew install mysql-client` (or `mysql`)
- **A connection string** (DSN), e.g. `postgres://user:pass@127.0.0.1:5432/appdb`.
- **A table + unique-field map per endpoint**, e.g.:

  | endpoint | table | unique_field | value source |
  |---|---|---|---|
  | POST /products/add | `products` | `idempotency_key` (or natural key) | the key sent |
  | PUT /products/{id} | `products` | `id` | `{id}` from the path |
  | DELETE /products/{id} | `products` | `id` | `{id}` from the path |

  (For a create, count by the idempotency key or a natural unique field; for PUT/DELETE,
  count by the addressed `id`.)

---

## 4. Concrete setup checklist (to go from 50% → a real 100%-capable run)

Nothing in DummyJSON changes. You stand up a **different, idempotency-capable target** and
point this build at it:

1. **Run a database** (one-off, local):
   `docker run -d --name idem-pg -e POSTGRES_PASSWORD=pw -p 5432:5432 postgres:16`
   (Docker is not currently running on this machine — install/start it first.)
2. **Run an idempotency-capable API** against that DB (any stack) exposing the same
   `PUT /<col>/<id>`, `DELETE /<col>/<id>`, `POST /<col>/add` surface **with** `Idempotency-Key`
   middleware (see §2). Note its base URL, e.g. `http://localhost:9100`.
3. **Install a DB client** (§3) so the harness can issue `COUNT(*)`.
4. **Set the environment** and re-run — the build is already fully env-driven:
   ```bash
   export FORGE_TARGET_BASE_URL=http://localhost:9100
   export FORGE_PROVIDER=ollama                 # local backend (Ollama must already be running)
   export FORGE_DB_DSN=postgres://postgres:pw@127.0.0.1:5432/appdb   # consumed by the DB hook (§5)
   bash scripts/phase4_idempotency_run.sh
   ```
   `build_gold.py` rebuilds gold against the new target automatically, the four agents run,
   and the judge scores fidelity. Against a correctly-idempotent target the **headline
   Compliance Rate becomes 100%** (and the `ideal` tokens already encode that contract).

---

## 5. The one code change to make assertion 3 a real `COUNT(*)`

Everything else is already in place. The only edit needed when a real DB + client exist is in
`agents/common/idempotency.py` (and the mirror in `build_gold.py`): replace the GET-based
`_record_count(path)` with a DB-backed count, gated behind `FORGE_DB_DSN` so the current
no-DB behavior is preserved when it is unset.

```python
# sketch — not wired, since no DB/psql exists here (DummyJSON left as-is)
import os, subprocess
def _record_count(path, table, unique_field, value):
    dsn = os.environ.get("FORGE_DB_DSN")
    if not dsn:                                  # no DB → keep the read-only GET proxy
        code, _ = _get(path); return 1 if code == 200 else (0 if code == 404 else None)
    sql = f"SELECT COUNT(*) FROM {table} WHERE {unique_field} = %(v)s"   # parameterized
    out = subprocess.run(["psql", dsn, "-tA", "-v", f"v={value}", "-c", sql],
                         capture_output=True, text=True, timeout=15)
    return int(out.stdout.strip()) if out.returncode == 0 else None
```

The table/unique-field/value map from §3 would be added to `idempotency_spec.json` per
collection. The scenario tokens, judge, leaderboard, evolver, and debate-gated prompt all
stay exactly as they are.

---

## 6. Acceptance criteria — "full test passed"

Against an idempotency-capable, persistent, DB-backed target, a faithful agent should observe,
for every collection:

- `*_status_consistent` = true   (3 replays, same code)
- `*_body_byte_identical` = true (idempotency layer replays the stored first response)
- `*_single_record` = true       (`SELECT COUNT(*) … = 1` after the 3 identical-key requests)
- `post_new_key_distinct` = true (fresh key → `COUNT(*) = 2`, a distinct new row)

→ **Idempotency Compliance Rate = 100%**, **Correctness = 100%**, **Fidelity = 100%**.

Any deviation is then a **real defect in the target's idempotency implementation** — which is
exactly what this test is built to catch.
