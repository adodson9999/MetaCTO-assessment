# api-tester-test-concurrent-request-handling — How spec

- **How:**
  1. Authenticate against the target and prepare the endpoint set for concurrency testing. Assert the setup preconditions hold before probing.
  2. Fire N concurrent creates. Assert each succeeds without corruption.
  3. Fire concurrent updates to one resource. Assert the final state is consistent.
  4. Check the post-run count. Assert the count delta matches the operations.
  5. Aggregate every scenario result and record the outcome. Assert the concurrent request success rate is computed over all scenarios.
- **Tools:** http
- **Metric:** Pass: concurrent request success rate meets the gold threshold. Fail: concurrency corrupts state or counts.
