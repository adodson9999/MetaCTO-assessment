# api-tester-verify-response-status-codes — How spec

- **How:**
  1. Authenticate against the target and prepare the endpoint set for HTTP status codes testing. Assert the setup preconditions hold before probing.
  2. Send a valid GET to an existing resource. Assert the response code is exactly 200.
  3. Request a non-existent resource id. Assert the response code is exactly 404.
  4. Send a malformed request. Assert the response code is in the 4xx class.
  5. Aggregate every scenario result and record the outcome. Assert the status-code accuracy over all scenarios is computed over all scenarios.
- **Tools:** http
- **Metric:** Pass: status-code accuracy over all scenarios meets the gold threshold. Fail: any endpoint returns the wrong status class.
