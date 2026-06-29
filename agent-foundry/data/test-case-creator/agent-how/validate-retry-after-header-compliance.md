# api-tester-validate-retry-after-header-compliance — How spec

- **How:**
  1. Authenticate against the target and prepare the endpoint set for Retry-After compliance testing. Assert the setup preconditions hold before probing.
  2. Exceed the rate limit. Assert a 429 with a positive Retry-After header.
  3. Wait the advertised duration then retry. Assert the request succeeds.
  4. Inspect the header value. Assert it equals the documented window.
  5. Aggregate every scenario result and record the outcome. Assert the Retry-After accuracy is computed over all scenarios.
- **Tools:** http
- **Metric:** Pass: Retry-After accuracy meets the gold threshold. Fail: Retry-After is absent or wrong after a 429.
