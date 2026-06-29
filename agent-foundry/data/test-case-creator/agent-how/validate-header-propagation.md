# api-tester-validate-header-propagation — How spec

- **How:**
  1. Authenticate against the target and prepare the endpoint set for header propagation testing. Assert the setup preconditions hold before probing.
  2. Send a request with a tracing header. Assert the response echoes the header.
  3. Send without the header. Assert the documented default behavior.
  4. Inspect downstream propagation. Assert the header reaches downstream per docs.
  5. Aggregate every scenario result and record the outcome. Assert the header propagation rate is computed over all scenarios.
- **Tools:** http
- **Metric:** Pass: header propagation rate meets the gold threshold. Fail: a header is not propagated as documented.
