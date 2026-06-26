# Shared skill — soft-delete-behavior test-plan construction

Collective (SkillClaw) skill offered to all four agents in the folder. Local filesystem
backend, air-gapped. Adoption is the user's call — never auto-applied.

## Distilled know-how

When converting a soft-delete-test brief into a plan, the failure modes that lose
Soft-Delete-Test Fidelity are:

1. **Substituting `{RESOURCE_ID}`.** Each `path_template` must keep the literal token
   `{RESOURCE_ID}`. The harness creates each resource, reads the real server-generated
   id, and substitutes it per case. An agent that writes a guessed id (e.g. `1`) or
   expands the token deletes/queries the wrong resource and breaks every downstream
   check.

2. **Dropping a descriptor.** The plan needs all seven top-level keys. The two most
   commonly forgotten are `db_query` (the direct `SELECT id, deleted_at, is_deleted ...`
   that proves the row survived with a non-null `deleted_at` within tolerance and
   `is_deleted=true`) and `include_deleted` (the `?include_deleted=true` re-inclusion
   check). Omitting either silently drops the heart of a *soft*-delete test — the
   evidence that the record was tombstoned, not destroyed.

3. **Wrong per-descriptor key count.** create=3, delete=3, get_deleted=4, collection=4,
   db_query=8, include_deleted=5. A missing key (e.g. `assert_deleted_at_not_null`,
   `assert_is_deleted_true`, or `deleted_at_within_seconds`) removes a check.

4. **Misreading the `db_query` asserts as mutations.** `assert_row_exists`,
   `assert_deleted_at_not_null`, `assert_is_deleted_true` are inert READ expectations.
   They never instruct the agent (or the harness) to INSERT/UPDATE the DB to make them
   true. The harness issues a read-only `SELECT` only.

5. **Quoting integers.** `case_count`, every `expected_status` integer, the integers
   inside the `delete.expected_status` array, and `deleted_at_within_seconds` are bare
   JSON numbers. Quoted strings ("404") are a defect.

6. **Wrong endpoint, method, or column name.** create is POST and delete is DELETE on
   the brief's `resource_endpoint`; the GET checks are GET; the DB columns
   (`id_column` / `deleted_at_column` / `is_deleted_column`) are copied verbatim from
   the brief. A mismatch points the SELECT at the wrong column and the row check fails.

## What "correct" looks like (the QA finding the headline metric reports)

A contract-correct soft-delete API yields, for every test case:
DELETE → 200/204; GET-by-id → exactly 404 with **no** posted field values in the body;
the id **absent** from the default collection but **present** under
`?include_deleted=true` with a non-null `deleted_at`; and a direct DB query returning
**exactly one** surviving row whose `deleted_at` is non-null, set within the tolerance
(10s) of the DELETE call, and whose `is_deleted` is true. Soft Delete Correctness
Rate = 100%.
