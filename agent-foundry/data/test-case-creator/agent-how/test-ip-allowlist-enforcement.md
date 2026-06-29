# api-tester-test-ip-allowlist-enforcement — How spec

- **How:**
  1. Authenticate against the target and prepare the endpoint set for IP allowlist testing. Assert the setup preconditions hold before probing.
  2. Request from an allowlisted address. Assert it is accepted.
  3. Request from a non-allowlisted address. Assert it is rejected with 403.
  4. Inspect the rejection. Assert no data is exposed.
  5. Aggregate every scenario result and record the outcome. Assert the IP allowlist enforcement rate is computed over all scenarios.
- **Tools:** http
- **Metric:** Pass: IP allowlist enforcement rate meets the gold threshold. Fail: a non-allowlisted address receives 2xx.
