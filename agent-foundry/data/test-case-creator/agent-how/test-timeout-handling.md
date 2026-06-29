# api-tester-test-timeout-handling — How spec

- **How:**
  1. Authenticate against the target and prepare the endpoint set for timeout handling testing. Assert the setup preconditions hold before probing.
  2. Send a normal request. Assert it completes within the timeout.
  3. Send a slow/oversized request. Assert a documented timeout response.
  4. Inspect the timeout response. Assert the status and message are documented.
  5. Aggregate every scenario result and record the outcome. Assert the timeout enforcement rate is computed over all scenarios.
- **Tools:** http
- **Metric:** Pass: timeout enforcement rate meets the gold threshold. Fail: a timeout is not enforced as documented.
