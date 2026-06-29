# api-tester-test-pagination-behavior — How spec

- **How:**
  1. Authenticate against the target and prepare the endpoint set for pagination testing. Assert the setup preconditions hold before probing.
  2. GET the first page with a limit. Assert the item count equals the limit and total is reported.
  3. GET a subsequent page with skip. Assert the returned window matches skip and limit.
  4. Request limit 0. Assert the documented limit-0 behavior holds.
  5. Aggregate every scenario result and record the outcome. Assert the pagination correctness over all scenarios is computed over all scenarios.
- **Tools:** http
- **Metric:** Pass: pagination correctness over all scenarios meets the gold threshold. Fail: a page returns the wrong window or total.
