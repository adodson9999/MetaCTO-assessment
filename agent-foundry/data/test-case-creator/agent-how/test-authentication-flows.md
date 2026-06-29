# api-tester-test-authentication-flows — How spec

- **How:**
  1. Authenticate against the target and prepare the endpoint set for authentication testing. Assert the setup preconditions hold before probing.
  2. POST valid credentials to the login endpoint. Assert an accessToken and refreshToken are returned.
  3. Call a protected endpoint without a token. Assert the response code is exactly 401.
  4. Call a protected endpoint with an invalid token. Assert the response code is exactly 401.
  5. Aggregate every scenario result and record the outcome. Assert the authentication pass rate with FAR and FRR is computed over all scenarios.
- **Tools:** http
- **Metric:** Pass: authentication pass rate with FAR and FRR meets the gold threshold. Fail: a request that should be denied is accepted.
