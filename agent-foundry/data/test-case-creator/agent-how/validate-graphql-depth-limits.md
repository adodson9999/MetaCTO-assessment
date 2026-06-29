# api-tester-validate-graphql-depth-limits — How spec

- **How:**
  1. Authenticate against the target and prepare the endpoint set for GraphQL depth limits testing. Assert the setup preconditions hold before probing.
  2. Send a query within the depth limit. Assert it succeeds.
  3. Send a query exceeding the depth limit. Assert it is rejected.
  4. Inspect the rejection. Assert the documented depth error.
  5. Aggregate every scenario result and record the outcome. Assert the depth enforcement rate is computed over all scenarios.
- **Tools:** http
- **Metric:** Pass: depth enforcement rate meets the gold threshold. Fail: an over-deep query is not rejected.
