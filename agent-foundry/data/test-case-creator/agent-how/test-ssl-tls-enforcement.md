# api-tester-test-ssl-tls-enforcement — How spec

- **How:**
  1. Authenticate against the target and prepare the endpoint set for TLS enforcement testing. Assert the setup preconditions hold before probing.
  2. Connect over the secure scheme. Assert the connection is accepted.
  3. Attempt an insecure connection. Assert it is rejected or redirected per docs.
  4. Inspect the security headers. Assert documented headers are present.
  5. Aggregate every scenario result and record the outcome. Assert the TLS enforcement rate is computed over all scenarios.
- **Tools:** http
- **Metric:** Pass: TLS enforcement rate meets the gold threshold. Fail: an insecure connection is allowed against docs.
