# api-tester-test-rate-limit-enforcement — How spec

- **How:**
  1. Authenticate against the target and prepare the endpoint set for rate limiting testing. Assert the setup preconditions hold before probing.
  2. Send requests up to the documented limit. Assert all are accepted with 2xx.
  3. Send one request past the limit. Assert the response code is 429.
  4. Wait the window then retry. Assert the request succeeds again.
  5. Aggregate every scenario result and record the outcome. Assert the rate-limit contract correctness is computed over all scenarios.
- **Tools:** http
- **Metric:** Pass: rate-limit contract correctness meets the gold threshold. Fail: the limiter does not return 429 past the limit.
