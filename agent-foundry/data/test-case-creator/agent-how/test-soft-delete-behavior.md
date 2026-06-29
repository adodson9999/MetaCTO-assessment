# api-tester-test-soft-delete-behavior — How spec

- **How:**
  1. Authenticate against the target and prepare the endpoint set for soft delete testing. Assert the setup preconditions hold before probing.
  2. Delete a resource. Assert it is marked isDeleted with a deletedOn timestamp.
  3. Read the soft-deleted resource. Assert the documented visibility holds.
  4. List the collection. Assert soft-deleted items follow the documented rule.
  5. Aggregate every scenario result and record the outcome. Assert the soft delete correctness is computed over all scenarios.
- **Tools:** http
- **Metric:** Pass: soft delete correctness meets the gold threshold. Fail: a delete does not follow the documented soft-delete rule.
